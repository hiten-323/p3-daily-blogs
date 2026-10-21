"""Free background sources: stock, Hugging Face, Kaggle bank, probe, gates."""
import base64
import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest

from content_generator.core.brand_guard import EDITORIAL_THRESHOLD
from content_generator.core.fallback_ladder import PASS_FLOOR
from content_generator.core.viral_gate import PASS_MARK
from content_generator.creative import ai_backgrounds, background_probe, hf_video, kaggle_bank, stock_video
from content_generator.creative import kaggle_notebook as kn
from content_generator.creative import premium_cards as pc
from content_generator.creative import shorts_concepts as scn
from content_generator.creative.concept_backdrop import grade_toward_palette
from content_generator.creative.visual_gate import AESTHETIC_PASS, MIN_BG_MOTION

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    "PEXELS_API_KEY", "PIXABAY_API_KEY", "HF_TOKEN", "KAGGLE_API_TOKEN", "KAGGLE_USERNAME", "KAGGLE_KEY",
    "PIXAZO_API_KEY", "RUNWAY_API_KEY",
)
_KAGGLE_ALIASES = ("KAGGLE_API_TOKEN", "KAGGLE_TOKEN", "KAGGLE_API_KEY", "KAGGLE_USERNAME", "KAGGLE_KEY")


def _choice(**extra):
    base = {
        "date": "2026-10-21", "format": "short", "concept": "steam_backlight", "scene": "steam",
        "ai_prompt": "thick white steam curling upward, photoreal",
    }
    base.update(extra)
    return base


def _plate(tmp_path, name="plate.mp4"):
    path = tmp_path / name
    path.write_bytes(b"\x00\x00\x00\x18ftyp" + b"\x00" * 80)
    return path


def _frames(*_a, **_k):
    return [np.zeros((8, 8, 3), np.uint8) for _ in range(24)]


def test_provider_order_and_gates_unchanged():
    assert ai_backgrounds.PROVIDER_ORDER == (
        "kaggle_bank", "hf_ltx", "hf_wan", "pixazo", "runway", "pexels", "pixabay",
    )
    assert PASS_MARK == 8.0
    assert PASS_FLOOR == 8.0
    assert EDITORIAL_THRESHOLD == 8.0
    assert AESTHETIC_PASS == 8.0
    assert MIN_BG_MOTION == 12.0
    assert scn.PHASH_MIN_DISTANCE == 12
    assert scn.ROTATION_DAYS == 7
    motion = (ROOT / "content_generator/creative/cinematic_motion.py").read_text(encoding="utf-8")
    assert "variety_check" in motion and "official_jar_asset" in motion and "commit_usage" in motion
    stock = (ROOT / "content_generator/creative/stock_video.py").read_text(encoding="utf-8")
    assert "load_jar" not in stock and "CUTOUTS" not in stock


def test_queries_cover_concepts():
    assert stock_video.query_for("steam_backlight") == "coffee steam"
    assert stock_video.query_for("crema_swirl") == "coffee crema"
    assert stock_video.query_for("bean_cascade") == "coffee beans"
    assert stock_video.query_for("granule_dissolve") == "coffee pour"
    assert stock_video.query_for("rain_window_cafe") == "rain window cafe"
    assert stock_video.query_for("golden_hour_kitchen") == "coffee cafe"
    for concept in scn.CONCEPTS:
        assert stock_video.query_for(concept["id"]) in stock_video.QUERIES.values()


def test_vertical_hd_preferred_and_tiny_rejected():
    video = {"id": 7, "video_files": [
        {"link": "https://cdn.example/land.mp4", "width": 1920, "height": 1080},
        {"link": "https://cdn.example/vert.mp4", "width": 720, "height": 1280},
        {"link": "https://cdn.example/tiny.mp4", "width": 200, "height": 400},
    ]}
    picked = stock_video.best_pexels_file(video)
    assert picked["link"].endswith("vert.mp4")
    assert stock_video.best_pexels_file({"video_files": [{"link": "t.mp4", "width": 320, "height": 480}]}) is None
    hit = {"id": 3, "videos": {
        "large": {"url": "https://cdn.example/wide.mp4", "width": 1920, "height": 1080},
        "medium": {"url": "https://cdn.example/tall.mp4", "width": 1080, "height": 1920},
    }}
    assert stock_video.best_pixabay_file(hit)["url" if False else "link"].endswith("tall.mp4")


