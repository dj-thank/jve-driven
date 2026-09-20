"""Download bounded, attributable CC0 assets through the providers' public interfaces.
Powered by Poly Haven. No API keys, purchase, scraping, or dataset-license acceptance.
"""
from __future__ import annotations
import argparse,hashlib,io,json,stat,zipfile
from pathlib import Path
from urllib.parse import urlsplit,unquote
import httpx

HOSTS={'api.polyhaven.com','dl.polyhaven.org','casual-effects.com'}
CAP=450_000_000

def sha(data): return hashlib.sha256(data).hexdigest()

class Acquisition:
    def __init__(self,out):
        self.root=Path(out)
        if self.root.exists():raise FileExistsError('Use a new acquisition directory')
        self.root.mkdir(parents=True);self.rows=[];self.used=0
        self.client=httpx.Client(timeout=60,follow_redirects=False,trust_env=False,headers={'User-Agent':'JveHeroAssets/0.7 Powered by Poly Haven'})
    def fetch(self,url,relative,expected=None):
        p=urlsplit(url);target=(self.root/relative).resolve()
        if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.query or p.fragment:raise ValueError('Unapproved source URL')
        if not target.is_relative_to(self.root.resolve()):raise ValueError('Asset path escaped pack')
        content=bytearray()
        with self.client.stream('GET',url) as response:
            response.raise_for_status()
            if response.is_redirect:raise ValueError('Unexpected asset redirect')
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content)>200_000_000 or self.used+len(content)>CAP:raise ValueError('Asset byte budget exceeded')
        data=bytes(content)
        if not data:raise ValueError('Empty asset')
        if expected and (len(data)!=expected['size'] or hashlib.md5(data).hexdigest()!=expected['md5']):raise ValueError('Provider checksum or size mismatch')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        self.used+=len(data);self.rows.append({'url':url,'path':target.relative_to(self.root.resolve()).as_posix(),'bytes':len(data),'sha256':sha(data),'provider_md5_verified':bool(expected)})
        self.save();return data
    def save(self):
        (self.root/'download-lock.json').write_text(json.dumps({'schema':'jevdrive.hero-source-lock.v1','api_credit':'Powered by Poly Haven','resources':self.rows,'bytes':self.used},indent=2),encoding='utf8')
    def model(self,ident,res):
        data=self.fetch('https://api.polyhaven.com/files/'+ident,'metadata/'+ident+'.json');meta=json.loads(data)
        info=meta['blend'][res]['blend'];name=unquote(urlsplit(info['url']).path).split('/')[-1]
        self.fetch(info['url'],ident+'/'+name,info)
        for path,entry in info.get('include',{}).items():self.fetch(entry['url'],ident+'/'+path,entry)
    def surface(self,ident):
        meta=json.loads(self.fetch('https://api.polyhaven.com/files/'+ident,'metadata/'+ident+'.json'))
        for role in ['Diffuse','nor_gl','Rough']:
            info=meta[role]['2k']['jpg'];self.fetch(info['url'],ident+'/'+role+'.jpg',info)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    acq=Acquisition(args.out)
    try:
        info=acq.fetch('https://casual-effects.com/g3d/data10/research/model/bmw/info.js','bmw/publisher-info.js').decode()
        if 'CC0/Public Domain' not in info:raise ValueError('Car license statement changed')
        data=acq.fetch('https://casual-effects.com/g3d/data10/research/model/bmw/bmw.zip','bmw/bmw.zip')
        derived=[]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist())>200_000_000:raise ValueError('Expanded model budget exceeded')
            for item in archive.infolist():
                path=(args.out/'bmw'/item.filename).resolve()
                if not path.is_relative_to((args.out/'bmw').resolve()) or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe model archive member')
                if item.is_dir():continue
                if path.suffix.lower() not in {'.obj','.mtl','.txt'}:raise ValueError('Unexpected model payload')
                content=archive.read(item);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
                derived.append({'path':path.relative_to(args.out.resolve()).as_posix(),'bytes':len(content),'sha256':sha(content)})
        (args.out/'extracted-lock.json').write_text(json.dumps({'archive_sha256':sha(data),'resources':derived},indent=2),encoding='utf8')
        for ident,res in [('tree_small_02','1k'),('modular_street_seating','2k'),('fern_02','2k')]:
            acq.model(ident,res);print('ACQUIRED',ident,flush=True)
        for ident in ['granite_tile_02','marble_01']:acq.surface(ident)
        (args.out/'SOURCES.txt').write_text('Powered by Poly Haven\nTree Small 02, Modular Street Seating, Fern 02, Granite Tile 02, Marble 01: Poly Haven / CC0-1.0.\nhttps://polyhaven.com/license\nBMW source: Mike Pan and Morgan McGuire / CC0, McGuire Computer Graphics Archive.\nhttps://casual-effects.com/g3d/data10/research/model/bmw/info.js\nVehicle finishes, normalization, badge removal, bench assembly and planter geometry are authored modifications.\nNo endorsement by a vehicle manufacturer. Do not confuse a CC0 copyright license with trademark rights.\nNo human scan data was acquired; the Renderpeople candidate was not used because the reviewed product excludes ML/CV research under its standard terms.\n',encoding='utf8')
        print(json.dumps({'resources':len(acq.rows),'download_bytes':acq.used,'success':True}))
    finally:acq.save();acq.client.close()

if __name__=='__main__':main()
