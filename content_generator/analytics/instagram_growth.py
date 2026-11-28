"""Instagram follower-growth intelligence.

Deterministic, data-driven layer. It does not automate engagement, follow/unfollow,
DM spam, bots, or engagement pods. It converts first-party performance logs into
a compact strategy block for the next generation run.
"""
from __future__ import annotations
import json, os, statistics
from collections import defaultdict

LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
PERF_PATH = os.path.join(LEARNING_DIR, "performance_log.json")
SNAP_PATH = os.path.join(LEARNING_DIR, "follower_snapshots.json")


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return []


def _rates(m):
    reach=max(float(m.get("reach") or m.get("views") or 0),1.0)
    return {"share_rate":float(m.get("shares",0))/reach,"save_rate":float(m.get("saves",0))/reach,
            "comment_rate":float(m.get("comments",0))/reach,"action_rate":(float(m.get("shares",0))+float(m.get("saves",0))+float(m.get("comments",0)))/reach}


def analyze_growth(window=30):
    rows=[r for r in _load(PERF_PATH) if r.get("metrics")][-window:]
    snaps=_load(SNAP_PATH)
    by_format=defaultdict(list); by_hook=[]
    for r in rows:
        rates=_rates(r["metrics"]); fmt=r.get("format") or "unknown"; by_format[fmt].append(rates["action_rate"])
        if r.get("hook"): by_hook.append((rates["action_rate"],r.get("hook",""),fmt))
    format_rank=sorted(((statistics.mean(v),k,len(v)) for k,v in by_format.items()),reverse=True)
    hook_rank=sorted(by_hook,reverse=True)[:5]
    follower_delta=0
    if len(snaps)>=2: follower_delta=int(snaps[-1].get("count",0))-int(snaps[max(0,len(snaps)-8)].get("count",0))
    return {"posts_analyzed":len(rows),"follower_delta_recent":follower_delta,
            "best_formats":[{"format":k,"action_rate":round(s,4),"samples":n} for s,k,n in format_rank[:3]],
            "best_hooks":[{"hook":h,"format":f,"action_rate":round(s,4)} for s,h,f in hook_rank]}


def get_instagram_growth_block(window=30):
    a=analyze_growth(window)
    lines=["INSTAGRAM GROWTH DIRECTOR & STRATEGY AUDIT (first-party evidence):",
           "Growth funnel: non-follower reach -> 3-second hold/watch -> completion -> shares/saves -> profile visits -> follows -> website actions. Optimize without spam tactics.",
           "Invisibility Audit: Actively identify and eliminate the three patterns that make content invisible: (1) saturated/cliché templates, (2) failing to create a clear reason to follow the account (rather than just liking the post), and (3) safe, compromise copy that blends in with giants.",
           "Every growth reel: visible change in first second, <=8-word hook, real motion, fast payoff, captions, audio plan, loopable ending, and one follow/save/share CTA only.",
           "Use carousels for saveable education/comparisons; use Stories for retention, replies and trust; use Reels for discovery.",
           "Do not use follower bots, follow/unfollow automation, engagement pods, or mass unsolicited DMs."]
    # Only claim best formats when samples >= 5 and action_rate is non-zero
    qualifying_formats = [x for x in a.get("best_formats", []) if x.get("samples", 0) >= 5 and x.get("action_rate", 0) > 0]
    if qualifying_formats:
        lines.append("Best recent formats: "+", ".join(f"{x['format']} ({x['action_rate']:.2%} action/reach, n={x['samples']})" for x in qualifying_formats))
        
    # Exclude hooks in BOTTOM 20% or with 0 action_rate from 'reuse structure'
    bottom_hooks = set()
    try:
        from content_generator.core.learning_engine import _load_log
        log_entries = _load_log()
        if len(log_entries) >= 5:
            sorted_entries = sorted(log_entries, key=lambda e: sum(float(v) for v in (e.get("metrics") or {}).values() if isinstance(v, (int, float))))
            bottom_n = max(1, len(sorted_entries) // 5)
            bottom_hooks = {str(e.get("hook") or "") for e in sorted_entries[:bottom_n] if e.get("hook")}
    except Exception:
        pass

    qualifying_hooks = [
        x for x in a.get("best_hooks", [])
        if x.get("action_rate", 0) > 0 and str(x.get("hook") or "") not in bottom_hooks
    ]
    if qualifying_hooks:
        lines.append("Reuse the STRUCTURE, not wording, of these hooks: "+" | ".join(x["hook"][:90] for x in qualifying_hooks[:3]))
    lines.append(f"Recent follower delta snapshot: {a['follower_delta_recent']:+d}. Treat this as account-level growth, not post-level attribution.")
    return "\n".join(lines)
