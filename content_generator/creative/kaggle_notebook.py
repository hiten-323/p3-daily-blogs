"""Kaggle notebook that renders background plates for the concept library.

Positive prompts describe coffee footage only. Jars, packaging, text and logos
are named in the negative prompt so the GPU run does not invent a product.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile

from content_generator.creative.shorts_concepts import CONCEPTS

NEGATIVE = (
    "jar, bottle, can, packaging, label, text, logo, watermark, brand, "
    "people, hands, product shot, words, letters"
)


def prompts() -> list[dict]:
    rows = []
    for concept in CONCEPTS:
        rows.append({
            "id": concept["id"],
            "prompt": (
                f"{concept['ai_prompt']}, vertical 9:16, photoreal, shallow depth of field, "
                "cinematic grade, empty lower centre, no people, no hands"
            ),
        })
    return rows


_CODE = r'''
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROMPTS = json.loads(base64.b64decode("__PROMPTS_B64__"))
NEGATIVE = """__NEGATIVE__"""
OUT = Path("/kaggle/working/clips")
OUT.mkdir(parents=True, exist_ok=True)
# Stop with a manifest before the 12h GPU session is killed.
DEADLINE = time.time() + 9 * 60 * 60
# LTX-Video's diffusers bundle is ~29GB (fp32 T5). CogVideoX-2b is ~14GB.
LTX_MIN_FREE_GB = 32
COG_MIN_FREE_GB = 16


def _pip():
    cmd = [
        sys.executable, "-m", "pip", "install", "-q",
        "diffusers>=0.32.2",
        "transformers>=4.46",
        "accelerate>=1.1",
        "imageio",
        "imageio-ffmpeg",
        "sentencepiece",
        "protobuf",
        "safetensors",
        "huggingface_hub",
    ]
    try:
        subprocess.check_call(cmd)
    except Exception as exc:
        print("pip_failed", type(exc).__name__)


def _cache_dir():
    # Keep weights out of /kaggle/working so kernels output does not upload the model.
    path = Path.home() / ".cache" / "huggingface"
    path.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(path)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(path / "hub")
    return path


def _free_gb(path):
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return 0.0


def _export(frames, path):
    from diffusers.utils import export_to_video
    export_to_video(frames, str(path), fps=8)


def _pretrained(cls, repo, dtype):
    try:
        return cls.from_pretrained(repo, torch_dtype=dtype)
    except TypeError:
        return cls.from_pretrained(repo, dtype=dtype)


def _prepare(pipe):
    pipe.enable_model_cpu_offload()
    vae = getattr(pipe, "vae", None)
    if vae is not None and hasattr(vae, "enable_tiling"):
        vae.enable_tiling()
    return pipe


def _try_load(label, repo, cls_name, dtype, free, minimum):
    if free < minimum:
        print(label + "_skipped", "disk", round(free, 1))
        return None
    try:
        module = __import__("diffusers", fromlist=[cls_name])
        cls = getattr(module, cls_name)
        pipe = _prepare(_pretrained(cls, repo, dtype))
        print("model", repo)
        return pipe
    except Exception as exc:
        print(label + "_unavailable", type(exc).__name__)
        return None


def _load():
    import torch
    if not torch.cuda.is_available():
        print("cuda", False)
        return None, None
    print("cuda", True, torch.cuda.get_device_name(0))
    # T4 is compute 7.5, so the weights load in float16.
    dtype = torch.float16
    cache = _cache_dir()
    pipe = _try_load("ltx", "Lightricks/LTX-Video", "LTXPipeline", dtype, _free_gb(cache), LTX_MIN_FREE_GB)
    if pipe is not None:
        return pipe, "Lightricks/LTX-Video"
    pipe = _try_load("cogvideo", "THUDM/CogVideoX-2b", "CogVideoXPipeline", dtype, _free_gb(cache), COG_MIN_FREE_GB)
    if pipe is not None:
        return pipe, "THUDM/CogVideoX-2b"
    return None, None


_pip()
pipe, model_name = _load()
if pipe is None:
    raise SystemExit("no background model available")

manifest = []
for job in PROMPTS:
    if time.time() > DEADLINE:
        print("time_budget_reached")
        break
    dest = OUT / f"{job['id']}.mp4"
    try:
        kwargs = {
            "prompt": job["prompt"],
            "negative_prompt": NEGATIVE,
            "num_frames": 49,
            "num_inference_steps": 8 if model_name.startswith("Lightricks/") else 30,
        }
        if model_name.startswith("Lightricks/"):
            kwargs["width"] = 512
            kwargs["height"] = 768
        frames = pipe(**kwargs).frames[0]
        _export(frames, dest)
        manifest.append({"id": job["id"], "file": dest.name, "model": model_name, "prompt": job["prompt"]})
        print("wrote", dest.name)
    except Exception as exc:
        print("clip_failed", job["id"], type(exc).__name__)

Path("/kaggle/working/manifest.json").write_text(json.dumps({"model": model_name, "clips": manifest}, indent=1))
print("clips", len(manifest))
'''


def notebook_source() -> str:
    encoded = base64.b64encode(json.dumps(prompts()).encode()).decode()
    return _CODE.replace("__PROMPTS_B64__", encoded).replace("__NEGATIVE__", NEGATIVE)


def notebook_document() -> dict:
    source = notebook_source()
    lines = [line + "\n" for line in source.strip().split("\n")]
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# Purity Beans background bank\n",
                    "Coffee footage only. The negative prompt forbids jars, packaging, text and logos.\n",
                    "The official jar is composited later and is never generated here.\n",
                ],
            },
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": lines},
        ],
    }


def status_is_error(text: str) -> bool:
    return "kernelworkerstatus.error" in (text or "").lower()


def _output_logs(folder: str) -> str:
    chunks = []
    if not os.path.isdir(folder):
        return ""
    for dirpath, _dirnames, filenames in os.walk(folder):
        for name in sorted(filenames):
            if not name.endswith(".log"):
                continue
            try:
                with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as handle:
                    chunks.append(handle.read())
            except OSError:
                continue
    return "\n".join(chunks)


def emit_error_log(ref: str, secrets: list[str], owner: str, run, redact) -> None:
    """Download `kaggle kernels output` (it includes the .log) and print a masked tail."""
    folder = tempfile.mkdtemp(prefix="purity-kaggle-log-")
    try:
        proc = run(["kaggle", "kernels", "output", ref, "-p", folder], secrets, owner)
        raw = _output_logs(folder).strip() or f"{proc.stdout or ''}\n{proc.stderr or ''}"
        shown = redact("\n".join(raw.splitlines()[-80:])[-8000:], secrets).strip() or "(no kernel log)"
        logging.getLogger(__name__).info("[kaggle_bank] kernel error log tail:\n%s", shown)
        print("[kaggle_bank] kernel error log tail:", flush=True)
        print(shown, flush=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def kernel_metadata(username: str) -> dict:
    slug = f"{username}/purity-beans-bg-bank" if username else "purity-beans-bg-bank"
    return {
        "id": slug,
        "title": "Purity Beans bg bank",
        "code_file": "kaggle_backgrounds.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_tpu": "false",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
        "keywords": [],
        "dataset_sources": [],
        "kernel_sources": [],
        "competition_sources": [],
        "model_sources": [],
    }
