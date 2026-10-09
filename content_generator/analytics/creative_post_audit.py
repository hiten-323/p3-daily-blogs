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
def _sample_video_frames(path, max_frames=8, decode_limit=3600):
    """Sample frames across a clip, preferring evenly spaced timeline positions."""
    import imageio.v3 as iio
    import numpy as np
    from PIL import Image

    meta={}
    try:
        meta=iio.immeta(path,plugin="ffmpeg") or {}
    except Exception:
        meta={}
    fps=meta.get("fps")
    duration=meta.get("duration")
    total=None
    try:
        if fps and duration and float(fps)>0 and float(duration)>0:
            total=max(1,int(float(fps)*float(duration)))
    except (TypeError,ValueError):
        total=None

    if total:
        limit=min(total,decode_limit)
        targets=sorted(set(int(round(i*(limit-1)/max(max_frames-1,1))) for i in range(min(max_frames,limit))))
        frame_map={}
        for i,frame in enumerate(iio.imiter(path,plugin="ffmpeg")):
            if i in targets:
                frame_map[i]=Image.fromarray(np.asarray(frame).astype("uint8")).convert("RGB")
            if not targets or i >= targets[-1]:
                break
        frames=[frame_map[i] for i in targets if i in frame_map]
        return {"frames":frames,"fps":float(fps),"duration_s":float(duration),
                "strategy":"timeline_evenly_spaced","frames_decoded_to":targets[-1] if targets else 0,
                "truncated":total>decode_limit}

    # Metadata may be unavailable for damaged files/codecs. Build a bounded,
    # low-resolution reservoir over the entire readable stream instead of
    # accidentally treating only the opening second as the whole video.
    candidates=[]
    decoded=0
    for i,frame in enumerate(iio.imiter(path,plugin="ffmpeg")):
        decoded=i+1
        if i%12==0:
            im=Image.fromarray(np.asarray(frame).astype("uint8")).convert("RGB")
            im.thumbnail((320,320))
            candidates.append((i,im.copy()))
        if decoded>=decode_limit:
            break
    if not candidates:
        return {"frames":[],"fps":None,"duration_s":None,"strategy":"no_frames","frames_decoded_to":decoded}
    take=min(max_frames,len(candidates))
    idxs=sorted(set(int(round(i*(len(candidates)-1)/max(take-1,1))) for i in range(take)))
    return {"frames":[candidates[i][1] for i in idxs],"fps":None,"duration_s":None,
            "strategy":"stream_reservoir","frames_decoded_to":decoded,"truncated":decoded>=decode_limit}


