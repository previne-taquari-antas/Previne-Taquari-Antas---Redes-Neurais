#!/usr/bin/env python3
"""Polígonos OSM próximos à fila CNEFE; inspeção, não residências confirmadas."""
import argparse
import csv
import json
from pathlib import Path
from shapely.geometry import Point, mapping
from shapely.ops import transform
from shapely.strtree import STRtree
from vincular_cnefe_edificacoes_porto_alegre import extrair_predios, TO_GEO, TO_METERS, as_float

def gerar(osm, fila, saida, raio=80, max_edificacoes=18000):
    predios=extrair_predios(osm)
    tree=STRtree([b['geom'] for b in predios])
    escolhidos={}
    with open(fila, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            lat,lon=as_float(row.get('lat_original')),as_float(row.get('lon_original'))
            if lat is None or lon is None:
                continue
            pt=transform(TO_METERS,Point(lon,lat))
            for idx in tree.query(pt.buffer(raio)):
                b=predios[int(idx)]
                if b['geom'].distance(pt)>raio:
                    continue
                escolhidos.setdefault(b['id'],b)
                if len(escolhidos)>=max_edificacoes:
                    break
            if len(escolhidos)>=max_edificacoes:
                break
    features=[]
    for b in escolhidos.values():
        g=transform(TO_GEO,b['geom']).simplify(.000004,preserve_topology=True)
        features.append({'type':'Feature','geometry':mapping(g),
           'properties':{'osm_id':b['id'],'tipo':b['tipo'],'rua':b['street'],
                         'numero':b['number'],'area_m2':b['area_m2'],
                         'residencial_explicito':b['residencial_explicito'],
                         'uso_residencial_nao_confirmado':True}})
    out=Path(saida)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'type':'FeatureCollection','features':features},
                   ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return {'edificacoes_para_revisao':len(features),'limite_amostra':max_edificacoes,'raio_m':raio}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--osm',required=True)
    p.add_argument('--fila',required=True)
    p.add_argument('--saida',required=True)
    p.add_argument('--raio',type=float,default=80)
    p.add_argument('--max-edificacoes',type=int,default=18000)
    a=p.parse_args()
    print(json.dumps(gerar(a.osm,a.fila,a.saida,a.raio,a.max_edificacoes),ensure_ascii=False))
