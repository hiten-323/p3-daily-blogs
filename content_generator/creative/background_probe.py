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
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
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
    if status in (401, 403):
        return "down"
    if status in ("timeout", "error"):
        return "down"
    if isinstance(status, int):
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

    derived = _kaggle_basic()
    if not derived:
        rows.append({"name": "kaggle_gpu", "status": "skipped", "detail": "KAGGLE_USERNAME or KAGGLE_KEY unset"})
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

    checks = (
        ("pixazo", "PIXAZO_API_KEY", "GET", "https://gateway.pixazo.ai/", lambda key: {
            "Ocp-Apim-Subscription-Key": key, "Authorization": f"Bearer {key}",
        }),
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
