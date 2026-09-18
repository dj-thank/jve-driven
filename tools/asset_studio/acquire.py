"""Acquire reviewed public assets, not a complete city or driving benchmark.

Powered by Poly Haven. Source models/textures are CC0; their API has separate
attribution and client-identification terms. No credentials or paid services.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HOSTS = {'api.polyhaven.com', 'dl.polyhaven.org', 'casual-effects.com',
         'raw.githubusercontent.com'}
LIMIT = 650_000_000
PER_FILE = 250_000_000
USER_AGENT = 'JveDriven-AssetStudio/0.7 (Powered by Poly Haven)'


def safe_path(root, relative):
    relative = str(relative).replace('\\', '/')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or ':' in relative:
        raise ValueError('Unsafe asset path')
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Asset escaped output directory')
    return target


def safe_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
        raise ValueError('Unapproved download host')
    return url


class ApprovedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class Store:
    def __init__(self, root):
        self.root = root.resolve(); self.root.mkdir(parents=True, exist_ok=False)
        self.records = []; self.used = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ApprovedRedirect())

    def fetch(self, url, relative, expected=None):
        safe_url(url)
        target = safe_path(self.root, relative)
        request = urllib.request.Request(url, headers={'User-Agent':USER_AGENT})
        with self.opener.open(request, timeout=60) as response:
            declared = int(response.headers.get('Content-Length', 0))
            if declared > min(PER_FILE, LIMIT-self.used):
                raise ValueError('Asset exceeds download budget')
            chunks = []; size = 0
            while chunk := response.read(1024*1024):
                size += len(chunk); self.used += len(chunk)
                if size > PER_FILE or self.used > LIMIT:
                    raise ValueError('Download budget exhausted')
                chunks.append(chunk)
            data = b''.join(chunks)
        if not data:
            raise ValueError('Empty asset')
        if expected:
            if expected.get('size') is not None and len(data) != expected['size']:
                raise ValueError('Publisher size mismatch')
            if expected.get('md5') and hashlib.md5(data).hexdigest() != expected['md5']:
                raise ValueError('Publisher checksum mismatch')
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        record = {'url':url,'path':target.relative_to(self.root).as_posix(),
                  'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                  'publisher_md5_checked':bool(expected and expected.get('md5')),
                  'downloaded_utc':datetime.now(timezone.utc).isoformat()}
        self.records.append(record); self.save()
        return data

    def save(self):
        (self.root/'download-lock.json').write_text(json.dumps({'schema':'asset-studio.downloads.v1',
            'resources':self.records,'bytes':self.used,'checksums_are_not_signatures':True},indent=2),encoding='utf8')

    def json(self, url, relative):
        return json.loads(self.fetch(url,relative))


def poly_model(store, name):
    catalogue = store.json('https://api.polyhaven.com/files/'+name, f'metadata/{name}.json')
    root = catalogue.get('gltf', {})
    resolution = '2k' if '2k' in root else '1k'
    entry = root[resolution]['gltf']
    store.fetch(entry['url'],f'{name}/{name}.gltf',entry)
    for path, resource in entry.get('include', {}).items():
        store.fetch(resource['url'],f'{name}/{path}',resource)
    return {'id':name,'kind':'model','license':'CC0-1.0',
            'source':'https://polyhaven.com/a/'+name,'resolution':resolution,
            'entrypoint':f'{name}/{name}.gltf','imported':False}


def poly_texture(store, name):
    catalogue = store.json('https://api.polyhaven.com/files/'+name,f'metadata/{name}.json')
    maps = {}
    for role in ('Diffuse','nor_gl','Rough'):
        entry = catalogue[role]['2k']['jpg']
        relative=f'{name}/{role}.jpg'; store.fetch(entry['url'],relative,entry); maps[role]=relative
    return {'id':name,'kind':'material','license':'CC0-1.0',
            'source':'https://polyhaven.com/a/'+name,'maps':maps,'imported':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();store=Store(args.out);results=[];failures=[]
    def task(name, work):
        try:
            result=work();results.append(result);print('ACQUIRED',name,json.dumps(result),flush=True)
        except Exception as exc:
            failures.append({'id':name,'error_type':type(exc).__name__,'message':str(exc)[:500]})
            print('FAILED',name,type(exc).__name__,str(exc)[:200],flush=True)
    def bmw():
        url='https://casual-effects.com/g3d/data10/research/model/bmw/bmw.zip'
        store.fetch(url,'bmw/bmw.zip')
        with zipfile.ZipFile(store.root/'bmw/bmw.zip') as archive:
            if sum(i.file_size for i in archive.infolist())>200_000_000:
                raise ValueError('Unpacked car exceeds budget')
            names=archive.namelist()
            for member in archive.infolist():
                if member.is_dir():continue
                target=safe_path(store.root/'bmw/source',member.filename)
                if target.suffix.lower() not in {'.obj','.mtl','.png','.jpg','.jpeg','.txt','.md','.any'}:
                    continue
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(member))
        return {'id':'bmw','kind':'model','license':'CC0/Public Domain',
                'authors':['Mike Pan','Morgan McGuire'],
                'source':'https://casual-effects.com/g3d/data10/',
                'archive_url':url,'archive_files':names,'imported':False}
    task('bmw',bmw)
    for name in ('tree_small_02','modular_street_seating','potted_plant_02'):
        task(name,lambda name=name:poly_model(store,name))
    for name in ('pavement_01','pavement_05'):
        task(name,lambda name=name:poly_texture(store,name))
    def sky():
        name='kloofendal_48d_partly_cloudy_puresky'
        doc=store.json('https://api.polyhaven.com/files/'+name,f'metadata/{name}.json')
        item=doc['hdri']['2k']['hdr'];store.fetch(item['url'],'sky/sky.hdr',item)
        return {'id':name,'kind':'hdri','license':'CC0-1.0','entrypoint':'sky/sky.hdr',
                'source':'https://polyhaven.com/a/'+name,'imported':False}
    task('sky',sky)
    # Official catalogue used for subsequent human-reviewed choices, not blind bulk import.
    def inventory():
        doc=store.json('https://api.polyhaven.com/assets?t=models','metadata/model-catalogue.json')
        chosen={k:v for k,v in doc.items() if re.search(r'bench|tree|chair|sofa|plant|bin|lamp|car|planter',k,re.I)}
        (store.root/'model-candidates.json').write_text(json.dumps(chosen,indent=2),encoding='utf8')
        return {'id':'catalogue','kind':'metadata','candidates':len(chosen),'imported':False}
    task('inventory',inventory)
    report={'schema':'asset-studio.acquisition.v1','results':results,'failures':failures,
            'total_download_bytes':store.used,'paid_purchases':0,'api_inference_calls':0,
            'runtime':'GitHub Actions public-asset acquisition, not user PC',
            'asset_credit':'Powered by Poly Haven; BMW model Mike Pan and Morgan McGuire, Computer Graphics Archive, July 2017.'}
    (store.root/'acquisition.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    store.save();print(json.dumps(report,indent=2),flush=True)
    return 0 if not failures else 2


if __name__=='__main__':raise SystemExit(main())