def test_brand_metadata_and_used_ids_skipped():
    branded = {"id": 1, "tags": "starbucks logo packaging", "videos": {
        "large": {"url": "https://cdn.example/a.mp4", "width": 1080, "height": 1920},
    }}
    clean = {"id": 2, "tags": "coffee steam cup", "user": "Asha", "videos": {
        "large": {"url": "https://cdn.example/b.mp4", "width": 1080, "height": 1920},
    }}
    used = {"id": 3, "tags": "coffee beans", "videos": {
        "large": {"url": "https://cdn.example/c.mp4", "width": 1080, "height": 1920},
    }}
    assert stock_video.clip_branded(branded)
    assert not stock_video.clip_branded(clean)
    ranked = stock_video.rank_stock_clips("pixabay", {"hits": [branded, used, clean]}, {"pixabay:3"})
    assert [video["id"] for video, _file in ranked] == [2]


def test_overlay_text_detector():
    smooth = np.zeros((96, 54, 3), np.uint8)
    smooth[:, :, 0] = np.linspace(20, 80, 96, dtype=np.uint8)[:, None]
    assert stock_video.frame_has_overlay_text(smooth) is False
    text = np.full((96, 54, 3), 30, np.uint8)
    for y in range(12, 28):
        text[y, 8:28:2] = 250
        text[y, 9:28:2] = 5
    assert stock_video.frame_has_overlay_text(text) is True


def test_stock_history_window_and_attribution(tmp_path, monkeypatch):
    hist = tmp_path / "stock.json"
    monkeypatch.setenv("STOCK_CLIP_HISTORY", str(hist))
    stock_video.reset_session()
    stock_video.remember({
        "id": "pexels:9", "source": "pexels", "date": "2026-10-01", "format": "reel",
        "concept": "steam_backlight", "attribution": {"author": "Asha", "license": "Pexels License"},
    })
    assert "pexels:9" in stock_video.recent_ids("2026-10-21")
    assert "pexels:9" not in stock_video.recent_ids("2026-11-15")
    saved = json.loads(hist.read_text())
    assert saved[0]["attribution"]["author"] == "Asha"


def test_pixabay_errors_do_not_log_the_key(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("PIXABAY_API_KEY", "supersecretpixabay")
    monkeypatch.setattr(stock_video, "_search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("key=supersecretpixabay")))
    assert stock_video.pixabay(_choice(), "lab", 5) is None
    assert "supersecretpixabay" not in caplog.text


def test_missing_secrets_skip_to_coded_fallback(monkeypatch):
    ai_backgrounds.reset_session()
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kaggle_bank, "available", lambda: False)
    called = []
    monkeypatch.setattr(stock_video, "pexels", lambda *a, **k: called.append("pexels"))
    monkeypatch.setattr(stock_video, "pixabay", lambda *a, **k: called.append("pixabay"))
    monkeypatch.setattr(hf_video, "ltx", lambda *a, **k: called.append("ltx"))
    frames, source = ai_backgrounds.fetch_background(_choice(), "lab", (8, 8), 5)
    assert frames is None and source == "procedural"
    assert called == []


def test_chain_stops_at_first_plate_and_splits_same_day(tmp_path, monkeypatch):
    ai_backgrounds.reset_session()
    for name in SECRET_NAMES:
        monkeypatch.setenv(name, "present")
    monkeypatch.setattr(ai_backgrounds, "load_frames", _frames)
    monkeypatch.setattr(kaggle_bank, "available", lambda: True)
    calls = []
    kaggle = _plate(tmp_path, "kaggle.mp4")
    hf = _plate(tmp_path, "hf.mp4")

    def take(*_a, **_k):
        calls.append("kaggle_bank")
        return {"path": str(kaggle), "id": "kaggle:steam_backlight"}

    def ltx(*_a, **_k):
        calls.append("hf_ltx")
        return str(hf)

    monkeypatch.setattr(kaggle_bank, "take", take)
    monkeypatch.setattr(hf_video, "ltx", ltx)
    monkeypatch.setattr(hf_video, "wan", lambda *a, **k: calls.append("hf_wan"))
    frames, source = ai_backgrounds.fetch_background(_choice(), "lab", (8, 8), 5)
    assert source == "kaggle_bank" and frames
    reel, reel_source = ai_backgrounds.fetch_background(_choice(format="reel"), "lab2", (8, 8), 5)
    assert reel_source == "hf_ltx" and reel
    assert calls == ["kaggle_bank", "hf_ltx"]


def test_same_source_reused_when_it_is_the_only_one(tmp_path, monkeypatch):
    ai_backgrounds.reset_session()
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ai_backgrounds, "load_frames", _frames)
    monkeypatch.setattr(kaggle_bank, "available", lambda: True)
    plate = _plate(tmp_path, "only.mp4")
    calls = []

    def take(*_a, **_k):
        calls.append("kaggle")
        return {"path": str(plate), "id": "kaggle:steam_backlight"}

    monkeypatch.setattr(kaggle_bank, "take", take)
    assert ai_backgrounds.fetch_background(_choice(), "a", (8, 8), 5)[1] == "kaggle_bank"
    assert ai_backgrounds.fetch_background(_choice(format="reel"), "b", (8, 8), 5)[1] == "kaggle_bank"
    assert calls == ["kaggle", "kaggle"]


