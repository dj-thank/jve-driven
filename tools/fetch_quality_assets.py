"""Fetch a bounded CC0 appearance pack; never replaces geographic evidence."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx

BUDGET = 160_000_000
HOSTS = {'api.polyhaven.com', 'dl.polyhaven.org'}

def validate_url(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password:
        raise ValueError('Only official public Poly Haven hosts are allowed')
    return url

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root/'asset-lock.json').exists():
        raise FileExistsError('Asset lock exists; reuse it or select a new directory')
    records = []; used = 0
    client = httpx.Client(timeout=45, trust_env=False, follow_redirects=False)
    def fetch(url, relative, expected=None):
        nonlocal used
        path = (root/relative).resolve()
        if not path.is_relative_to(root): raise ValueError('Asset path outside pack')
        with client.stream('GET', validate_url(url)) as response:
            response.raise_for_status(); chunks = []
            for chunk in response.iter_bytes():
                used += len(chunk)
                if used > BUDGET: raise RuntimeError('Asset pack exceeds 160 MB')
                chunks.append(chunk)
        data = b''.join(chunks)
        if expected and (len(data) != expected['size'] or
                hashlib.md5(data).hexdigest() != expected['md5']):
            raise ValueError('Provider size/checksum mismatch')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix+'.tmp')
        temporary.write_bytes(data); temporary.replace(path)
        records.append({'path':path.relative_to(root).as_posix(), 'url':url,
                        'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()})
        print('ASSET', relative, len(data), flush=True)
        return data
    specifications = {}
    try:
        for asset in ('kloofendal_48d_partly_cloudy_puresky','pavement_01','tree_small_02'):
            specifications[asset] = json.loads(fetch(
                'https://api.polyhaven.com/files/'+asset, 'metadata/'+asset+'.json'))
        sky = specifications['kloofendal_48d_partly_cloudy_puresky']['hdri']['2k']['hdr']
        fetch(sky['url'], 'sky.hdr', sky)
        for name, channel in [('paving_normal','nor_gl'),('paving_roughness','Rough'),('paving_albedo','Diffuse')]:
            spec = specifications['pavement_01'][channel]['2k']['jpg']
            fetch(spec['url'], name+'.jpg', spec)
        spec = specifications['tree_small_02']['gltf']['1k']['gltf']
        fetch(spec['url'], 'tree/tree.gltf', spec)
        for relative, item in spec.get('include',{}).items():
            fetch(item['url'], 'tree/'+relative, item)
        manifest = {'schema':'jevdrive.appearance-assets.v1', 'license':'CC0-1.0',
            'license_url':'https://polyhaven.com/license',
            'acquired_utc':datetime.now(timezone.utc).isoformat(),
            'resources':records, 'bytes':used,
            'sky':'sky.hdr', 'normal':'paving_normal.jpg',
            'roughness':'paving_roughness.jpg', 'albedo':'paving_albedo.jpg', 'tree':'tree/tree.gltf',
            'paving_repeat_m':1.5,
            'not_tokyo_measurements':True,
            'roles':{'sky':'artistic lighting, not measured Tokyo weather',
                     'paving':'optional generic microdetail; source colour preserved',
                     'tree':'generic species/shape; OSM positions remain separate'}}
        (root/'asset-lock.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        print('COMPLETE', used, 'bytes', len(records), 'resources')
    finally:
        client.close()

if __name__ == '__main__':
    main()