def _video(path):
    out={"path":path,"frames_sampled":0,"frame_delta":0.0,"recommendations":[]}
    try:
        import numpy as np
        sample=_sample_video_frames(path,max_frames=8)
        frames=[]
        brightness=[]; contrasts=[]
        for im in sample["frames"]:
            gray=np.asarray(im.convert("L").resize((32,32))).astype("float32")
            frames.append(gray)
            rgb=np.asarray(im.convert("RGB")).astype("float32")/255.0
            brightness.append(float(rgb.mean()))
            contrasts.append(float(rgb.std()))
        out["frames_sampled"]=len(frames)
        out["sample_strategy"]=sample.get("strategy")
        out["duration_s"]=sample.get("duration_s")
        out["mean_brightness"]=round(sum(brightness)/len(brightness),4) if brightness else None
        out["mean_contrast"]=round(sum(contrasts)/len(contrasts),4) if contrasts else None
        if len(frames)>1:
            out["frame_delta"]=round(sum(float(np.abs(frames[i]-frames[i-1]).mean()/255) for i in range(1,len(frames)))/(len(frames)-1),4)
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
        if sample.get("truncated"):
            out["recommendations"].append("video exceeded visual-audit sampling cap; inspect the omitted tail")
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
def _vision_review(images, videos, content=None) -> dict:
    """
    Optional multimodal critique of the actual rendered pixels.
    This is advisory: unavailable API, malformed responses, or timeouts never
    block a generation, and model findings are kept separate from performance data.
    """
    if os.getenv("ENABLE_VISION_CREATIVE_AUDIT", "true").strip().lower() not in {"1","true","yes"}:
        return {"status":"disabled","model":"","assets":[],"recommendations":[]}
    api_key=os.getenv("GEMINI_API_KEY","").strip()
    if not api_key:
        return {"status":"skipped_no_api_key","model":"","assets":[],"recommendations":[]}
    try:
        import base64, io, urllib.request
        from PIL import Image
        model=os.getenv("GEMINI_VISION_AUDIT_MODEL","gemini-2.5-flash").strip()
        parts=[]
        sampled=[]
        # Keep calls bounded for free-tier safety; prioritize one asset per platform,
        # then one video keyframe set. All files are actual rendered outputs.
        selected=[]
        seen_platforms=set()
        for asset in images:
            platform=str(asset.get("platform") or "unknown")
            if platform not in seen_platforms:
                selected.append(asset); seen_platforms.add(platform)
            if len(selected)>=6: break
        def image_part(path, max_side=768):
            with Image.open(path) as im:
                im=im.convert("RGB")
                im.thumbnail((max_side,max_side))
                buf=io.BytesIO(); im.save(buf,format="JPEG",quality=78,optimize=True)
                return {"inline_data":{"mime_type":"image/jpeg","data":base64.b64encode(buf.getvalue()).decode("ascii")}}
        for idx, asset in enumerate(selected):
            path=asset.get("path")
            if not path or not os.path.exists(path): continue
            prov=None
            try:
                from content_generator.creative.jar_provenance import verify_jar_provenance
                prov=verify_jar_provenance(path)
            except Exception: pass
            parts.append({"text":f"ASSET {idx+1}: platform={asset.get('platform')}; file={os.path.basename(path)}. Inspect the actual rendered pixels."})
            jar_path=(prov or {}).get("jar_asset_id")
            if (prov or {}).get("verified") and jar_path and os.path.exists(jar_path):
                parts.append({"text":"Authentic source jar reference for comparison:"})
                parts.append(image_part(jar_path))
            parts.append({"text":"Rendered output to critique:"})
            parts.append(image_part(path))
            sampled.append({"asset":os.path.basename(path),"platform":asset.get("platform")})
        # Sample up to 2 native videos, three frames each, without uploading full video files.
        for video in videos[:2]:
            path=video.get("path")
            if not path or not os.path.exists(path): continue
            try:
                sampled_video=_sample_video_frames(path,max_frames=3)
                frames=[]
                for im in sampled_video.get("frames") or []:
                    im=im.convert("RGB"); im.thumbnail((640,640))
                    buf=io.BytesIO(); im.save(buf,format="JPEG",quality=72)
                    frames.append(base64.b64encode(buf.getvalue()).decode("ascii"))
                if frames:
                    parts.append({"text":f"VIDEO: {os.path.basename(path)}; sampled frames using {sampled_video.get('strategy')} strategy over the readable timeline. Judge pacing, motion, continuity, first-frame hook, readability and real-jar presentation. Do not infer audio from silent frames."})
                    for frame in frames:
                        parts.append({"inline_data":{"mime_type":"image/jpeg","data":frame}})
                    sampled.append({"asset":os.path.basename(path),"platform":video.get("platform","video"),
                                    "sampled_video_frames":len(frames),"sample_strategy":sampled_video.get("strategy")})
            except Exception as exc:
                logger.info("[creative-audit] vision video sampling skipped for %s: %s",os.path.basename(path),exc)
        if not parts:
            return {"status":"no_assets","model":model,"assets":[],"recommendations":[]}
        rubric=(
            "You are a strict creative director reviewing rendered assets for Purity Beans, an Indian instant-coffee brand. "
            "Do not claim an asset will go viral. Evaluate each actual image/video sample for: first-frame stopping power, "
            "immediate message clarity, typography legibility, contrast/exposure, mobile-safe zones, visual hierarchy, "
            "distinctiveness versus a generic catalogue ad, human/context/action cues, payoff-to-hook fit, realism, and "
            "whether the visible package appears consistent with the supplied authentic source jar reference. "
            "Never invent product facts. The jar reference is authoritative; if label fidelity is uncertain, say uncertain. "
            "Return STRICT JSON only: {\"assets\":[{\"asset\":string,\"score\":integer_1_to_5,"
            "\"strengths\":[string],\"issues\":[string],\"directives\":[one_or_more_of_"
            "\"boost_exposure,boost_contrast,add_action_texture,break_centered_catalog,boost_upper_activity,boost_motion,diversify_palette\"]}],"
            "\"portfolio_issues\":[string]}. Use concise actionable findings, not generic praise. "
            "If a video only has sampled frames, do not infer audio or full-video details."
        )
        parts.insert(0,{"text":rubric})
        body=json.dumps({"contents":[{"parts":parts}],"generationConfig":{"temperature":0.1,"maxOutputTokens":1800}}).encode("utf-8")
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json","User-Agent":"PurityBeans-CreativeAudit/1.0"},method="POST")
        with urllib.request.urlopen(req,timeout=35) as resp:
            data=json.loads(resp.read().decode("utf-8"))
        raw="".join(str(p.get("text") or "") for p in (data.get("candidates") or [{}])[0].get("content",{}).get("parts",[]) if isinstance(p,dict))
        # Recover JSON even if the provider wraps it in a Markdown fence.
        raw=raw.strip()
        if raw.startswith("```"):
            raw=raw.split("\n",1)[-1]
            if raw.endswith("```"): raw=raw[:-3]
        parsed=json.loads(raw)
        if not isinstance(parsed,dict) or not isinstance(parsed.get("assets"),list):
            raise ValueError("vision model response did not match expected JSON shape")
        return {"status":"ok","model":model,"assets":parsed.get("assets",[])[:8],
                "portfolio_issues":parsed.get("portfolio_issues",[])[:8],"sampled":sampled,
                "recommendations":[]}
    except Exception as exc:
        logger.warning("[creative-audit] optional vision review unavailable: %s",exc)
        return {"status":"failed_non_blocking","model":os.getenv("GEMINI_VISION_AUDIT_MODEL","gemini-2.5-flash"),
                "assets":[],"recommendations":[],"error":f"{type(exc).__name__}: {exc}"[:240]}