def test_commit_records_stock_attribution(tmp_path, monkeypatch):
    ai_backgrounds.reset_session()
    hist = tmp_path / "stock.json"
    attr = tmp_path / "attr.json"
    monkeypatch.setenv("STOCK_CLIP_HISTORY", str(hist))
    monkeypatch.setenv("BACKGROUND_ATTRIBUTION", str(attr))
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-secret")
    for name in ("HF_TOKEN", "PIXAZO_API_KEY", "RUNWAY_API_KEY", "PIXABAY_API_KEY", "KAGGLE_USERNAME", "KAGGLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kaggle_bank, "available", lambda: False)
    monkeypatch.setattr(ai_backgrounds, "load_frames", _frames)
    plate = _plate(tmp_path, "pexels.mp4")

    def pexels(choice, label, seconds):
        return {
            "path": str(plate), "id": "pexels:42", "source": "pexels",
            "date": choice.get("date"), "format": choice.get("format"), "concept": choice.get("concept"),
            "attribution": {"provider": "pexels", "author": "Asha", "license": "Pexels License", "page_url": "https://www.pexels.com/video/42"},
        }

    monkeypatch.setattr(stock_video, "pexels", pexels)
    frames, source = ai_backgrounds.fetch_background(_choice(), "lab", (8, 8), 5)
    assert source == "pexels" and frames
    ai_backgrounds.commit_usage()
    saved = json.loads(hist.read_text())
    assert saved[0]["id"] == "pexels:42" and saved[0]["attribution"]["author"] == "Asha"
    assert json.loads(attr.read_text())[0]["clip_id"] == "pexels:42"
    assert "pexels-secret" not in hist.read_text()


def test_hf_quota_busy_and_timeout_skip_cleanly(tmp_path, monkeypatch):
    hf_video.reset_session()
    monkeypatch.setattr(hf_video, "_OUT", str(tmp_path))
    monkeypatch.setenv("HF_TOKEN", "hf-secret-token")
    calls = []

    def inference(target, prompt, token, timeout):
        calls.append(target[1])
        assert token == "hf-secret-token"
        if "ltx" in target[1]:
            return 429, b'{"error":"quota exceeded"}', "application/json"
        return 200, b"\x00\x00\x00\x18ftyp" + b"\x00" * 40, "video/mp4"

    def space(*_a, **_k):
        calls.append("space")
        return 503, b'{"error":"currently loading","estimated_time":30}', "application/json"

    monkeypatch.setattr(hf_video, "_inference", inference)
    monkeypatch.setattr(hf_video, "_space", space)
    assert hf_video.ltx(_choice(), "lab", 5) is None
    saved = hf_video.wan(_choice(), "lab", 5)
    assert saved and saved.endswith("hf_wan_bg.mp4")
    assert calls[0] == "space"
    assert "fal-ai/ltx-video-13b-distilled" in calls
    assert hf_video.interpret("timeout", b"", "")[0] == "timeout"
    assert hf_video.interpret(503, b'{"estimated_time": 4}', "application/json")[0] == "busy"
    assert hf_video.interpret(401, b"unauthorized", "application/json")[0] == "auth"


def test_hf_auth_failure_does_not_call_wan(monkeypatch):
    hf_video.reset_session()
    monkeypatch.setenv("HF_TOKEN", "hf-secret-token")
    monkeypatch.setattr(hf_video, "_space", lambda *a, **k: (401, b'{"error":"Invalid token"}', "application/json"))
    monkeypatch.setattr(hf_video, "_inference", lambda *a, **k: (_ for _ in ()).throw(AssertionError("router called")))
    assert hf_video.ltx(_choice(), "lab", 5) is None
    assert hf_video.wan(_choice(), "lab", 5) is None


def test_space_payloads_match_the_live_gradio_apis():
    api, data = hf_video.space_call("Lightricks/ltx-video-distilled", "steam rising")
    assert api == "text_to_video"
    assert data[0] == "steam rising"
    assert data[6] == "text-to-video"
    assert data[2] is None and data[3] is None
    api, data = hf_video.space_call("Wan-AI/Wan2.1", "steam rising")
    assert api == "t2v_generation_async"
    assert data == ["steam rising", "720*1280", False, -1]
    assert hf_video._router_url("fal-ai", "fal-ai/wan/v2.1/1.3b/text-to-video").startswith(
        "https://router.huggingface.co/fal-ai/fal-ai/wan/v2.1/1.3b/text-to-video"
    )


def test_gradio_sse_complete_event_is_a_video_url():
    body = (
        b'event: complete\n'
        b'data: [{"video":{"url":"https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/out.mp4"}}, 7]\n\n'
    )
    kind, extra = hf_video.interpret(200, body, "text/event-stream")
    assert kind == "url"
    assert extra.endswith("out.mp4")


def test_pixazo_uses_documented_text_to_video_and_allowed_duration():
    from content_generator.creative.ai_backgrounds import PIXAZO_TEXT_TO_VIDEO, _pixazo_duration
    assert PIXAZO_TEXT_TO_VIDEO == "https://gateway.pixazo.ai/ltx-2-5-lite/v1/text-to-video"
    assert _pixazo_duration(5) == 6
    assert _pixazo_duration(8) == 8
    assert "ltx-video/v1/generate" not in PIXAZO_TEXT_TO_VIDEO


def test_colour_grade_moves_toward_label_palette():
    pal = pc.PALETTES["bold"][0]
    frame = np.zeros((16, 12, 3), np.uint8)
    frame[..., 2] = 200
    graded = grade_toward_palette(frame, pal)
    assert graded[..., 0].mean() > frame[..., 0].mean()
    assert graded[..., 2].mean() < frame[..., 2].mean()


def test_notebook_prompts_forbid_jars_and_cover_the_library():
    jobs = kn.prompts()
    assert len(jobs) == len(scn.CONCEPTS)
    assert 12 <= len(jobs) <= 20
    for job in jobs:
        low = job["prompt"].lower()
        assert "jar" not in low and "logo" not in low and "packaging" not in low
    source = kn.notebook_source()
    assert "Lightricks/LTX-Video" in source
    assert "THUDM/CogVideoX-2b" in source
    assert "jar" in kn.NEGATIVE and "logo" in kn.NEGATIVE and "text" in kn.NEGATIVE
    meta = kn.kernel_metadata("purity")
    assert meta["enable_gpu"] == "true"
    assert meta["id"] == "purity/purity-beans-bg-bank"
    document = kn.notebook_document()
    blob = json.dumps(document["cells"][1])
    assert "negative_prompt" in blob


def test_bank_keeps_small_clips_and_releases_large_ones(tmp_path, monkeypatch):
    monkeypatch.setenv("BG_BANK_DIR", str(tmp_path / "clips"))
    monkeypatch.setenv("BG_BANK_MANIFEST", str(tmp_path / "manifest.json"))
    monkeypatch.setenv("CLIP_BANK_USAGE", str(tmp_path / "usage.json"))
    monkeypatch.setenv("BG_BANK_MAX_CLIP_BYTES", "100")
    monkeypatch.setenv("BG_BANK_MAX_TOTAL_BYTES", "1000")
    kaggle_bank.reset_session()
    big = tmp_path / "steam_backlight.mp4"
    big.write_bytes(b"x" * 250)
    uploaded = []
    monkeypatch.setattr(kaggle_bank, "upload_release", lambda files: uploaded.extend(files) or True)
    record = kaggle_bank.stage_clip(str(big), "steam_backlight", model="Lightricks/LTX-Video", query="steam")
    assert record["storage"] == "release"
    assert not (tmp_path / "clips" / "steam_backlight.mp4").exists()
    monkeypatch.setenv("BG_BANK_MAX_CLIP_BYTES", "10000")
    small = tmp_path / "crema_swirl.mp4"
    small.write_bytes(b"y" * 40)
    kept = kaggle_bank.stage_clip(str(small), "crema_swirl", query="crema")
    assert kept["storage"] == "repo"
    assert Path(kept["path"]).is_file()
    monkeypatch.setenv("BG_BANK_MAX_CLIP_BYTES", "100")
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "steam_backlight.mp4").write_bytes(b"x" * 250)
    (folder / "manifest.json").write_text(json.dumps({"clips": [{"id": "steam_backlight", "model": "Lightricks/LTX-Video"}]}))
    data = kaggle_bank.ingest_dir(str(folder))
    assert uploaded
    assert any(clip["concept"] == "steam_backlight" for clip in data["clips"])


