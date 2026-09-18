"""Acquire two specific MIT-licensed business avatars, preserving licenses.
The models are not portrayed as scanned people or finished motion synthesis.
"""
from __future__ import annotations
import argparse,hashlib,json,urllib.request,urllib.parse
from pathlib import Path
from acquire import Store,HOSTS

REPO='microsoft/Microsoft-Rocketbox'
TREES={
 'Business_Female_01':'5e0b9102069b337452f13fb670a57a12f7a36bd0',
 'Business_Male_01':'ed3821f2e54a7a6414cd74dc026ca38c777439d1',
}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    HOSTS.add('api.github.com');s=Store(a.out);selected=[]
    base='https://raw.githubusercontent.com/'+REPO+'/master/'
    for name,sha in TREES.items():
        doc=s.json('https://api.github.com/repos/'+REPO+'/git/trees/'+sha+'?recursive=1','metadata/'+name+'.json')
        if doc.get('truncated'):raise ValueError('Incomplete avatar inventory')
        for item in doc['tree']:
            path=item['path']
            if item['type']!='blob':continue
            if not (path.endswith(name+'.fbx') or path.endswith(('_color.tga','_normal.tga','_specular.tga'))):continue
            url=base+'Assets/Avatars/Professions/'+name+'/'+urllib.parse.quote(path)
            data=s.fetch(url,name+'/'+path,{'size':item['size']})
            digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if digest!=item['sha']:raise ValueError('Avatar changed from reviewed Git blob')
            selected.append({'path':name+'/'+path,'git_blob_sha':digest,'sha256':hashlib.sha256(data).hexdigest()})
    license_bytes=s.fetch(base+'LICENSE.md','LICENSE-Microsoft-Rocketbox.md')
    if hashlib.sha1(b'blob '+str(len(license_bytes)).encode()+b'\0'+license_bytes).hexdigest()!='9bcfb3ece5301a55d3a41bbd00a029ab27d61d13':
        raise ValueError('Reviewed MIT license changed')
    s.fetch(base+'README.md','README-upstream.md')
    report={'schema':'asset-studio.people-acquisition.v1','source':REPO,'license':'MIT',
        'copyright':'Copyright (c) 2020 Microsoft','avatar_trees':TREES,'files':selected,
        'download_bytes':s.used,'native_import_performed':False,'animation_retargeted':False,
        'note':'Retain the MIT license with the source models and derivatives. No endorsement or real-person identity is asserted.'}
    (s.root/'acquisition.json').write_text(json.dumps(report,indent=2),encoding='utf8');s.save()
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