def _apply_vision_review(vision: dict, images: list[dict], videos: list[dict]) -> list[str]:
    """Attach model critique to each audited asset and map its directives to renderer QA."""
    asset_by_name={os.path.basename(str(a.get("path") or "")):a for a in images+videos}
    recs=[]
    for item in vision.get("assets") or []:
        if not isinstance(item,dict): continue
        name=os.path.basename(str(item.get("asset") or ""))
        target=asset_by_name.get(name)
        if not target: continue
        score=item.get("score")
        try: score=max(1,min(5,int(score)))
        except Exception: score=None
        directives=[d for d in (item.get("directives") or []) if d in {
            "boost_exposure","boost_contrast","add_action_texture","break_centered_catalog",
            "boost_upper_activity","boost_motion","diversify_palette"}]
        target["vision_review"]={"score":score,"strengths":item.get("strengths") or [],
                                 "issues":item.get("issues") or [],"directives":directives}
        for issue in target["vision_review"]["issues"]:
            recs.append(f"vision:{name}: {str(issue)[:180]}")
    for issue in vision.get("portfolio_issues") or []:
        recs.append(f"vision:portfolio: {str(issue)[:180]}")
    vision["_renderer_directives"]={}
    for item in vision.get("assets") or []:
        if not isinstance(item,dict):continue
        name=os.path.basename(str(item.get("asset") or "")); target=asset_by_name.get(name)
        if not target:continue
        platform=str(target.get("platform") or "unknown")
        bucket=vision["_renderer_directives"].setdefault(platform,[])
        for directive in item.get("directives") or []:
            if directive in {"boost_exposure","boost_contrast","add_action_texture","break_centered_catalog","boost_upper_activity","boost_motion","diversify_palette"} and directive not in bucket:
                bucket.append(directive)
    return recs


def audit_generated_creatives(*,day_number,generation_id,image_results=None,creative_dir=None,content=None):
    from content_generator.creative.jar_provenance import verify_jar_provenance
    image_results=image_results or {}; assets=[]; seen=set()
    def add(v,p):
        if isinstance(v,str) and v and os.path.exists(v) and v not in seen:seen.add(v);assets.append((v,p))
    for p,k in (("instagram","instagram_post"),("facebook","facebook_post"),("instagram_carousel","carousel"),("instagram_reel_thumbnail","reel")):
        v=image_results.get(k)
        for x in v if isinstance(v,list) else [v]:add(x,p)
    # Preserve platform identity for files returned from this generation.
    # Do not relabel these paths as generic merely because they also live in the
    # output directory; duplicate discoveries are ignored by add().
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
    # Optional vision-model inspection of the actual rendered images and sampled video frames.
    # Failures are recorded but never prevent a safe generation/publish.
    vision=_vision_review(images,videos,content)
    vision_recs=_apply_vision_review(vision,images,videos) if vision.get("status")=="ok" else []
    recs=[]
    for x in images+videos+copy_audit:
        for rec in x.get("recommendations",[]):
            if rec not in recs:recs.append(rec)
    for rec in vision_recs:
        if rec not in recs:recs.append(rec)
    row={"ts":datetime.datetime.now(datetime.timezone.utc).isoformat(),"day_number":day_number,"generation_id":generation_id,
         "image_assets":images,"video_assets":videos,"copy_audit":copy_audit,"vision_audit":vision,
         "portfolio_diversity":diversity,"recommendations":recs[:30],
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
    semantic_directives=set()
    for row in rows:
        va=row.get("vision_audit") or {}
        by_platform=va.get("_renderer_directives") or {}
        for recorded_platform, directives in by_platform.items():
            if platform and platform not in str(recorded_platform) and str(recorded_platform) not in {"generated_image","video"}:
                continue
            semantic_directives.update(d for d in directives if isinstance(d,str))
    return {
        "boost_exposure": "boost_exposure" in semantic_directives or any("exposure" in r or "near-black" in r or "consistently dark" in r for r in active),
        "boost_contrast": "boost_contrast" in semantic_directives or any("contrast" in r for r in active),
        "add_action_texture": "add_action_texture" in semantic_directives or any("action/texture" in r or "steam" in r for r in active),
        "break_centered_catalog": "break_centered_catalog" in semantic_directives or any("lower-center focal composition dominates" in r for r in active),
        "boost_upper_activity": "boost_upper_activity" in semantic_directives or any("upper safe zone" in r or "first-frame visual hook" in r for r in active),
        "boost_motion": "boost_motion" in semantic_directives or any("visually static" in r or "motion change" in r for r in active),
        "diversify_palette": "diversify_palette" in semantic_directives or any("diversity low" in r for r in active),
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

