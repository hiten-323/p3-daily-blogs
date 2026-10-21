"""Kaggle notebook that renders background plates for the concept library.

Positive prompts describe coffee footage only. Jars, packaging, text and logos
are named in the negative prompt so the GPU run does not invent a product.
"""
from __future__ import annotations

import json

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
import json
from pathlib import Path

PROMPTS = json.loads("""__PROMPTS__""")
NEGATIVE = """__NEGATIVE__"""
OUT = Path("/kaggle/working/clips")
OUT.mkdir(parents=True, exist_ok=True)

def _export(frames, path):
    from diffusers.utils import export_to_video
    export_to_video(frames, str(path), fps=8)

pipe = None
model_name = None
try:
    import torch
    from diffusers import LTXPipeline
    pipe = LTXPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
    pipe.to("cuda")
    model_name = "Lightricks/LTX-Video"
    print("model", model_name)
except Exception as exc:
    print("ltx_unavailable", type(exc).__name__)
    try:
        import torch
        from diffusers import CogVideoXPipeline
        pipe = CogVideoXPipeline.from_pretrained("THUDM/CogVideoX-2b", torch_dtype=torch.float16)
        pipe.enable_model_cpu_offload()
        model_name = "THUDM/CogVideoX-2b"
        print("model", model_name)
    except Exception as exc2:
        print("cogvideo_unavailable", type(exc2).__name__)

if pipe is None:
    raise SystemExit("no background model available")

manifest = []
for job in PROMPTS:
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
    payload = json.dumps(prompts())
    return _CODE.replace("__PROMPTS__", payload).replace("__NEGATIVE__", NEGATIVE)


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


def kernel_metadata(username: str) -> dict:
    slug = f"{username}/purity-beans-bg-bank" if username else "purity-beans-bg-bank"
    return {
        "id": slug,
        "title": "Purity Beans background bank",
        "code_file": "kaggle_backgrounds.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_internet": "true",
        "keywords": ["purity-beans", "background"],
        "dataset_sources": [],
        "kernel_sources": [],
        "competition_sources": [],
        "model_sources": [],
    }
