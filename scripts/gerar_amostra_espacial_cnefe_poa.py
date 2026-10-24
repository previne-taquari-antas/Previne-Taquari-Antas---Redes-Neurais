#!/usr/bin/env python3
"""Criar amostra espacial reproduzível do CNEFE Porto Alegre para visualização (não validada)."""
import argparse, csv, hashlib, json
from pathlib import Path
from collections import defaultdict, Counter

FIELDS=('id_cnefe','nv_geo_coord','rua_ibge','numero_ibge','lat_original','lon_original',
 'lat_proposta','lon_proposta','quantidade_mesmo_ponto','status','osm_candidato',
 'tipo_osm','distancia_footprint_m','justificativa','street_view_url')
def main(csv_path,resumo,out,per_cell=2):
    # Estratificação por células ~275m × 290m e tipo de avaliação.
    grid=defaultdict(dict)
    count=0
    with open(csv_path,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            count+=1
            try:
                lat=float(r['lat_original']);lon=float(r['lon_original'])
                if not (-30.50<lat<-29.50 and -51.60<lon<-50.70): continue
            except (ValueError,KeyError,TypeError): continue
            xy=(r['lat_original'],r['lon_original'])
            key=(round((lat+31)/.0025),round((lon+52)/.003),r['status'])
            rank=int.from_bytes(hashlib.blake2b(r['id_cnefe'].encode(),digest_size=5).digest(),'big')
            entries=grid[key]
            if xy not in entries or rank<entries[xy][0]:entries[xy]=(rank,r)
            if len(entries)>per_cell:del entries[max(entries,key=lambda v:entries[v][0])]
    best={}
    for subset in grid.values():
        for xy,(rank,r) in subset.items():
            if xy not in best or rank<best[xy][0]:best[xy]=(rank,r)
    rows=[{k:r.get(k,'') for k in FIELDS} for rank,r in best.values()]
    rows.sort(key=lambda r:(float(r['lat_original']),float(r['lon_original']),r['id_cnefe']))
    summary=json.loads(Path(resumo).read_text(encoding='utf-8'))
    assert count==summary['domicilios_particulares_cnefe'], 'Auditoria incompleta'
    payload={'fonte':'CNEFE 2022 IBGE + footprints OSM; associações ainda não validadas',
             'total_amostra':len(rows),'coordenadas_distintas_amostra':len(best),
             'universo_domicilios':count,
             'por_status':dict(Counter(r['status'] for r in rows)),
             'metodo':'Máximo 2 coordenadas distintas por grade de aproximadamente 275m x 290m e status',
             'observacao':'Pontos laranja originais CNEFE; candidatos azuis NÃO validados.',
             'dados':rows}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'universo':count,'pontos_espacialmente_distribuidos':len(rows),
                      'coordenadas_distintas':len(best)},ensure_ascii=False))
if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--csv',required=True);a.add_argument('--resumo',required=True)
    a.add_argument('--saida',required=True);a.add_argument('--por-celula',type=int,default=2)
    p=a.parse_args();main(p.csv,p.resumo,p.saida,p.por_celula)
