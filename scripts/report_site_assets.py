"""Reproducible inventory of pages, shared assets, duplicates and loaded libraries."""
import argparse,collections,hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='script' and a.get('src'):self.links.append(a['src'])
  if tag=='link' and a.get('href') and a.get('rel')=='stylesheet':self.links.append(a['href'])
def inventory(root):
 root=Path(root).resolve();pages=[];used=set();libraries=set();groups=collections.defaultdict(list)
 for p in sorted(root.rglob('*.html')):
  if any(x in p.parts for x in ['node_modules','.git','raw','rascunhos','_site']):continue
  parser=Links();parser.feed(p.read_text());pages.append({'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size})
  for url in parser.links:
   if url.startswith(('http:','https:','//')):libraries.add(url)
   else:used.add((p.parent/url.split('?')[0]).resolve())
 assets=list((root/'assets').rglob('*.js'))+list((root/'assets').rglob('*.css'))
 for p in assets:groups[hashlib.sha256(p.read_bytes()).hexdigest()].append(p.relative_to(root).as_posix())
 workflows=[]
 for p in sorted((root/'.github/workflows').glob('*.yml')):
  text=p.read_text();workflows.append({'path':p.relative_to(root).as_posix(),'name':next((line[5:].strip() for line in text.splitlines() if line.startswith('name:')),''),'scripts':sorted(set(re.findall(r'(?:scripts|codigo_python)/[A-Za-z0-9_./-]+\.py',text)))})
 return {'pages':pages,'total_html_bytes':sum(p['bytes'] for p in pages),'external_libraries':sorted(libraries),'identical_assets':[v for v in groups.values() if len(v)>1],'assets_without_direct_html_reference':[p.relative_to(root).as_posix() for p in assets if p.resolve() not in used],'workflows':workflows,'note':'No direct HTML reference does not mean unused: generators and JavaScript may load these files.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(inventory(a.root),ensure_ascii=False,indent=2)+'\n')