def test_daily_run_prefers_unused_matching_bank_clip(tmp_path, monkeypatch):
    monkeypatch.setenv("BG_BANK_MANIFEST", str(tmp_path / "manifest.json"))
    monkeypatch.setenv("CLIP_BANK_USAGE", str(tmp_path / "usage.json"))
    kaggle_bank.reset_session()
    clip = tmp_path / "steam.mp4"
    clip.write_bytes(b"z" * 1200)
    kaggle_bank.save_manifest({"clips": [
        {"id": "kaggle:steam_backlight", "concept": "steam_backlight", "query": "steam", "path": str(clip), "model": "ltx"},
        {"id": "kaggle:rain_window_cafe", "concept": "rain_window_cafe", "query": "rain_window", "path": str(clip), "model": "ltx"},
    ]})
    taken = kaggle_bank.take(_choice(), "lab", 5)
    assert taken["id"] == "kaggle:steam_backlight"
    kaggle_bank.remember(taken)
    again = kaggle_bank.take(_choice(format="reel"), "lab", 5)
    assert again is None


def test_kaggle_push_masks_derived_token_and_skips_without_secrets(tmp_path, monkeypatch, capsys, caplog):
    caplog.set_level(logging.INFO)
    for name in _KAGGLE_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kaggle_bank, "_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert kaggle_bank.main() == 0
    assert "kaggle auth: missing" in capsys.readouterr().out
    monkeypatch.setenv("KAGGLE_USERNAME", "purity-user")
    monkeypatch.setenv("KAGGLE_KEY", "kaggle-secret-key")
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "kaggle"))

    class _Proc:
        def __init__(self):
            self.returncode = 0
            self.stdout = "pushed kaggle-secret-key"
            self.stderr = ""

    monkeypatch.setattr(kaggle_bank, "_run", lambda *a, **k: _Proc())
    assert kaggle_bank.push() == 0
    out = capsys.readouterr().out
    derived = base64.b64encode(b"purity-user:kaggle-secret-key").decode()
    assert f"::add-mask::{derived}" in out
    assert f"::add-mask::Basic {derived}" in out
    visible = out.replace(f"::add-mask::{derived}", "").replace(f"::add-mask::Basic {derived}", "")
    assert "kaggle-secret-key" not in visible
    assert "kaggle-secret-key" not in caplog.text
    stored = json.loads((tmp_path / "kaggle" / "kaggle.json").read_text())
    assert stored["key"] == "kaggle-secret-key"
    if os.name != "nt": assert oct(os.stat(tmp_path / "kaggle" / "kaggle.json").st_mode & 0o777) == "0o600"


