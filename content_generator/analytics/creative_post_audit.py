"""Post-generation visual QA and next-generation adaptation loop."""
from __future__ import annotations
import datetime, hashlib, json, logging, os
from pathlib import Path
from content_generator.core.ist_dates import today_ist
logger=logging.getLogger(__name__)
_DIR=Path(os.getenv("LEARNING_DIR","output/learning"))
_PATH=_DIR/"creative_post_audits.json"
def _load():
    try:
        d=json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.exists() else []
        return d if isinstance(d,list) else []
    except Exception: return []
def _save(rows):
    try:
        _DIR.mkdir(parents=True,exist_ok=True)
        _PATH.write_text(json.dumps(rows[-500:],indent=2,ensure_ascii=False),encoding="utf-8")
    except Exception as e: logger.warning("[creative-audit] save failed: %s",e)
def _img(path):
    try:
        from PIL import Image
        import numpy as np
        im=Image.open(path).convert("RGB"); w,h=im.size
        im=im.resize((min(320,w),max(1,int(h*min(320,w)/w))))
        a=np.asarray(im).astype("float32")/255; g=a.mean(2)
        # Detect whether visual edge activity is concentrated in the lower-middle
        # region versus the lower side rails. This is only a composition proxy,
        # not object recognition or proof that the central object is the jar.
        lower=g[int(g.shape[0]*.38):max(int(g.shape[0]*.9),int(g.shape[0]*.38)+1),:]
        cut0=max(1,int(lower.shape[1]*.25)); cut1=min(lower.shape[1]-1,int(lower.shape[1]*.75))
        focal=lower[:,cut0:cut1]
        sides=np.concatenate([lower[:,:cut0],lower[:,cut1:]],axis=1) if cut1>cut0 else lower
        def edges(region):
            if region.size==0:return 0.0
            dx=np.abs(np.diff(region,axis=1)).mean() if region.shape[1]>1 else 0.0
            dy=np.abs(np.diff(region,axis=0)).mean() if region.shape[0]>1 else 0.0
            return float((dx+dy)/2)
        focal_edges=edges(focal); side_edges=edges(sides)
        small=Image.open(path).convert("L").resize((16,16))
        return {"width":w,"height":h,"aspect_ratio":round(w/h,3) if h else 0,
                "brightness":round(float(g.mean()),4),"contrast":round(float(g.std()),4),
                "edge_density":round(edges(g),4),
                "upper_activity":round(float(g[:max(1,int(g.shape[0]*.35))].std()),4),
                "center_brightness_delta":round(abs(float(g[int(g.shape[0]*.2):int(g.shape[0]*.8),int(g.shape[1]*.2):int(g.shape[1]*.8)].mean())-float(g.mean())),4),
                "lower_center_edge_ratio":round(focal_edges/(side_edges+0.0001),3),
                "lower_center_edge_density":round(focal_edges,4),
                "visual_hash":hashlib.sha1(small.tobytes()).hexdigest()[:16]}
    except Exception as e: return {"error":f"{type(e).__name__}: {e}"}
def _video(path):
    out={"path":path,"frames_sampled":0,"frame_delta":0.0,"recommendations":[]}
    try:
        import imageio.v3 as iio, numpy as np
        frames=[]; brightness=[]; contrasts=[]
        for i,f in enumerate(iio.imiter(path,plugin="ffmpeg")):
            if i>=24: break
            if i%3: continue
            a=np.asarray(f).astype("float32")
            if a.ndim==3:a=a.mean(2)
            brightness.append(float(a.mean()/255.0))
            contrasts.append(float(a.std()/255.0))
            from PIL import Image
            frames.append(np.asarray(Image.fromarray(a.astype("uint8")).resize((32,32))).astype("float32"))
            if len(frames)>=8:break
        out["frames_sampled"]=len(frames)
        out["mean_brightness"]=round(sum(brightness)/len(brightness),4) if brightness else None
        out["mean_contrast"]=round(sum(contrasts)/len(contrasts),4) if contrasts else None
        if len(frames)>1: out["frame_delta"]=round(sum(float(np.abs(frames[i]-frames[i-1]).mean()/255) for i in range(1,len(frames)))/(len(frames)-1),4)
        if not frames:
            out["recommendations"].append("video visual audit failed: no frames could be decoded; inspect before treating QA as passed")
        elif len(frames)<3:
            out["recommendations"].append("video sampling incomplete; render QA is uncertain and requires inspection")
        elif out["frame_delta"]<.025:
            out["recommendations"].append("increase scene/motion change; video is visually static")
        if brightness and sum(brightness)/len(brightness)<.22:
            out["recommendations"].append("video is consistently dark; raise exposure/background separation")
        if contrasts and sum(contrasts)/len(contrasts)<.10:
            out["recommendations"].append("video has low frame contrast; strengthen foreground/background separation")
    except Exception as e:
        out["error"]=f"{type(e).__name__}: {e}"
        out["recommendations"].append("video visual audit failed: frame decoder error; inspect before treating QA as passed")
    return out
