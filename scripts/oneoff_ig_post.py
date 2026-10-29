"""One-off, owner-approved Instagram feed post (Hiten, 2026-10-29 12:45 IST).

The pipeline-wide Instagram pause (config/instagram_pause.json) stays ON.
This script makes exactly ONE publish attempt with no retries, and refuses
to run if the same post already exists on the account. It never prints
tokens. Usage (CI only): python scripts/oneoff_ig_post.py --confirm BOLD50-20261029
"""
from __future__ import annotations
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIRM = "BOLD50-20261029"
IMAGE_URL = ("https://raw.githubusercontent.com/hiten-323/p3-daily-blogs/main/"
             "brand_assets/oneoff/bold50_ig_20261029.jpg")
MARKER = "Use INSTA10 for 10% off any 50g jar."
CAPTION = (
    "Some mornings need just one thing: pure coffee. \u2615\n"
    "Purity Beans Bold is agglomerated instant coffee, so it dissolves fast and tastes full. "
    "No shortcuts and nothing added.\n"
    "The 50g jar is a good place to start. Use INSTA10 for 10% off any 50g jar.\n"
    "Link in bio \U0001F446\n"
    "#PurityBeans #InstantCoffee #PureCoffee #CoffeeIndia #MorningCoffee"
)


def _err(data) -> str:
    e = data.get("error") if isinstance(data, dict) else None
    if isinstance(e, dict):
        return f"{e.get('message')} (code={e.get('code')}, subcode={e.get('error_subcode')})"
    return str(data)[:300]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.confirm != CONFIRM:
        print("refused: confirm token mismatch"); return 2
    import requests
    from content_generator.publisher.meta_graph import META_GRAPH_BASE as G
    acct = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()
    tok = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not acct or not tok:
        print("refused: instagram credentials missing"); return 2
    h = {"Authorization": f"Bearer {tok}"}
    out = {"attempted": False, "success": False, "media_id": "", "permalink": "", "error": ""}

    def done(rc):
        print("RESULT " + json.dumps(out))
        path = os.environ.get("GITHUB_STEP_SUMMARY")
        if path:
            with open(path, "a") as f:
                f.write("### One-off IG post\n```\n" + json.dumps(out, indent=2) + "\n```\n")
        return rc

    # Idempotency: refuse if this caption is already live.
    r = requests.get(f"{G}/{acct}/media", params={"fields": "id,caption,permalink,timestamp", "limit": 10},
                     headers=h, timeout=20).json()
    if "data" not in r:
        out["error"] = "precheck_failed: " + _err(r); return done(1)
    for m in r["data"]:
        if MARKER in (m.get("caption") or ""):
            out.update(error="already_posted", media_id=m.get("id", ""), permalink=m.get("permalink", ""))
            return done(1)
    img = requests.head(IMAGE_URL, timeout=20)
    if img.status_code != 200:
        out["error"] = f"image_url_http_{img.status_code}"; return done(1)
    if a.dry_run:
        out["error"] = "dry_run_ok"; return done(0)

    out["attempted"] = True
    c = requests.post(f"{G}/{acct}/media", params={"image_url": IMAGE_URL, "caption": CAPTION},
                      headers=h, timeout=60).json()
    cid = c.get("id") if isinstance(c, dict) else None
    if not cid:
        out["error"] = "container: " + _err(c); return done(1)
    status = ""
    for _ in range(24):  # poll container status only (read-only), max ~2 min
        s = requests.get(f"{G}/{cid}", params={"fields": "status_code,status"}, headers=h, timeout=20).json()
        status = s.get("status_code", "")
        if status in ("FINISHED", "ERROR", "EXPIRED"):
            break
        time.sleep(5)
    if status != "FINISHED":
        out["error"] = f"container_status_{status or 'unknown'}"; return done(1)
    p = requests.post(f"{G}/{acct}/media_publish", params={"creation_id": cid}, headers=h, timeout=60).json()
    mid = p.get("id") if isinstance(p, dict) else None
    if not mid:
        out["error"] = "publish: " + _err(p); return done(1)
    out.update(success=True, media_id=mid)
    q = requests.get(f"{G}/{mid}", params={"fields": "permalink,timestamp"}, headers=h, timeout=20).json()
    out["permalink"] = q.get("permalink", ""); out["timestamp"] = q.get("timestamp", "")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
