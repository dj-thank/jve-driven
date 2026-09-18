"""Pure asset validation: change detection, not authorship or fidelity certification."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path,PurePosixPath

FONT_SUFFIXES={'.ttf','.otf','.ttc','.woff','.woff2','.pfb','.pfa','.fnt','.bdf','.pcf'}


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def resolve_inside(root,relative):
    root=Path(root).resolve();s=str(relative).replace('\\','/');p=PurePosixPath(s)
    if not s or p.is_absolute() or '..' in p.parts or ':' in s:raise ValueError('Unsafe relative asset path')
    result=(root/s).resolve()
    if not result.is_relative_to(root):raise ValueError('Asset outside source root')
    return result


def verify_downloads(root):
    root=Path(root);data=json.loads((root/'download-lock.json').read_text(encoding='utf8'))
    rows=data.get('resources');seen=set()
    if not isinstance(rows,list) or not rows:raise ValueError('Empty download evidence')
    for row in rows:
        path=resolve_inside(root,row['path'])
        if path in seen:raise ValueError('Duplicate source file')
        seen.add(path)
        if type(row['bytes']) is not int or row['bytes']<=0:raise ValueError('Invalid source size')
        if not path.is_file() or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise ValueError('Source checksum or size differs')
    return len(rows)


def finite_bounds(lo,hi):
    if len(lo)!=3 or len(hi)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in [*lo,*hi]):
        raise ValueError('Invalid bounds')
    if any(b<a for a,b in zip(lo,hi)) or max(b-a for a,b in zip(lo,hi))<1e-8:
        raise ValueError('Empty or reversed bounds')
    return [b-a for a,b in zip(lo,hi)]


def assert_dimensions(lo,hi,kind):
    extent=finite_bounds(lo,hi)
    limits={'car':((1.4,2.4),(3.5,5.8),(1.0,2.1)),
            'person':((.25,1.7),(.15,.9),(1.4,2.1)),
            'tree':((1,10),(1,10),(3,8)),
            'bench':((1,3.5),(.3,1.1),(.35,1.4)),
            'plant':((.15,1.8),(.15,1.8),(.3,2.0))}
    if kind not in limits:raise ValueError('Unknown asset class')
    if any(not a<=x<=b for x,(a,b) in zip(extent,limits[kind])):
        raise ValueError(f'{kind} extent is implausible: {extent}')
    if abs(lo[2])>.015:raise ValueError('Asset does not rest at local ground')
    return extent


def wheel_roll(distance,radius):
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (distance,radius)) or not .15<=radius<=.6:
        raise ValueError('Invalid wheel travel/radius')
    return -distance/radius


def frame_clock(count,fps):
    if type(count) is not int or not 1<=count<=900 or type(fps) is not int or not 1<=fps<=60:
        raise ValueError('Invalid frame schedule')
    return [{'frame':i+1,'time_s':i/fps} for i in range(count)]


def assert_font_free(root):
    bad=[p.name for p in Path(root).rglob('*') if p.is_file() and p.suffix.lower() in FONT_SUFFIXES]
    if bad:raise ValueError('Font files must not be distributed')
    return True
