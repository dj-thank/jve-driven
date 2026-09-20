"""Save the official catalogue, bounded and without any authentication."""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import httpx

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists(): raise FileExistsError('Choose a new catalogue snapshot')
url='https://api.plateauview.mlit.go.jp/datacatalog/plateau-datasets'
with httpx.Client(timeout=30,trust_env=False,follow_redirects=False) as client:
    with client.stream('GET',url) as response:
        response.raise_for_status(); data=bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data)>16_000_000: raise ValueError('Catalogue exceeds 16 MB limit')
parsed=json.loads(data)
if not isinstance(parsed,dict) or not isinstance(parsed.get('datasets'),list):
    raise ValueError('Unsupported catalogue schema')
a.out.parent.mkdir(parents=True,exist_ok=True)
a.out.write_bytes(data)
a.out.with_suffix('.provenance.json').write_text(json.dumps({
    'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
    'fetched_utc':datetime.now(timezone.utc).isoformat()},indent=2),encoding='utf8')
print('Catalogue saved:',len(data),'bytes')