def _recs(m,platform):
    r=[]
    if m.get("error"):
        return ["visual pixel audit failed: inspect this render; metrics are unavailable"]
    if m.get("brightness",1)<.24:r.append("raise exposure/background separation; avoid another near-black frame")
    if m.get("contrast",1)<.12:r.append("increase foreground/background contrast")
    if m.get("edge_density",1)<.035:r.append("add visible action/texture such as pour, hand, steam, granules, or environment")
    if m.get("upper_activity",1)<.035:r.append("strengthen the first-frame visual hook in the upper safe zone")
    if (m.get("lower_center_edge_ratio",0)>1.8
            and m.get("lower_center_edge_density",0)>.025
            and platform in {"instagram","facebook","instagram_carousel","instagram_reel_thumbnail","generated_image"}):
        r.append("lower-center focal composition dominates; vary into a contextual or off-center composition")
    return r
def _div(h):
    h=[x for x in h if x]
    if len(h)<2:return 0.0
    n=d=0
    for i,x in enumerate(h):
        for y in h[i+1:]: n+=1; d+=x!=y
    return round(d/n,3) if n else 0
def audit_generated_creatives(*,day_number,generation_id,image_results=None,creative_dir=None,content=None):
    from content_generator.creative.jar_provenance import verify_jar_provenance
    image_results=image_results or {}; assets=[]; seen=set()
    def add(v,p):
        if isinstance(v,str) and v and os.path.exists(v) and v not in seen:seen.add(v);assets.append((v,p))
    for p,k in (("instagram","instagram_post"),("facebook","facebook_post"),("instagram_carousel","carousel"),("instagram_reel_thumbnail","reel")):
        v=image_results.get(k)
        for x in v if isinstance(v,list) else [v]:add(x,p)
    root=Path(creative_dir or os.getenv("CREATIVE_OUTPUT_DIR","output/creative"))
    today=today_ist().isoformat()
    for p in root.glob(f"*_{today}.mp4"):add(str(p),"video")
    # Audit every current-day rendered image, including renderer outputs that were not returned.
    for pattern in (f"*_{today}.jpg", f"*_{today}.jpeg", f"*_{today}.png"):
        for p in root.glob(pattern): add(str(p),"generated_image")
    images=[]; videos=[]
    for path,platform in assets:
        if path.lower().endswith(".mp4"):videos.append({"path":path,"platform":platform,**_video(path)});continue
        prov=verify_jar_provenance(path);m=_img(path);r=_recs(m,platform)
        if not prov.get("verified"):r.insert(0,"HARD BLOCK: image has no verified real-jar provenance")
        images.append({"path":path,"platform":platform,"jar_verified":bool(prov.get("verified")),"metrics":m,"recommendations":r})
    diversity=_div([x["metrics"].get("visual_hash") for x in images])
    if len(images)>=3 and diversity<.45:
        for x in images:x["recommendations"].append("portfolio diversity low: vary setting, camera distance, human/context cue, and visual progression")
    # Copy/content-type QA complements the pixel audit.
    copy_audit=[]
    for key in ("growth_reel","reels","yt_short","carousel","instagram_post","facebook_post","threads_post","linkedin_post","stories"):
        pieces = content.get(key) if isinstance(content,dict) else None
        if key == "reels" and isinstance(pieces,list): iterable=[(f"reel_{i+1}",p) for i,p in enumerate(pieces)]
        elif isinstance(pieces,dict): iterable=[(key,pieces)]
        else: iterable=[]
        for label,piece in iterable:
            if not isinstance(piece,dict) or not piece: continue
            hook=str(piece.get("hook") or piece.get("hook_text") or piece.get("headline") or piece.get("title") or "").strip()
            if key == "carousel" and isinstance(piece.get("slides"), list):
                slide_parts=[]
                for slide in piece.get("slides") or []:
                    if isinstance(slide,dict):
                        slide_parts.extend(str(slide.get(k) or "") for k in ("heading","headline","body","on_screen"))
                text=" ".join([str(piece.get(k) or "") for k in ("caption","body","description","cta","community_question")] + slide_parts)
            elif key == "yt_short" and isinstance(piece.get("scenes"), list):
                scene_parts=[]
                for scene in piece.get("scenes") or []:
                    if isinstance(scene,dict):
                        scene_parts.extend(str(scene.get(k) or "") for k in ("spoken","on_screen","visual"))
                text=" ".join([str(piece.get(k) or "") for k in ("caption","body","description","cta","community_question","title")] + scene_parts)
            else:
                text=" ".join(str(piece.get(k) or "") for k in ("caption","body","description","cta","community_question","text","hook","hook_text","headline","title"))
            cr=[]
            if len(hook)<12: cr.append("hook is too short to communicate a clear curiosity/problem")
            if key in ("growth_reel","reels","yt_short") and "follow" not in text.lower() and "subscribe" not in text.lower():
                cr.append(f"{label}: discovery video lacks an explicit follow/subscribe conversion cue")
            if key == "yt_short" and "subscribe" not in text.lower() and "short" not in text.lower():
                cr.append(f"{label}: YouTube Short lacks subscribe/channel retention trigger")
            if key == "carousel" and "save" not in text.lower() and "share" not in text.lower():
                cr.append(f"{label}: carousel lacks an explicit save/share cue for algorithmic distribution")
            if key in ("instagram_post","facebook_post","threads_post") and "?" not in text:
                cr.append(f"{label}: community asset lacks a question/debate trigger")
            if key == "threads_post" and "?" not in text:
                cr.append(f"{label}: Threads post needs an open-ended question to fuel reply ranking")
            if key == "linkedin_post" and len(hook)>140:
                cr.append(f"{label}: LinkedIn hook exceeds 140 chars before the see-more fold")
            if text.lower().count("shop")>=2:
                cr.append(f"{label}: commercial language repeats; protect discovery value before selling")
            copy_audit.append({"asset":label,"hook_length":len(hook),"recommendations":cr})
    recs=[]
    for x in images+videos+copy_audit:
        for r in x.get("recommendations",[]):
            if r not in recs:recs.append(r)
    row={"ts":datetime.datetime.now(datetime.timezone.utc).isoformat(),"day_number":day_number,"generation_id":generation_id,
         "image_assets":images,"video_assets":videos,"copy_audit":copy_audit,"portfolio_diversity":diversity,"recommendations":recs[:20],
         "asset_count":len(images)+len(videos)}
    rows=_load();rows.append(row);_save(rows)
    logger.info("[creative-audit] day=%s assets=%s diversity=%.2f recommendations=%s",day_number,row["asset_count"],diversity,len(recs))
    return row
