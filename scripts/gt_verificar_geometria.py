#!/usr/bin/env python3
"""Auditoria geométrica OSM x CNEFE: NÃO é vistoria ou prova de ocupação.

Verifica se cada ponto CNEFE está no interior de um polígono building OSM
e se há evidência residencial; 'building=yes' não significa casa.
OSM deve ser baixado recentemente e data/fonte retidas.
"""
import argparse, json, math, urllib.request, urllib.parse, time
from collections import Counter
from pathlib import Path

from gt_risco_vida import CIDADES, ROOT, carrega_painel, distancia_m
from gt_auditar_residencias import corresponde

BBOX={
 "santa_tereza":(-29.192,-51.748,-29.158,-51.718),
 "mucum":(-29.171,-51.892,-29.150,-51.855),
}
NONRES=set("roof ruins construction proposed bridge greenhouse garage shed garages service industrial warehouse commercial retail office supermarket kiosk school university college kindergarten hospital public civic government church chapel cathedral religious temple mosque train_station transportation sports_hall sports_centre stadium hangar barn stable cowshed sty silo parking toilets pavilion".split())
RES=set("house detached residential apartments semidetached_house terrace bungalow cabin farm dormitory static_caravan".split())


def overpass(city, cache):
    if cache.exists():return json.loads(cache.read_text(encoding="utf-8"))
    s,w,n,e=BBOX[city]
    query=f'[out:json][timeout:120];way["building"]({s},{w},{n},{e});out geom;'
    payload=urllib.parse.urlencode({"data":query}).encode()
    errs=[]
    for url in ("https://overpass.kumi.systems/api/interpreter",
                "https://overpass-api.de/api/interpreter"):
        try:
            req=urllib.request.Request(url,data=payload,headers={"User-Agent":"PREVINE-GT-geometry-quality-audit/1.0"})
            with urllib.request.urlopen(req,timeout=120) as response: result=json.load(response)
            cache.parent.mkdir(parents=True,exist_ok=True)
            cache.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
            return result
        except Exception as e:errs.append(f"{url}: {type(e).__name__} {e}")
    raise RuntimeError("OSM unavailable; geometry validation NOT performed: "+"; ".join(errs))


def inside(lon,lat,polygon):
    # Ray crossing in lon/lat; adequate for point-in-polygon at this local extent.
    flag=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        x1,y1=a;x2,y2=b
        if ((y1>lat)!=(y2>lat)) and lon < (x2-x1)*(lat-y1)/(y2-y1)+x1:flag=not flag
    return flag


def audit(city,data,osm):
    ways=[]
    for e in osm.get("elements",[]):
        tag=e.get("tags",{}).get("building","yes")
        points=[(p["lon"],p["lat"]) for p in e.get("geometry",[])]
        if e.get("type")!="way" or len(points)<4:continue
        ways.append({"id":e["id"],"type":tag,"ring":points,
                     "box":(min(p[0] for p in points),min(p[1] for p in points),
                            max(p[0] for p in points),max(p[1] for p in points))})
    matched,summary=[],Counter()
    for i,f in enumerate(data["features"]):
        lon,lat=f["geometry"]["coordinates"]
        s,w,n,e=BBOX[city]
        if not(s<=lat<=n and w<=lon<=e):
            summary["fora_recorte_piloto"]+=1
            continue
        hit=[v for v in ways if v["box"][0]<=lon<=v["box"][2] and v["box"][1]<=lat<=v["box"][3]
             and inside(lon,lat,v["ring"])]
        cls=("dentro_poligono_residencial_osm" if any(v["type"] in RES for v in hit)
            else "dentro_poligono_uso_indefinido" if any(v["type"] not in NONRES for v in hit)
            else "dentro_poligono_nao_residencial" if hit
            else "sem_poligono_cobrindo_ponto")
        summary[cls]+=1
        matched.append({"type":"Feature","geometry":f["geometry"],"properties":{
            "cnefe_index":i,"classe_auditoria":cls,
            "tag_building": sorted(set(v["type"] for v in hit)) or [],
            "osm_way_ids":[v["id"] for v in hit],
            "unidades_cnefe_2022":f["properties"]["unidades_domiciliares_cnefe_2022"],
            "verificado_em_imagem_recente":False,"confirmado_em_campo":False,
            "moradia_2026_validada":False}})
    summary["pontos_cnefe_dentro_recorte"]=len(matched)
    summary["poligonos_osm_consultados"]=len(ways)
    return {"type":"FeatureCollection","features":matched},dict(summary)


def main():
    p=argparse.ArgumentParser();p.add_argument("--cidade",choices=list(CIDADES),required=True)
    p.add_argument("--pasta",type=Path,default=ROOT/"artifacts/gt_risco_vida")
    args=p.parse_args()
    d=json.loads((args.pasta/f"{args.cidade}_cnefe_residencial_2022.geojson").read_text(encoding="utf-8"))
    osm=overpass(args.cidade,args.pasta/f"{args.cidade}_osm_footprints_fonte.json")
    gj,counts=audit(args.cidade,d,osm)
    (args.pasta/f"{args.cidade}_cnefe_verificacao_geometrica.geojson").write_text(json.dumps(gj,ensure_ascii=False),encoding="utf-8")
    counts.update({"municipio":args.cidade,"status":"auditoria_geometrica_preliminar_nao_validacao_campo",
                   "limites":"Tag building não valida ocupação; imagem aérea datada e campo pendentes."})
    (args.pasta/f"{args.cidade}_verificacao_geometrica_resumo.json").write_text(json.dumps(counts,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(counts,ensure_ascii=False))

if __name__=="__main__": main()
