import os,shutil,glob,json
from PIL import Image
A='/home/box/agent-data/agents/4f2065d4-8340-4296-a443-fcb7c30b214b/attachments/'
L=[ # key, sku, size, type, name, bbox(None=auto), baked_copy, text_zone, blocked
('f6614e37','bold','100g','cutout','front',None,False,None,False),
('72dc58f7','bold','100g','infographic','hot_cold',(0.38,0.47,0.63,0.99),True,None,False),
('3461f782','bold','100g','lifestyle','cafe_barista',(0.29,0.38,0.51,0.88),True,'top',False),
('ad24c529','bold','100g','infographic','badges_kitchen',(0.26,0.30,0.46,0.88),True,None,False),
('a576a816','bold','50g','cutout','front',None,False,None,False),
('41b963e6','bold','50g','infographic','badges_window',(0.36,0.36,0.64,0.66),True,None,False),
('caee1cb0','purica','100g','lifestyle','sip_pure',(0.35,0.27,0.66,0.90),True,None,False),
('973e809f','purica','50g','cutout','front',None,False,None,False),
('a66d499a','purica','50g','infographic','true_coffee_lovers',(0.36,0.34,0.66,0.92),True,None,False),
('24454fb0','purica','50g','back','back',None,False,None,False),
('ef13d680','purica','100g','infographic','why_purica_wide',(0.62,0.12,0.80,0.80),True,None,False),
('5d3b2f94','purica','100g','cutout','front',None,False,None,False),
('7a105c69','purista','100g','infographic','hot_cold',(0.36,0.47,0.62,0.99),True,None,False),
('ba2ffed8','purista','50g','cutout','front',None,False,None,False),
('57a4bbc5','purista','100g','infographic','real_coffee_lovers',(0.43,0.22,0.78,0.80),True,None,False),
('32d68e70','purista','50g','back','back',None,False,None,False),
('35e8e906','purista','50g','infographic','purista_wide',(0.45,0.10,0.75,0.85),True,None,False),
('83044509','purista','100g','cutout','front',None,False,None,False),
('704458f8','ultra_blend','100g','lifestyle','awaken_valley',(0.08,0.40,0.34,0.97),True,'top',False),
('52d564c5','ultra_blend','50g','cutout','front',None,False,None,False),
('6bd22512','ultra_blend','100g','infographic','true_coffee_lovers',(0.36,0.30,0.64,0.95),True,None,True),
('bdb6317b','ultra_blend','50g','back','back',None,False,None,False),
('5cde8569','ultra_blend','50g','lifestyle','roastery_hero',(0.20,0.05,0.78,0.99),False,'right',False),
('d136b2f2','ultra_blend','100g','cutout','front',None,False,None,False),
]
TEXT={'3461f782':[[0.48,0.32,1.0,0.53]],'caee1cb0':[[0.02,0.04,0.42,0.33]],'704458f8':[[0.36,0.31,0.97,0.60]]}
SURF={'cutout':['studio_card','ig_post','ig_story','carousel_cover','carousel_middle','carousel_cta','fb','threads','linkedin','reel_thumb','yt_thumb','blog'],
 'back':['carousel_detail','blog'],
 'lifestyle':['ig_post','ig_story','carousel_cover','carousel_cta','fb','threads','linkedin','reel_thumb','yt_thumb','blog'],
 'infographic':['ig_post','carousel_cover','carousel_middle','fb','linkedin','threads','blog']}
def auto(im):
  g=im.convert('L').point(lambda v:255 if v<235 else 0);b=g.getbbox();w,h=im.size
  return tuple(round(x,3) for x in (b[0]/w,b[1]/h,b[2]/w,b[3]/h))