def get_visual_adaptation_directives(max_days=5, platform=None) -> dict:
    """Extract actionable render directives from pixel/video findings, never copy-only warnings."""
    rows=_load()[-max_days:]
    visual_rows=[]
    for row in rows:
        recs=[]
        for asset in row.get("image_assets") or []:
            ap=str(asset.get("platform") or "")
            if platform and platform not in ap and ap not in {"generated_image","video"}:
                continue
            recs.extend(asset.get("recommendations") or [])
        for asset in row.get("video_assets") or []:
            ap=str(asset.get("platform") or "")
            if platform and platform not in ap and ap not in {"video","generated_image"}:
                continue
            recs.extend(asset.get("recommendations") or [])
        # Legacy audits stored only the aggregate recommendation list. Consume
        # it for backward compatibility only when there are no structured asset
        # findings at all; new records never learn visuals from copy-only checks.
        if not row.get("image_assets") and not row.get("video_assets"):
            recs.extend(
                r for r in (row.get("recommendations") or [])
                if any(tag in r.lower() for tag in (
                    "exposure", "near-black", "contrast", "action/texture",
                    "steam", "upper safe zone", "first-frame visual hook",
                    "visually static", "motion change", "diversity low",
                    "lower-center focal composition dominates",
                ))
            )
        visual_rows.append(list(dict.fromkeys(recs)))
    if not rows:
        return {"boost_exposure":False,"boost_contrast":False,"add_action_texture":False,
                "break_centered_catalog":False,"boost_upper_activity":False,"boost_motion":False,
                "diversify_palette":False,"active_recommendations":[]}
    counts={}
    for recs in visual_rows:
        for rec in recs:
            counts[rec]=counts.get(rec,0)+1
    latest=set(visual_rows[-1] if visual_rows else [])
    active={r for r,n in counts.items() if n>=2} | latest
    return {
        "boost_exposure": any("exposure" in r or "near-black" in r or "consistently dark" in r for r in active),
        "boost_contrast": any("contrast" in r for r in active),
        "add_action_texture": any("action/texture" in r or "steam" in r for r in active),
        "break_centered_catalog": any("lower-center focal composition dominates" in r for r in active),
        "boost_upper_activity": any("upper safe zone" in r or "first-frame visual hook" in r for r in active),
        "boost_motion": any("visually static" in r or "motion change" in r for r in active),
        "diversify_palette": any("diversity low" in r for r in active),
        "active_recommendations": sorted(list(active)),
    }
def get_adaptation_block(max_days=5):
    rows=_load()[-max_days:]
    if len(rows)<2:
        if len(rows)==1:
            raw=rows[0].get("recommendations") or []
            cnt={}
            for r in raw: cnt[r]=cnt.get(r,0)+1
            recurring=[r for r,n in cnt.items() if n>=2]
            if not recurring: return ""
        else: return ""
    else:
        counts={}
        for row in rows:
            for r in set(row.get("recommendations") or []):counts[r]=counts.get(r,0)+1
        recurring=[r for r,n in counts.items() if n>=2]
    if not recurring:return ""
    lines=["POST-GENERATION CREATIVE QA ADAPTATION (heuristic QA, not measured performance):",
           "Apply these recurring visual constraints to the NEXT generation:"]
    lines += [f"- {r}" for r in recurring[:8]]
    lines.append("Keep the authentic jar, but vary human context, camera distance, setting, motion, lighting, and visual progression. Do not reuse one visual template across platforms.")
    return "\n".join(lines)
def audit_summary(row):
    return f"creative_audit assets={row.get('asset_count',0)} diversity={row.get('portfolio_diversity',0):.2f} recommendations={len(row.get('recommendations') or [])}"

