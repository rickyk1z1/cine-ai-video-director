#!/usr/bin/env python3
"""Explicit deterministic contact-sheet composition/extraction; never AI image repair."""
import argparse
import json
from pathlib import Path

def run(mode,spec,output):
    from PIL import Image, ImageOps
    out=Path(output)
    if out.exists():raise ValueError('输出目录已存在，请使用新版本目录')
    cells=spec['cells']
    if not cells or len({c['shot_id'] for c in cells})!=len(cells):raise ValueError('画格须有唯一镜头ID')
    prepared=[]
    if mode=='compose':
        cols=spec['columns']; w,h=spec['cell_size']
        if type(cols) is not int or cols<1 or min(w,h)<1:raise ValueError('无效布局')
        for c in cells:
            with Image.open(c['path']) as im:prepared.append(ImageOps.contain(im.convert('RGB'),(w,h)))
        rows=(len(cells)+cols-1)//cols
        board=Image.new('RGB',(cols*w,rows*h),'white')
        for i,im in enumerate(prepared):
            x=(i%cols)*w;y=(i//cols)*h
            board.paste(im,(x+(w-im.width)//2,y+(h-im.height)//2))
            cells[i]['box']=[x,y,x+w,y+h]
        out.mkdir(parents=True);board.save(out/'组图.png')
    else:
        with Image.open(spec['path']) as source:
            source=source.convert('RGB')
            for c in cells:
                box=c['box']
                if len(box)!=4 or any(type(v) is not int for v in box) or not (0<=box[0]<box[2]<=source.width and 0<=box[1]<box[3]<=source.height):raise ValueError('裁切范围无效')
                prepared.append(source.crop(box))
        out.mkdir(parents=True)
    for i,im in enumerate(prepared):
        name=f'{i+1:02d}.png';im.save(out/name);cells[i]['output']=name
    (out/'画格对应.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    return str(out)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=['compose','extract']);ap.add_argument('--input',required=True);ap.add_argument('--output',required=True)
    a=ap.parse_args()
    try:print(run(a.mode,json.loads(Path(a.input).read_text()),a.output))
    except ImportError:ap.exit(1,'需要Pillow；使用已有含Pillow的Python环境，不自动安装。\n')
    except (ValueError,KeyError,OSError) as e:ap.exit(1,str(e)+'\n')
