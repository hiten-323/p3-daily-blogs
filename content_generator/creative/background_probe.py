"""Report which daily background sources are live.

Missing secrets are a clean skip. The coded fallback is always live. The probe
does not generate video and does not print secret values. Derived Kaggle basic
tokens are registered with ::add-mask:: before any request.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# Cloudflare returns HTTP 403 error 1010 for Python-urllib before the key is read.
USER_AGENT = "PurityBeansBackground/1.0"

ORDER = (
    "kaggle_bank", "kaggle_gpu", "hf_ltx", "hf_wan", "pixazo", "runway",
    "pexels", "pixabay", "coded",
)


def _secret(name: str) -> str:
    return os.getenv(name, "").strip()


def mask_derived(value: str) -> None:
    raw = str(value or "").strip()
    if len(raw) < 6 or any(ch in raw for ch in "\r\n"):
        return
    print(f"::add-mask::{raw}", flush=True)


def _default_transport(method: str, url: str, headers: dict, timeout: float, data=None):
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=merged, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(1024)
    except TimeoutError:
        return "timeout", b""
    except Exception as exc:
        code = getattr(exc, "code", "error")
        body = b""
        reader = getattr(exc, "read", None)
        if callable(reader):
            try:
                body = reader() or b""
            except Exception:
                body = b""
        if "timed out" in str(exc).lower():
            return "timeout", b""
        return code, body[:300]


def _http_state(status) -> str:
    """Map a provider status to live, quota or down.

    401 and 403 are auth failures. 404 is a missing route, not a live source.
    400 and 422 still count as live: the key was accepted and the body was rejected.
    """
    if status in (401, 403):
        return "down"
    if status in (402, 429):
        return "quota"
    if status in ("timeout", "error", 404) or (isinstance(status, int) and status >= 500):
        return "down"
    if isinstance(status, int) and 200 <= status < 500:
        return "live"
    return "down"


def _kaggle_basic() -> str:
    from content_generator.creative import kaggle_bank
    username, key = kaggle_bank._credentials()
    if not username or not key:
        return ""
    derived = base64.b64encode(f"{username}:{key}".encode()).decode()
    mask_derived(derived)
    mask_derived(f"Basic {derived}")
    return derived


def _kaggle_token() -> str:
    """Opaque API token. A JSON or username:key blob stays on the legacy path."""
    from content_generator.creative import kaggle_bank
    return kaggle_bank.api_token()


def _token_state(status, body: bytes) -> str:
    """A 200 is live only when introspection says the token is active."""
    state = _http_state(status)
    if state != "live":
        return state
    try:
        payload = json.loads((body or b"").decode() or "{}")
    except Exception:
        return "down"
    if not isinstance(payload, dict) or payload.get("active") is False:
        return "down"
    if payload.get("active") is True or payload.get("username"):
        return "live"
    return "down"


def _pixazo_state(call, key: str) -> tuple[str, str]:
    """Probe the documented LTX 2.5 text-to-video routes.

    The body uses duration 1, which the API rejects. That must not queue a render.
    """
    from content_generator.creative.ai_backgrounds import PIXAZO_TEXT_TO_VIDEO
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "Ocp-Apim-Subscription-Key": key,
    }
    primary = os.getenv("PIXAZO_VIDEO_URL", PIXAZO_TEXT_TO_VIDEO)
    urls = [primary]
    if not os.getenv("PIXAZO_VIDEO_URL"):
        urls.append("https://gateway.pixazo.ai/ltx-2-5-pro/v1/text-to-video")
    last = "error"
    for url in urls:
        status, _body = call("POST", url, headers, 8, b'{"duration":1}')
        last = status
        if status == 404:
            continue
        return _http_state(status), f"http {status}"
    return "down", f"http {last}"


def probe_results(transport=None) -> list[dict]:
    """Return one row per source. Status is live, skipped, empty or down."""
    from content_generator.creative import hf_video, kaggle_bank
    call = transport or _default_transport
    rows = []

    unused = 0
    try:
        used = kaggle_bank.used_ids()
        unused = sum(1 for clip in kaggle_bank.load_manifest().get("clips") or [] if str(clip.get("id")) not in used)
    except Exception as exc:
        logger.info("[bg_probe] bank unreadable: %s", type(exc).__name__)
    rows.append({
        "name": "kaggle_bank",
        "status": "live" if unused else "empty",
        "detail": f"{unused} unused" if unused else "no unused clips",
    })

    token = _kaggle_token()
    if token:
        mask_derived(token)
        mask_derived(f"Bearer {token}")
        status, body = call(
            "POST", "https://api.kaggle.com/v1/security.OAuthService/IntrospectToken",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            8, json.dumps({"token": token}).encode(),
        )
        rows.append({"name": "kaggle_gpu", "status": _token_state(status, body), "detail": f"http {status}"})
    else:
        derived = _kaggle_basic()
        if not derived:
            rows.append({"name": "kaggle_gpu", "status": "skipped", "detail": "kaggle auth: missing"})
        else:
            status, _body = call(
                "GET", "https://www.kaggle.com/api/v1/kernels/list?pageSize=1",
                {"Authorization": f"Basic {derived}"}, 8, None,
            )
            rows.append({"name": "kaggle_gpu", "status": _http_state(status), "detail": f"http {status}"})

    token = _secret("HF_TOKEN")
    if not token:
        rows.append({"name": "hf_ltx", "status": "skipped", "detail": "HF_TOKEN unset"})
        rows.append({"name": "hf_wan", "status": "skipped", "detail": "HF_TOKEN unset"})
    else:
        who, _body = call("GET", "https://huggingface.co/api/whoami-v2", {"Authorization": f"Bearer {token}"}, 8, None)
        if _http_state(who) != "live":
            rows.append({"name": "hf_ltx", "status": "down", "detail": f"token http {who}"})
            rows.append({"name": "hf_wan", "status": "down", "detail": f"token http {who}"})
        else:
            for name, space in (("hf_ltx", hf_video.LTX_SPACE), ("hf_wan", hf_video.WAN_SPACE)):
                status, _body = call("GET", hf_video._space_host(space) + "/", {}, 8, None)
                rows.append({"name": name, "status": _http_state(status), "detail": f"space http {status}"})

    pixazo_key = _secret("PIXAZO_API_KEY")
    if not pixazo_key:
        rows.append({"name": "pixazo", "status": "skipped", "detail": "PIXAZO_API_KEY unset"})
    else:
        status, detail = _pixazo_state(call, pixazo_key)
        rows.append({"name": "pixazo", "status": status, "detail": detail})

    checks = (
        ("runway", "RUNWAY_API_KEY", "GET", "https://api.dev.runwayml.com/v1/organization", lambda key: {
            "Authorization": f"Bearer {key}", "X-Runway-Version": "2024-11-06",
        }),
        ("pexels", "PEXELS_API_KEY", "GET", "https://api.pexels.com/videos/search?query=coffee&per_page=1&orientation=portrait", lambda key: {
            "Authorization": key,
        }),
        ("pixabay", "PIXABAY_API_KEY", "GET", "https://pixabay.com/api/videos/?q=coffee&per_page=3", None),
    )
    for name, env_name, method, url, header_fn in checks:
        key = _secret(env_name)
        if not key:
            rows.append({"name": name, "status": "skipped", "detail": f"{env_name} unset"})
            continue
        headers = header_fn(key) if header_fn else {}
        target = url
        if name == "pixabay":
            target = f"{url}&key={key}"
        status, _body = call(method, target, headers, 8, None)
        rows.append({"name": name, "status": _http_state(status), "detail": f"http {status}"})

    rows.append({"name": "coded", "status": "live", "detail": "procedural fallback"})
    return rows


def main() -> int:
    rows = probe_results()
    summary = ", ".join(f"{row['name']}={row['status']}" for row in rows)
    for row in rows:
        detail = row.get("detail") or ""
        print(f"::notice::{row['name']}: {row['status']}" + (f" ({detail})" if detail else ""))
    print("background source probe: " + summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
