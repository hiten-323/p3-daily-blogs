"""Report which daily background sources are live.

Missing secrets are a clean skip. The coded fallback is always live. The probe
does not generate video and does not print secret values. Derived Kaggle basic
tokens are registered with ::add-mask:: before any request.
"""
from __future__ import annotations

import base64
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
    username, key = _secret("KAGGLE_USERNAME"), _secret("KAGGLE_KEY")
    if not username or not key:
        return ""
    derived = base64.b64encode(f"{username}:{key}".encode()).decode()
    mask_derived(derived)
    mask_derived(f"Basic {derived}")
    return derived


def _pixazo_state(call, key: str) -> tuple[str, str]:
    """Check the video route. A 404 there is not a live video source.

    The image route is only used to tell a bad key from a missing video path.
    An empty JSON body must not start a render.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "Ocp-Apim-Subscription-Key": key,
    }
    video = os.getenv("PIXAZO_VIDEO_URL", "https://gateway.pixazo.ai/ltx-video/v1/generate")
    status, _body = call("POST", video, headers, 8, b"{}")
    if status != 404:
        return _http_state(status), f"http {status}"
    image = os.getenv("PIXAZO_IMAGE_ENDPOINT", "https://gateway.pixazo.ai/flux-3-image/v1/text-to-image")
    image_status, _body = call("POST", image, headers, 8, b"{}")
    if image_status in (401, 403):
        return "down", f"http {image_status}"
    if _http_state(image_status) == "live":
        return "down", "video route 404"
    return "down", f"http {status}"


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

    username, key = _secret("KAGGLE_USERNAME"), _secret("KAGGLE_KEY")
    missing = [name for name, value in (("KAGGLE_USERNAME", username), ("KAGGLE_KEY", key)) if not value]
    derived = _kaggle_basic()
    if missing or not derived:
        detail = " and ".join(missing or ["KAGGLE_USERNAME", "KAGGLE_KEY"]) + " unset"
        rows.append({"name": "kaggle_gpu", "status": "skipped", "detail": detail})
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
            for name, model in (("hf_ltx", hf_video.LTX_MODEL), ("hf_wan", hf_video.WAN_MODEL)):
                status, _body = call("GET", f"https://huggingface.co/api/models/{model}", {}, 8, None)
                rows.append({"name": name, "status": _http_state(status), "detail": f"hub http {status}"})

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
