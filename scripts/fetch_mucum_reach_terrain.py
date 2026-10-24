#!/usr/bin/env python3
"""Crop official ANADEM/PROJ geoid rasters with TLS verification enabled."""
import json,os,sys
from pathlib import Path
import rasterio
from rasterio.windows import from_bounds

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT.parent/'inputs'

def main():
    kind=sys.argv[1]
    if kind=='anadem':
        url='https://metadados.snirh.gov.br/files/anadem_v1_tiles/anadem_v1_22J.tif';name='anadem_reach_egm2008.tif'
        d=json.loads((INPUT/'bho6_taquari_antas_network.geojson').read_text());audit=json.loads((INPUT/'network_audit_latest.json').read_text())
        ids=set(sum([v['segments'] for v in audit['topology']['paths'].values()],[]));xy=[xy for f in d['features'] if f['properties'].get('cotrecho') in ids for xy in f['geometry']['coordinates']]
        bounds=(min(x[0] for x in xy)-.02,min(x[1] for x in xy)-.02,max(x[0] for x in xy)+.02,max(x[1] for x in xy)+.02)
    elif kind=='geoid':
        url='https://cdn.proj.org/us_nga_egm08_25.tif';name='egm2008_local_geoid.tif';bounds=(-52.4,-29.6,-51.3,-28.5)
    else:raise ValueError(kind)
    env=dict(GDAL_HTTP_TIMEOUT=30,GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif')
    if os.environ.get('SSL_CERT_FILE'):env['CURL_CA_BUNDLE']=os.environ['SSL_CERT_FILE'];env['GDAL_CURL_CA_BUNDLE']=os.environ['SSL_CERT_FILE']
    with rasterio.Env(**env):
        with rasterio.open('/vsicurl/'+url) as ds:
            print('REMOTE',kind,ds.shape,ds.crs,ds.block_shapes,flush=True)
            if not ds.crs.is_geographic:raise RuntimeError('Expected geographic raster')
            window=from_bounds(*bounds,ds.transform).round_offsets().round_lengths();a=ds.read(1,window=window);profile=ds.profile
            profile.update(height=a.shape[0],width=a.shape[1],count=1,transform=ds.window_transform(window),compress='deflate',tiled=True,blockxsize=256,blockysize=256)
            with rasterio.open(INPUT/name,'w',**profile) as out:out.write(a,1)
            (INPUT/(name+'.source.json')).write_text(json.dumps(dict(url=url,bounds=list(rasterio.windows.bounds(window,ds.transform)),shape=list(a.shape),crs=str(ds.crs)),indent=2)+'\n')
            print('SAVED',INPUT/name,a.shape,flush=True)

if __name__=='__main__':main()
