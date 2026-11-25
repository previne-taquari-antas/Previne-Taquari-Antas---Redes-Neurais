#!/usr/bin/env python3
"""Extract large static scripts into content-addressed cacheable assets at build time.
Source HTML stays intact for the scientific generators and existing contracts.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

SCRIPT=re.compile(r'<script\b([^>]*)>([\s\S]*?)</script>',re.I)

def optimize(site):
    site=Path(site).resolve(); generated=site/'assets/generated'; generated.mkdir(parents=True,exist_ok=True)
    stats={'pages':0,'html_before_bytes':0,'html_after_bytes':0,'assets':0,'asset_bytes':0}
    for path in sorted(site.rglob('*.html')):
        original=path.read_text(encoding='utf-8'); text=original
        def extract(match):
            attrs,code=match.groups()
            if len(code.encode('utf-8'))<32768 or re.search(r'\bsrc\s*=',attrs) or 'document.currentScript' in code:
                return match.group(0)
            kind=re.search(r'\btype=["\']([^"\']+)',attrs)
            kind=kind.group(1).lower() if kind else ''
            identifier=re.search(r'\bid=["\']([^"\']+)',attrs)
            prefix=''
            if kind=='application/json' and identifier:
                # Preserve the exact JSON text consumed by existing generators/readers.
                json.loads(code)
                prefix='<script'+attrs+'></script>\n'
                code='document.getElementById('+json.dumps(identifier.group(1))+').textContent='+json.dumps(code,ensure_ascii=False)+';\n'
                attrs=''
            elif kind not in ('','text/javascript','application/javascript') or identifier:
                return match.group(0)
            digest=hashlib.sha256(code.encode()).hexdigest()[:24]
            asset=generated/(digest+'.js')
            if not asset.exists():
                asset.write_text(code,encoding='utf-8');stats['assets']+=1;stats['asset_bytes']+=len(code.encode())
            relative=Path(os.path.relpath(asset,path.parent)).as_posix()
            return prefix+'<script'+attrs+' src="'+relative+'"></script>'
        text=SCRIPT.sub(extract,text)
        # Changed code gets a new URL even when a client has an older cached bundle.
        def version_asset(match):
            attr,url=match.groups()
            if ':' in url or url.startswith('//'):return match.group(0)
            plain=url.split('?',1)[0]
            target=(path.parent/plain).resolve()
            if target.suffix not in ('.js','.css') or not target.is_relative_to(site) or 'generated' in target.parts or not target.is_file():return match.group(0)
            digest=hashlib.sha256(target.read_bytes()).hexdigest()[:16]
            return attr+'="'+plain+'?v='+digest+'"'
        text=re.sub(r'(src|href)="([^"<>]+)"',version_asset,text)
        if text!=original:
            stats['pages']+=1;stats['html_before_bytes']+=len(original.encode());stats['html_after_bytes']+=len(text.encode())
            path.write_text(text,encoding='utf-8')
    return stats

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--site-dir',required=True)
    print(json.dumps(optimize(parser.parse_args().site_dir),indent=2))
