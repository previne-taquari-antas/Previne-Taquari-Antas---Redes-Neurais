#!/usr/bin/env python3
"""Fail publication on invalid JavaScript or duplicate DOM ids in active pages."""
import collections
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.scripts=[];self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='script':self.current=[a,'']
    def handle_data(self,data):
        if self.current is not None:self.current[1]+=data
    def handle_endtag(self,tag):
        if tag=='script' and self.current is not None:
            self.scripts.append(self.current);self.current=None

def validate(root=ROOT):
    errors=[];count=0;inline=0
    pages=sorted(set(root.glob('*.html'))|set((root/'pesquisas').glob('*.html'))|set((root/'inventario').glob('*.html')))
    def check(path,label):
        result=subprocess.run(['node','--check',str(path)],capture_output=True,text=True)
        if result.returncode:errors.append(label+': '+result.stderr)
    for path in pages:
        page=Page();page.feed(path.read_text(encoding='utf-8'))
        duplicates=[key for key,n in collections.Counter(page.ids).items() if n>1]
        if duplicates:errors.append(str(path)+': duplicate ids '+str(duplicates))
        for attrs,code in page.scripts:
            if 'src' in attrs or not code.strip() or attrs.get('type','') not in ('','text/javascript','application/javascript','module'):continue
            with tempfile.NamedTemporaryFile(mode='w',suffix='.mjs' if attrs.get('type')=='module' else '.js') as temp:
                temp.write(code);temp.flush();check(temp.name,str(path));inline+=1
    for path in sorted((root/'assets').rglob('*.js')):
        if 'generated' in path.parts or path.parent==root/'assets' or path.parent==root/'assets/js':check(path,str(path));count+=1
    if errors:raise SystemExit('\n'.join(errors))
    print(f'OK frontend: {len(pages)} pages, {inline} inline scripts, {count} external scripts')
if __name__=='__main__':validate()
