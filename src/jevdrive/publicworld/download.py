"""Bounded unauthenticated downloads with content hashes and offline verification."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse,urljoin
import httpx

ALLOWED_HOSTS={
 'api.plateauview.mlit.go.jp','tile.plateauview.mlit.go.jp',
 'assets.cms.plateau.reearth.io','assets.plateauview.mlit.go.jp',
 'cyberjapandata.gsi.go.jp','api.openstreetmap.org',
}

def validate_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ALLOWED_HOSTS or p.port not in (None,443) or p.username or p.password or p.fragment:
        raise ValueError(f'Unapproved public data URL: {p.scheme}://{p.hostname}')
    if p.query and p.hostname!='api.openstreetmap.org':
        # Known imagery/terrain parameters are harmless; never accept credentials.
        from urllib.parse import parse_qs
        if not set(parse_qs(p.query)) <= {'v','version','format','extensions'}:
            raise ValueError('Unexpected query parameters on a public data request')
    return url


def sha256(data): return hashlib.sha256(data).hexdigest()

class DownloadStore:
    def __init__(self,root:Path,max_bytes=350_000_000,max_files=500,client=None,*,resume=False):
        if not 1<=max_bytes<=2_000_000_000 or not 1<=max_files<=5000:
            raise ValueError('Download budget out of permitted range')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.max_bytes=max_bytes;self.max_files=max_files;self.used=0;self.records={}
        if resume and (self.root/'download-lock.json').exists():
            verify_lock(self.root)
            lock=json.loads((self.root/'download-lock.json').read_text(encoding='utf8'))
            self.records={r['url']:r for r in lock['resources']}
            self.used=sum(r['bytes'] for r in self.records.values())
            if self.used>self.max_bytes or len(self.records)>self.max_files:
                raise ValueError('Resume exceeds configured download budget')
        # No user API key, cookies, or environment auth is sent to data hosts.
        self.client=client or httpx.Client(timeout=30,trust_env=False,follow_redirects=False,
              headers={'User-Agent':'JevDriveLab-public-data/0.2','Accept':'*/*'})
        self.owns_client=client is None

    def close(self):
        if self.owns_client: self.client.close()

    def fetch(self,url,kind='asset'):
        validate_url(url)
        if url in self.records:
            r=self.records[url]
            data=(self.root/r['path']).read_bytes()
            if sha256(data)!=r['sha256']: raise RuntimeError('Cached file checksum mismatch')
            return data,r
        if len(self.records)>=self.max_files: raise RuntimeError('Download file budget exhausted')
        target=url;redirects=[]
        for _ in range(6):
            validate_url(target)
            with self.client.stream('GET',target) as response:
                if response.status_code in (301,302,303,307,308):
                    target=urljoin(target,response.headers['location']);redirects.append(target);continue
                response.raise_for_status()
                declared=response.headers.get('content-length')
                if declared and int(declared)>self.max_bytes-self.used:
                    raise RuntimeError('Content-Length exceeds remaining byte budget')
                chunks=[]
                for chunk in response.iter_bytes():
                    self.used+=len(chunk)
                    if self.used>self.max_bytes: raise RuntimeError('Download byte budget exhausted')
                    chunks.append(chunk)
                data=b''.join(chunks)
                if not data: raise RuntimeError('Empty public asset')
                digest=sha256(data)
                path=Path('raw')/(sha256(url.encode())[:20]+'.bin')
                (self.root/path).parent.mkdir(parents=True,exist_ok=True)
                (self.root/path).write_bytes(data)
                record={'url':url,'resolved_url':target,'redirects':redirects,'path':path.as_posix(),
                        'sha256':digest,'bytes':len(data),'kind':kind,
                        'fetched_utc':datetime.now(timezone.utc).isoformat(),
                        'etag':response.headers.get('etag'),'last_modified':response.headers.get('last-modified')}
                self.records[url]=record
                self.save()
                return data,record
        raise RuntimeError('Too many redirects')

    def json(self,url,kind='metadata'):
        data,record=self.fetch(url,kind)
        if len(data)>32_000_000: raise ValueError('Metadata exceeds 32 MB')
        return json.loads(data),record

    def save(self):
        (self.root/'download-lock.json').write_text(json.dumps({'schema':'jevdrive.download-lock.v1',
              'resources':list(self.records.values())},indent=2),encoding='utf8')


def verify_lock(root:Path):
    root=Path(root).resolve()
    data=json.loads((root/'download-lock.json').read_text())
    seen_urls=set();seen_paths=set()
    for r in data['resources']:
        p=(root/r['path']).resolve()
        if not p.is_relative_to(root): raise ValueError('Path outside snapshot')
        if r.get('url') in seen_urls or r['path'] in seen_paths:
            raise ValueError('Duplicate snapshot resource')
        seen_urls.add(r.get('url'));seen_paths.add(r['path'])
        if not p.is_file() or p.stat().st_size!=r['bytes'] or sha256(p.read_bytes())!=r['sha256']:
            raise RuntimeError(f'Bad or missing snapshot asset: {r["path"]}')
    return len(data['resources'])
