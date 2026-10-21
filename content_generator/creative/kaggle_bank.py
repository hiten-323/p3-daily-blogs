"""Weekly Kaggle clip bank and the daily reader.

A workflow pushes a GPU notebook (LTX-Video, CogVideoX-2B backup) that renders
one background plate per concept. Outputs land in the repo when they are small
enough, otherwise as GitHub release assets on the tag ``bg-bank``. Daily runs
take an unused clip whose concept matches the day before any live provider.

Missing KAGGLE_USERNAME or KAGGLE_KEY skips the push and the pull. The bank
reader does not need those secrets when clips are already local.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile

from content_generator.creative import kaggle_notebook as notebook

logger = logging.getLogger(__name__)

RELEASE_TAG = "bg-bank"
_RESERVED: set[str] = set()


def reset_session() -> None:
    _RESERVED.clear()


def manifest_path() -> str:
    return os.getenv("BG_BANK_MANIFEST", os.path.join("assets", "background_bank", "manifest.json"))


def usage_path() -> str:
    return os.getenv("CLIP_BANK_USAGE", os.path.join("output", "learning", "clip_bank_usage.json"))


def bank_dir() -> str:
    return os.getenv("BG_BANK_DIR", os.path.join("assets", "background_bank", "clips"))


def _limits() -> tuple[int, int]:
    clip = int(os.getenv("BG_BANK_MAX_CLIP_BYTES", str(8 * 1024 * 1024)))
    total = int(os.getenv("BG_BANK_MAX_TOTAL_BYTES", str(48 * 1024 * 1024)))
    return clip, total


def load_manifest(path: str | None = None) -> dict:
    try:
        with open(path or manifest_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("clips"), list):
            return data
    except Exception:
        pass
    return {"clips": []}


def save_manifest(data: dict, path: str | None = None) -> None:
    dest = path or manifest_path()
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)


def load_usage(path: str | None = None) -> list[dict]:
    try:
        with open(path or usage_path(), encoding="utf-8") as handle:
            rows = json.load(handle)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def used_ids(path: str | None = None) -> set[str]:
    return {str(row.get("id")) for row in load_usage(path) if row.get("id")} | set(_RESERVED)


def remember(pending: dict, path: str | None = None) -> None:
    if not pending or not pending.get("id"):
        return
    rows = [row for row in load_usage(path) if not (row.get("id") == pending.get("id") and row.get("date") == pending.get("date") and row.get("format") == pending.get("format"))]
    rows.append({
        "id": pending.get("id"),
        "date": pending.get("date"),
        "format": pending.get("format"),
        "concept": pending.get("concept"),
        "source": "kaggle_bank",
    })
    dest = path or usage_path()
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(rows[-400:], handle, indent=1)
    _RESERVED.add(str(pending["id"]))


def release(clip_id: str) -> None:
    _RESERVED.discard(str(clip_id or ""))


def available() -> bool:
    used = used_ids()
    return any(str(clip.get("id")) not in used for clip in load_manifest().get("clips") or [])


def _match(choice: dict) -> dict | None:
    from content_generator.creative.stock_video import CONCEPT_QUERY
    concept = (choice or {}).get("concept")
    bucket = CONCEPT_QUERY.get(concept or "", "")
    used = used_ids()
    clips = [clip for clip in load_manifest().get("clips") or [] if str(clip.get("id")) not in used]
    exact = [clip for clip in clips if clip.get("concept") == concept]
    if exact:
        return exact[0]
    same = [clip for clip in clips if clip.get("query") == bucket and bucket]
    return same[0] if same else None


def _redact(text: str, secrets: list[str]) -> str:
    out = text or ""
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def mask_derived(value: str) -> None:
    """Register a derived token with GitHub Actions before any later log line."""
    raw = str(value or "").strip()
    if len(raw) < 6 or any(ch in raw for ch in "\r\n"):
        return
    print(f"::add-mask::{raw}", flush=True)


def _credentials() -> tuple[str, str]:
    username = os.getenv("KAGGLE_USERNAME", "").strip()
    key = os.getenv("KAGGLE_KEY", "").strip()
    if username and key:
        return username, key
    token = os.getenv("KAGGLE_API_TOKEN", "").strip()
    if token:
        try:
            parsed = json.loads(token)
            if isinstance(parsed, dict):
                u = str(parsed.get("username") or "").strip()
                k = str(parsed.get("key") or "").strip()
                if u and k:
                    return u, k
        except Exception:
            pass
        if ":" in token:
            parts = token.split(":", 1)
            u = parts[0].strip()
            k = parts[1].strip()
            if u and k:
                return u, k
    return username, key


def _derived_basic(username: str, key: str) -> str:
    return base64.b64encode(f"{username}:{key}".encode()).decode()


def _write_kaggle_json(username: str, key: str) -> str:
    derived = _derived_basic(username, key)
    mask_derived(derived)
    mask_derived(f"Basic {derived}")
    home = os.getenv("KAGGLE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".kaggle")
    os.makedirs(home, mode=0o700, exist_ok=True)
    dest = os.path.join(home, "kaggle.json")
    payload = json.dumps({"username": username, "key": key}).encode()
    descriptor = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return dest


def _run(args: list[str], secrets: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    proc = subprocess.run(args, capture_output=True, text=True, env=env, check=False)
    logger.info("[kaggle_bank] %s rc=%s %s", args[0], proc.returncode, _redact((proc.stdout or "") + (proc.stderr or ""), secrets)[-240:])
    return proc


def _gh_token() -> str:
    return os.getenv("GH_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()


def ensure_local(clip: dict) -> str | None:
    path = clip.get("path") or ""
    if path and os.path.isfile(path) and os.path.getsize(path) > 1000:
        return path
    asset = clip.get("release_asset")
    tag = clip.get("release_tag") or RELEASE_TAG
    if not asset:
        return None
    token = _gh_token()
    if not token:
        logger.info("[kaggle_bank] release clip skipped (GitHub token unset)")
        return None
    cache = os.getenv("BG_BANK_CACHE", os.path.join("output", "creative", "bg_bank"))
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, os.path.basename(asset))
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        return dest
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    cmd = ["gh", "release", "download", tag, "--pattern", os.path.basename(asset), "--dir", cache, "--clobber"]
    if repo:
        cmd += ["--repo", repo]
    proc = _run(cmd, [token])
    return dest if proc.returncode == 0 and os.path.isfile(dest) else None


def take(choice: dict, label: str, seconds: int = 5) -> dict | None:
    clip = _match(choice)
    if not clip:
        logger.info("[kaggle_bank] no unused clip for %s", (choice or {}).get("concept"))
        return None
    path = ensure_local(clip)
    if not path:
        return None
    clip_id = str(clip.get("id"))
    _RESERVED.add(clip_id)
    return {
        "path": path,
        "id": clip_id,
        "source": "kaggle_bank",
        "date": (choice or {}).get("date"),
        "format": (choice or {}).get("format"),
        "concept": (choice or {}).get("concept"),
        "attribution": {
            "provider": "kaggle",
            "model": clip.get("model"),
            "prompt": clip.get("prompt"),
            "license": "generated background, no third-party clip",
        },
    }


def _dir_size(folder: str) -> int:
    total = 0
    if not os.path.isdir(folder):
        return 0
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            total += os.path.getsize(path)
    return total


def stage_clip(src: str, concept: str, *, model: str = "", prompt: str = "", query: str = "") -> dict:
    """Copy a clip into the repo bank, or mark it for the release when it is too large."""
    clip_id = f"kaggle:{concept}"
    size = os.path.getsize(src)
    per_clip, total_cap = _limits()
    record = {
        "id": clip_id,
        "concept": concept,
        "query": query,
        "model": model,
        "prompt": prompt,
        "bytes": size,
    }
    if size <= per_clip and _dir_size(bank_dir()) + size <= total_cap:
        os.makedirs(bank_dir(), exist_ok=True)
        dest = os.path.join(bank_dir(), f"{concept}.mp4")
        shutil.copyfile(src, dest)
        record.update({"path": dest, "storage": "repo", "release_tag": None, "release_asset": None})
        return record
    record.update({
        "path": "",
        "storage": "release",
        "release_tag": RELEASE_TAG,
        "release_asset": f"{concept}.mp4",
        "pending_file": src,
    })
    return record


def upload_release(files: list[str]) -> bool:
    if not files:
        return True
    token = _gh_token()
    if not token:
        logger.info("[kaggle_bank] oversized clips not uploaded (GitHub token unset)")
        return False
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    repo_args = ["--repo", repo] if repo else []
    view = _run(["gh", "release", "view", RELEASE_TAG, *repo_args], [token])
    if view.returncode != 0:
        created = _run([
            "gh", "release", "create", RELEASE_TAG, "--title", "Background clip bank",
            "--notes", "Kaggle weekly coffee backgrounds. No jars, text or logos.", *repo_args,
        ], [token])
        if created.returncode != 0:
            return False
    uploaded = _run(["gh", "release", "upload", RELEASE_TAG, *files, "--clobber", *repo_args], [token])
    return uploaded.returncode == 0


def ingest_dir(folder: str) -> dict:
    """Pull notebook outputs into the manifest. Large files stay out of git."""
    from content_generator.creative.stock_video import CONCEPT_QUERY
    manifest_file = os.path.join(folder, "manifest.json")
    described = {}
    if os.path.isfile(manifest_file):
        try:
            payload = json.loads(open(manifest_file, encoding="utf-8").read())
            for row in payload.get("clips") or []:
                described[row.get("id") or row.get("file", "").rsplit(".", 1)[0]] = row
        except Exception as exc:
            logger.info("[kaggle_bank] manifest unreadable: %s", type(exc).__name__)
    data = load_manifest()
    by_id = {clip.get("id"): clip for clip in data.get("clips") or []}
    pending = []
    new_release = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".mp4"):
            continue
        concept = name[:-4]
        info = described.get(concept) or {}
        record = stage_clip(
            os.path.join(folder, name), concept,
            model=str(info.get("model") or ""),
            prompt=str(info.get("prompt") or ""),
            query=CONCEPT_QUERY.get(concept, ""),
        )
        pending_file = record.pop("pending_file", "")
        if pending_file:
            staged = os.path.join(folder, record["release_asset"])
            if os.path.abspath(pending_file) != os.path.abspath(staged):
                shutil.copyfile(pending_file, staged)
            pending.append(staged)
            new_release.append(record["id"])
        by_id[record["id"]] = record
    if pending and not upload_release(pending):
        for clip_id in new_release:
            by_id.pop(clip_id, None)
        logger.info("[kaggle_bank] release upload failed — oversized clips left out of the bank")
    data["clips"] = list(by_id.values())
    save_manifest(data)
    return data


def write_kernel(folder: str, username: str) -> str:
    os.makedirs(folder, exist_ok=True)
    notebook_path = os.path.join(folder, "kaggle_backgrounds.ipynb")
    with open(notebook_path, "w", encoding="utf-8") as handle:
        json.dump(notebook.notebook_document(), handle)
    meta_path = os.path.join(folder, "kernel-metadata.json")
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(notebook.kernel_metadata(username), handle, indent=1)
    return folder


def push() -> int:
    username, key = _credentials()
    if not username or not key:
        logger.info("[kaggle_bank] push skipped (KAGGLE_USERNAME or KAGGLE_KEY unset)")
        return 0
    _write_kaggle_json(username, key)
    folder = tempfile.mkdtemp(prefix="purity-kaggle-")
    write_kernel(folder, username)
    proc = _run(["kaggle", "kernels", "push", "-p", folder], [username, key, _derived_basic(username, key)])
    return proc.returncode


def pull() -> int:
    username, key = _credentials()
    if not username or not key:
        logger.info("[kaggle_bank] pull skipped (KAGGLE_USERNAME or KAGGLE_KEY unset)")
        return 0
    _write_kaggle_json(username, key)
    secrets = [username, key, _derived_basic(username, key)]
    status = _run(["kaggle", "kernels", "status", f"{username}/purity-beans-bg-bank"], secrets)
    text = ((status.stdout or "") + (status.stderr or "")).lower()
    if "complete" not in text:
        logger.info("[kaggle_bank] kernel not complete — pull skipped")
        return 0
    folder = tempfile.mkdtemp(prefix="purity-kaggle-out-")
    output = _run(["kaggle", "kernels", "output", f"{username}/purity-beans-bg-bank", "-p", folder], secrets)
    if output.returncode != 0:
        return output.returncode
    ingest_dir(folder)
    return 0


def main() -> int:
    """Pull a finished weekly notebook, then push the next one.

    A missing secret is a clean skip (exit 0). A push or pull that was attempted
    and failed exits non-zero so the weekly workflow does not look green.
    """
    try:
        pull_rc = pull()
        push_rc = push()
    except Exception as exc:
        logger.info("[kaggle_bank] weekly run failed: %s", type(exc).__name__)
        return 1
    return 0 if pull_rc == 0 and push_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
