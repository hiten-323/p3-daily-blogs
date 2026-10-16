"""One-off approved publish (Hiten, 2026-10-16 10:20 IST). Idempotent: skips a platform if the caption is already live."""
import json, os, sys, time, requests
sys.path.insert(0, os.getcwd())
from content_generator.publisher import instagram as ig, facebook as fb
from content_generator.publisher.meta_graph import META_GRAPH_BASE as G
D = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(D, "trial_reel_preview.mp4")
CAP = open(os.path.join(D, "caption.txt"), encoding="utf-8").read()
MARK = CAP.splitlines()[0]
out = {}

def ig_run():
    acct, tok = os.environ["INSTAGRAM_ACCOUNT_ID"], os.environ["INSTAGRAM_ACCESS_TOKEN"]
    r = requests.get(f"{G}/{acct}/media", params={"fields": "id,caption,permalink,media_type,timestamp", "limit": 25},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20).json()
    for m in r.get("data", []):
        if MARK in (m.get("caption") or ""):
            return {"skipped": "already_live", "media_id": m["id"], "permalink": m.get("permalink")}
    res = ig._post_reel_direct_binary(VIDEO, CAP)
    if res.get("success"):
        rb = requests.get(f"{G}/{res['media_id']}", params={"fields": "id,media_type,media_product_type,permalink,caption"},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=20).json()
        res["readback"] = {k: rb.get(k) for k in ("id", "media_type", "media_product_type", "permalink")}
        res["readback"]["caption_exact"] = rb.get("caption") == CAP
    return res

def fb_run():
    page = os.environ["FACEBOOK_PAGE_ID"]
    tok = fb.resolve_page_access_token(page, os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.environ["INSTAGRAM_ACCESS_TOKEN"])
    H = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{G}/{page}/video_reels", params={"fields": "id,description,permalink_url", "limit": 25}, headers=H, timeout=20).json()
    for v in r.get("data", []):
        if MARK in (v.get("description") or ""):
            return {"skipped": "already_live", "video_id": v["id"], "permalink": v.get("permalink_url")}
    s = requests.post(f"{G}/{page}/video_reels", data={"upload_phase": "start"}, headers=H, timeout=30).json()
    vid = s.get("video_id")
    if not vid:
        return {"success": False, "error": f"start_failed {s.get('error', {}).get('message', '')}"}
    size = os.path.getsize(VIDEO)
    with open(VIDEO, "rb") as fh:
        u = requests.post(f"https://rupload.facebook.com/video-upload/{G.rstrip('/').split('/')[-1]}/{vid}",
                          headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)}, data=fh, timeout=300)
    if u.status_code not in (200, 201):
        return {"success": False, "video_id": vid, "error": f"upload_failed {u.status_code} {u.text[:200]}"}
    f = requests.post(f"{G}/{page}/video_reels", data={"upload_phase": "finish", "video_id": vid,
                      "video_state": "PUBLISHED", "description": CAP}, headers=H, timeout=60).json()
    if not f.get("success"):
        return {"success": False, "video_id": vid, "error": f"finish_failed {json.dumps(f)[:300]}"}
    rb = {}
    for _ in range(40):
        rb = requests.get(f"{G}/{vid}", params={"fields": "id,status,permalink_url,description"}, headers=H, timeout=20).json()
        st = (rb.get("status") or {})
        if st.get("video_status") in ("ready", "error") and (st.get("publishing_phase") or {}).get("status") in ("complete", "error", None):
            if st.get("video_status") == "error" or (st.get("publishing_phase") or {}).get("status") != "in_progress":
                break
        time.sleep(15)
    pl = rb.get("permalink_url") or ""
    if pl.startswith("/"):
        pl = "https://www.facebook.com" + pl
    return {"success": (rb.get("status") or {}).get("video_status") == "ready", "video_id": vid, "permalink": pl,
            "status": rb.get("status"), "caption_exact": rb.get("description") == CAP}

for name, fn in (("instagram_reel", ig_run), ("facebook_reel", fb_run)):
    try:
        out[name] = fn()
    except Exception as e:
        out[name] = {"success": False, "error": repr(e)[:300]}
    print(name, json.dumps(out[name], ensure_ascii=False))
json.dump(out, open("adhoc_result.json", "w"), indent=2, ensure_ascii=False)