def test_kaggle_api_token_is_passed_to_the_cli_and_not_logged(tmp_path, monkeypatch, capsys, caplog):
    caplog.set_level(logging.INFO)
    for name in _KAGGLE_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KAGGLE_TOKEN", "KGAT_test_token_value")
    monkeypatch.setenv("KAGGLE_USERNAME", "purity-user")
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "kaggle"))
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "pushed KGAT_test_token_value"
        stderr = ""

    def _run(args, secrets):
        seen["args"] = args
        seen["secrets"] = list(secrets)
        seen["token"] = os.environ.get("KAGGLE_API_TOKEN")
        return _Proc()

    monkeypatch.setattr(kaggle_bank, "_run", _run)
    assert kaggle_bank.push() == 0
    assert seen["args"][:3] == ["kaggle", "kernels", "push"]
    assert seen["token"] == "KGAT_test_token_value"
    assert "KGAT_test_token_value" in seen["secrets"]
    assert not (tmp_path / "kaggle" / "kaggle.json").exists()
    out = capsys.readouterr().out
    visible = out.replace("::add-mask::KGAT_test_token_value", "").replace("::add-mask::Bearer KGAT_test_token_value", "")
    assert "KGAT_test_token_value" not in visible
    assert "KGAT_test_token_value" not in caplog.text