items=[]
for k,sku,size,t,n,bb,baked,tz,blk in L:
  src=glob.glob(A+k+'*.png')[0];d=f'brand_assets/approved_photos/{sku}';os.makedirs(d,exist_ok=True)
  fn=f'{sku}_{size}_{t}_{n}.png';shutil.copy(src,f'{d}/{fn}');im=Image.open(src)
  it=dict(file=f'{sku}/{fn}',sku=sku,size=size,type=t,width=im.size[0],height=im.size[1],
    jar_bbox=list(bb or auto(im)),baked_copy=baked,text_zone=tz,
    allowed_surfaces=[] if blk else SURF[t],blocked=blk,
    text_bboxes=TEXT.get(k, [[0,0,1,1]] if t=='infographic' else []))
  if t in ('lifestyle','infographic') and not blk:
    it['blocked']=True;it['allowed_surfaces']=[];it['blocked_reason']='AI render, not realistic (rejected by Hiten 2026-10-14).'
  if sku=='bold' and size=='100g' and t=='cutout':
    it['blocked']=True;it['allowed_surfaces']=[];it['blocked_reason']='Superseded: soft label. Use bold_100g_cutout_hires (from Hiten approved card).'
  if sku=='bold' and size=='50g' and t=='cutout':
    it['blocked']=True;it['allowed_surfaces']=[];it['blocked_reason']='Superseded: soft, oversaturated label. Use bold_100g_cutout_wide_hires.'
  if blk: it['blocked_reason']="Copy says 'Purica isn't just instant coffee' and 'Agglomerated' on an Ultra Blend (70/30 chicory) creative - wrong SKU copy."
  items.append(it)
# Hiten's own approved Bold story card (2026-10-14) + hi-res cutout extracted from it
items.insert(0, dict(file='bold/bold_100g_cutout_hires.png', alpha_file='bold/bold_100g_cutout_hires_alpha.png',
  sku='bold', size='100g', type='cutout', width=737, height=1280, jar_bbox=[0.175,0.032,0.817,0.936],
  baked_copy=False, text_zone=None, allowed_surfaces=SURF['cutout'], blocked=False, text_bboxes=[], primary=False,
  source='extracted from bold_100g_approved_card_story.png (cream bg normalised to white; alpha version has no halo)'))
items.insert(0, dict(file='bold/bold_100g_cutout_wide_hires.png', sku='bold', size='100g', type='cutout',
  width=1198, height=1313, jar_bbox=[0.179,0.002,0.846,0.999], baked_copy=False, text_zone=None,
  allowed_surfaces=SURF['cutout'], blocked=False, text_bboxes=[], primary=True,
  source='Hiten Jain hi-res render on white, 2026-10-14 (label: NET WEIGHT : 100 GM)'))
items.insert(0, dict(file='bold/bold_100g_approved_card_story.png', sku='bold', size='100g', type='approved_card',
  width=941, height=1672, jar_bbox=[0.25,0.215,0.75,0.94], baked_copy=True, text_zone=None,
  allowed_surfaces=['ig_story','reel_thumb'], blocked=False, text_bboxes=[[0.1,0.03,0.9,0.19],[0.15,0.94,0.85,0.985]],
  use_as_is=True, aspect='9:16', source='Hiten Jain, 2026-10-14'))
json.dump(dict(version=1,source='Official photos supplied by Hiten Jain, 2026-10-14',
 rules=dict(approved_card='founder-made finished card; used as-is (resize only) on its aspect',lifestyle='use as-is; crop/resize only; jar_bbox must stay fully in frame; overlay only in text_zone (never over baked copy)',
  text_bboxes='baked-in copy; crop must keep all of it; overlays never touch it',cutout='only on clean plain brand-colour / soft paper cards with a subtle floor shadow; never composited into scenes or with props',real_photo='drop real (non-AI) photos in <sku>/real/ - they take priority over cutouts automatically; optional <name>.json sidecar with jar_bbox',tone='global-only correction (whole image), no local grading',
  infographic='use as-is; no extra overlay (baked copy)',blocked='never used'),
 handle='@purepantryprovisions',cta='Follow @purepantryprovisions + shop p3online.in',items=items),
 open('brand_assets/approved_photos/manifest.json','w'),indent=1)
# verification sheet
from PIL import ImageDraw
S=Image.new('RGB',(6*300,4*300),'gray')
for i,it in enumerate(items):
  im=Image.open('brand_assets/approved_photos/'+it['file']).convert('RGB');w,h=im.size;d=ImageDraw.Draw(im)
  x0,y0,x1,y1=it['jar_bbox'];d.rectangle((x0*w,y0*h,x1*w,y1*h),outline='red',width=8);im.thumbnail((295,295));S.paste(im,(i%6*300,i//6*300))
S.save('/workspace/bbox.jpg')
