#!/usr/bin/env python3
"""Grid observations and aligned binary-mask differences; never infer 3D truth."""
import argparse, hashlib, json, math
from pathlib import Path

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p, data):
    with Path(p).open('x') as f: json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)

def grid(image, out, rows=3, columns=3, pixel_step=None):
    from PIL import Image, ImageDraw
    if not 1 <= rows <= 20 or not 1 <= columns <= 20: raise ValueError('grid range 1..20')
    out=Path(out);out.mkdir(exist_ok=False,parents=True)
    with Image.open(image) as original: im=original.convert('RGB')
    w,h=im.size; d=ImageDraw.Draw(im);cells=[]
    if pixel_step is not None:
        if type(pixel_step)!=int or not 8<=pixel_step<=1024:raise ValueError('pixel step must be 8..1024')
        for x in range(0,w,pixel_step):d.line([(x,0),(x,h)],fill=(150,70,70));d.text((x+2,2),str(x),fill='red')
        for y in range(0,h,pixel_step):d.line([(0,y),(w,y)],fill=(150,70,70));d.text((2,y+2),str(y),fill='red')
    for r in range(0 if pixel_step is not None else rows):
        for c in range(columns):
            box=[round(c*w/columns),round(r*h/rows),round((c+1)*w/columns),round((r+1)*h/rows)]
            ident=f'r{r+1}c{c+1}'; d.rectangle(box,outline='red',width=2);d.text((box[0]+5,box[1]+5),ident,fill='red')
            cells.append({'id':ident,'roi_xyxy':box,'features':[],'review':'pending'})
    im.save(out/'grid.png');write(out/'grid.json',{'source':str(Path(image).resolve()),'sha256':sha(image),'size':[w,h],'grid_kind':'pixel' if pixel_step is not None else 'coverage','pixel_step':pixel_step,'image':{'path':'grid.png','sha256':sha(out/'grid.png')},'cells':cells,'note':'Coverage grid only; not topology, segmentation or 3D geometry.'})

def verify_alignment(reference,candidate,alignment):
    a=json.loads(Path(alignment).read_text())
    for key,p in [('reference_mask_sha256',reference),('candidate_mask_sha256',candidate)]:
        if a.get(key)!=sha(p): raise ValueError('alignment mask identity mismatch')
    if a.get('status')!='validated' or not a.get('camera') or not a.get('model_sha256'): raise ValueError('validated camera and model identity required')
    for key in ['camera','model']:
        f=Path(alignment).parent/a[key]
        if not f.is_file() or sha(f)!=a.get(key+'_sha256'):raise ValueError('stale '+key)
    return a

def diff(reference,candidate,alignment,out):
    from PIL import Image
    a=verify_alignment(reference,candidate,alignment)
    imgs=[]
    for p in [reference,candidate]:
        with Image.open(p) as im:
            if im.mode!='L':raise ValueError('explicit L binary masks required')
            vals=list(im.getdata());size=im.size
        if not set(vals)<={0,255} or len(set(vals))!=2:raise ValueError('mask must contain foreground and background')
        imgs.append((size,vals))
    if imgs[0][0]!=imgs[1][0]:raise ValueError('dimensions differ: never auto warp or resize')
    ref,cur=imgs[0][1],imgs[1][1];red=blue=intersection=0;pixels=[]
    for x,y in zip(ref,cur):
        if y and not x: pixels.append((230,45,45));red+=1
        elif x and not y:pixels.append((35,95,230));blue+=1
        elif x and y:pixels.append((35,175,95));intersection+=1
        else:pixels.append((250,250,250))
    out=Path(out);out.mkdir(exist_ok=False,parents=True);im=Image.new('RGB',imgs[0][0]);im.putdata(pixels);im.save(out/'difference.png')
    result={'claim':'aligned-mask-only','iou':intersection/(intersection+red+blue),'excess_pixels':red,'missing_pixels':blue,'alignment_sha256':sha(alignment),'reference_mask_sha256':sha(reference),'candidate_mask_sha256':sha(candidate),'legend':{'red':'model exceeds reference','blue':'reference missing from model','green':'overlap'},'limitations':['Masks and camera supplied, not inferred','Does not measure interior features, surface curvature or physical accuracy']};
    import os
    def record(p):return {'path':os.path.relpath(Path(p).resolve(),out.resolve()),'sha256':sha(p)}
    result.update(reference_mask=record(reference),candidate_mask=record(candidate),alignment=record(alignment),camera=record(Path(alignment).parent/a['camera']),model=record(Path(alignment).parent/a['model']),image=record(out/'difference.png'))
    write(out/'metrics.json',result);return result

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    g=s.add_parser('grid');g.add_argument('image');g.add_argument('--out',required=True);g.add_argument('--rows',type=int,default=3);g.add_argument('--columns',type=int,default=3);g.add_argument('--pixel-step',type=int)
    d=s.add_parser('diff');d.add_argument('--reference',required=True);d.add_argument('--candidate',required=True);d.add_argument('--alignment',required=True);d.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        if a.command=='grid':grid(a.image,a.out,a.rows,a.columns,a.pixel_step);print('grid-created; observations pending')
        else: print(json.dumps(diff(a.reference,a.candidate,a.alignment,a.out)))
    except (ValueError,OSError,KeyError,ImportError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':main()


def validate_diff(metrics_path):
    """Recompute difference pixels and counts; file hashes alone do not prove a comparison."""
    from PIL import Image
    p=Path(metrics_path);d=json.loads(p.read_text());files={}
    for key in ('reference_mask','candidate_mask','alignment','camera','model','image'):
        item=d[key];q=(p.parent/item['path']).resolve()
        if not q.is_file()or sha(q)!=item['sha256']:raise ValueError('stale difference artifact: '+key)
        files[key]=q
    verify_alignment(files['reference_mask'],files['candidate_mask'],files['alignment'])
    with Image.open(files['reference_mask'])as im:
        if im.mode!='L':raise ValueError('reference mask not L')
        size=im.size;a=list(im.getdata())
    with Image.open(files['candidate_mask'])as im:
        if im.mode!='L'or im.size!=size:raise ValueError('candidate mask dimensions/mode differ')
        b=list(im.getdata())
    if set(a)|set(b)!={0,255}:raise ValueError('explicit binary mask foreground/background required')
    expected=[];red=blue=overlap=0
    for x,y in zip(a,b):
        if y and not x:expected.append((230,45,45));red+=1
        elif x and not y:expected.append((35,95,230));blue+=1
        elif x and y:expected.append((35,175,95));overlap+=1
        else:expected.append((250,250,250))
    with Image.open(files['image'])as im:
        if im.size!=size or list(im.convert('RGB').getdata())!=expected:raise ValueError('difference image does not match masks')
    if d['excess_pixels']!=red or d['missing_pixels']!=blue or abs(d['iou']-overlap/(red+blue+overlap))>1e-12:raise ValueError('difference metrics do not match masks')
    return {'passed':True,'claim':'recomputed aligned-mask-only'}