def test_probe_uses_bearer_token_and_hides_it(monkeypatch, capsys):
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in _KAGGLE_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_test_token_value")
    seen = {}

    def transport(method, url, headers, timeout, data=None):
        seen["method"] = method
        seen["url"] = url
        seen["auth"] = headers.get("Authorization")
        seen["body"] = data
        return 200, b'{"active":true,"username":"purity-user"}'

    monkeypatch.setattr(background_probe, "_default_transport", transport)
    rows = {row["name"]: row for row in background_probe.probe_results()}
    assert rows["kaggle_gpu"]["status"] == "live"
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/IntrospectToken")
    assert seen["auth"] == "Bearer KGAT_test_token_value"
    assert b"KGAT_test_token_value" in seen["body"]
    out = capsys.readouterr().out
    visible = out.replace("::add-mask::KGAT_test_token_value", "").replace("::add-mask::Bearer KGAT_test_token_value", "")
    assert "KGAT_test_token_value" not in visible
    assert background_probe._token_state(200, b'{"active":false}') == "down"


def test_http_404_and_cloudflare_block_are_not_live():
    assert background_probe._http_state(200) == "live"
    assert background_probe._http_state(400) == "live"
    assert background_probe._http_state(404) == "down"
    assert background_probe._http_state(401) == "down"
    assert background_probe._http_state(429) == "quota"


def test_pexels_search_sends_named_user_agent(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-test-key")
    captured = {}

    class _Resp:
        def read(self):
            return b'{"videos":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(req, timeout):
        captured["ua"] = req.get_header("User-agent")
        return _Resp()

    monkeypatch.setattr(stock_video, "_open", opener)
    stock_video.pexels({"concept": "steam_backlight", "scene": "steam"}, "lab", 5)
    assert captured["ua"] == stock_video.USER_AGENT
    assert "Python-urllib" not in captured["ua"]


def test_pixazo_lite_route_400_is_live_and_does_not_send_a_prompt(monkeypatch, capsys):
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PIXAZO_API_KEY", "pixazo-test-key")
    seen = []

    def transport(method, url, headers, timeout, data=None):
        seen.append((url, data))
        if "ltx-2-5-lite" in url:
            return 400, b'{"message":"duration rejected"}'
        return 500, b""

    monkeypatch.setattr(background_probe, "_default_transport", transport)
    rows = {row["name"]: row for row in background_probe.probe_results()}
    assert rows["pixazo"]["status"] == "live"
    assert rows["pixazo"]["detail"] == "http 400"
    assert seen and b"duration" in seen[0][1]
    assert b"prompt" not in seen[0][1]
    assert "pixazo-test-key" not in capsys.readouterr().out


def test_hf_probe_checks_space_hosts(monkeypatch):
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HF_TOKEN", "hf-test-token")
    seen = []

    def transport(method, url, headers, timeout, data=None):
        seen.append(url)
        if "whoami" in url:
            return 200, b"{}"
        if "lightricks-ltx-video-distilled" in url:
            return 200, b"ok"
        if "wan-ai-wan2-1" in url:
            return 404, b"missing"
        return 500, b""

    monkeypatch.setattr(background_probe, "_default_transport", transport)
    rows = {row["name"]: row for row in background_probe.probe_results()}
    assert rows["hf_ltx"]["status"] == "live"
    assert rows["hf_wan"]["status"] == "down"
    assert any("lightricks-ltx-video-distilled.hf.space" in url for url in seen)


def test_probe_reports_skips_and_hides_secrets(monkeypatch, capsys):
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PIXABAY_API_KEY", "supersecretpixabay")
    for name in _KAGGLE_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KAGGLE_USERNAME", "purity-user")
    monkeypatch.setenv("KAGGLE_KEY", "kaggle-secret-key")
    seen = []

    def transport(method, url, headers, timeout, data=None):
        seen.append(url)
        return 200, b"{}"

    monkeypatch.setattr(background_probe, "_default_transport", transport)
    assert background_probe.main() == 0
    out = capsys.readouterr().out
    assert "supersecretpixabay" not in out
    assert "kaggle-secret-key" not in out
    assert "pixabay=live" in out
    assert "coded=live" in out
    assert "hf_ltx=skipped" in out
    assert "pexels=skipped" in out
    derived = base64.b64encode(b"purity-user:kaggle-secret-key").decode()
    assert f"::add-mask::{derived}" in out
    assert any("key=supersecretpixabay" in url for url in seen)


def test_workflows_wire_probe_and_do_not_dispatch_publish():
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    weekly = (ROOT / ".github/workflows/kaggle-backgrounds.yml").read_text(encoding="utf-8")
    assert "python -m content_generator.creative.background_probe" in daily
    assert "python -m content_generator.creative.background_probe" in weekly
    for name in SECRET_NAMES:
        assert f"{name}: ${{{{ secrets.{name} }}}}" in daily
    assert "GH_TOKEN: ${{ github.token }}" in daily
    assert "python -m content_generator.creative.kaggle_bank" in weekly
    assert "kaggle>=2.2.4" in weekly
    assert 'print("kaggle auth: "' in weekly
    assert "KAGGLE_API_TOKEN: ${{ secrets.KAGGLE_API_TOKEN }}" in weekly
    assert "gh workflow run" not in weekly
    assert "daily.yml" not in weekly
    assert "retry-unposted" not in weekly


def test_official_cutout_ignores_stock_and_untrusted_jars(tmp_path, monkeypatch):
    from content_generator.creative import jar_provenance as jp
    outside = tmp_path / "stock_jar.png"
    outside.write_bytes(b"not-a-real-jar")
    canonical = os.path.join(pc._DIR, pc.CUTOUTS["bold"])
    registry = {
        "bad": {"asset_real_jar_verified": True, "jar_asset_id": str(outside), "render_source": "approved_photo"},
        "ok": {"asset_real_jar_verified": True, "jar_asset_id": canonical, "render_source": "cinematic_real_jar"},
    }
    monkeypatch.setattr(jp, "_load_registry", lambda: registry)
    chosen = pc.official_jar_asset("bold")
    assert os.path.basename(chosen) == os.path.basename(canonical)
    assert "stock_jar" not in chosen


def test_cinematic_composites_official_cutout(monkeypatch, tmp_path):
    from content_generator.creative import cinematic_motion as cm
    seen = {}
    real_load = pc.load_jar
    canonical = os.path.join(pc._DIR, pc.CUTOUTS["bold"])

    def spy(sku, height, source=None):
        seen["source"] = source
        return real_load(sku, height, source=source)

    monkeypatch.setattr(pc, "load_jar", spy)
    monkeypatch.setattr(pc, "official_jar_asset", lambda sku: canonical)
    meta = cm.render_cinematic_video("bold", [{"on": "Morning steam", "sub": "Brew it slow"}], str(tmp_path / "c.mp4"),
                                     seconds=1.0, seed=0, audio=None)
    assert seen["source"] == canonical
    assert meta["jar_asset_id"] == canonical



def test_kaggle_credentials_parse_api_token(monkeypatch):
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)

    # Empty case
    assert kaggle_bank._credentials() == ("", "")
    assert background_probe._kaggle_basic() == ""

    # JSON token case
    token_json = json.dumps({"username": "purity_json_user", "key": "secret_key_123"})
    monkeypatch.setenv("KAGGLE_API_TOKEN", token_json)
    assert kaggle_bank._credentials() == ("purity_json_user", "secret_key_123")
    basic = background_probe._kaggle_basic()
    assert basic == base64.b64encode(b"purity_json_user:secret_key_123").decode()

    # Colon-separated token case
    monkeypatch.setenv("KAGGLE_API_TOKEN", "purity_colon_user:secret_key_456")
    assert kaggle_bank._credentials() == ("purity_colon_user", "secret_key_456")
    basic_colon = background_probe._kaggle_basic()
    assert basic_colon == base64.b64encode(b"purity_colon_user:secret_key_456").decode()

    # Direct username and key precedence
    monkeypatch.setenv("KAGGLE_USERNAME", "direct_user")
    monkeypatch.setenv("KAGGLE_KEY", "direct_key")
    assert kaggle_bank._credentials() == ("direct_user", "direct_key")
