#!/usr/bin/env python3
"""Quantify local floodplain geometry from the existing drone terrain.

This is terrain-derived capacity, not a new field survey or hydraulic validation.
The raw drone is treated as ellipsoidal as in the source pipeline. MAPGEO2015
is applied explicitly to match the published SGB gauge-zero datum, rather than
mixing the repository's hgeoHNOR2020-corrected raster with orthometric levels.
"""
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform,reproject,Resampling
from rasterio.features import rasterize,shapes
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import binary_propagation
from pyproj import Transformer
import shapely
from shapely.geometry import shape,mapping,LineString,Point
from shapely.ops import transform,unary_union

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/data/g040_hydro_stack/mucum_floodplain_storage_20261024'
GAUGE_ZERO=33.985
GAUGE_LON=-(51+52/60+7.8212/3600)
GAUGE_LAT=-(29+10/60+1.8947/3600)
PEAK_STAGE=22.975
SOURCE_URL='https://rigeo.sgb.gov.br/bitstream/doc/25518/1/marcuzzo_silva_Mendes_zero%20ortometrico_artigo.pdf'
MAPGEO_URL='https://geoftp.ibge.gov.br/modelos_digitais_de_superficie/modelo_de_ondulacao_geoidal/aplicativo_desktop_MAPGEO2015/setup_mapgeo2015_v1.exe'

def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.pending');temp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');temp.replace(p)

def geoid_interpolator(grid):
    if grid.suffix.lower()=='.json':
        d=json.loads(grid.read_text());return RegularGridInterpolator((d['latitude'],d['longitude']),np.array(d['undulation_m']),bounds_error=True)
    a=np.loadtxt(grid);lon=np.where(a[:,0]>180,a[:,0]-360,a[:,0]);lat=a[:,1]
    keep=(lon>-52.2)&(lon<-51.5)&(lat>-29.5)&(lat<-28.8)
    lon,lat,n=lon[keep],lat[keep],a[keep,2];xs=np.unique(lon);ys=np.unique(lat)
    z=np.full((len(ys),len(xs)),np.nan);z[np.searchsorted(ys,lat),np.searchsorted(xs,lon)]=n
    if not np.isfinite(z).all():raise RuntimeError('MAPGEO grid has missing local nodes')
    save(OUT/'mapgeo2015_local_grid.json',dict(longitude=xs.tolist(),latitude=ys.tolist(),undulation_m=z.tolist(),source=MAPGEO_URL))
    return RegularGridInterpolator((ys,xs),z,bounds_error=True)

def route(network,audit):
    d=json.loads(network.read_text());by={str(f['properties']['cotrecho']):shape(f['geometry']) for f in d['features'] if 'cotrecho' in f['properties']}
    ids=json.loads(audit.read_text())['topology']['paths']['86472600_to_86510000']['segments']
    xy=[]
    for id in ids:
        coords=list(by[str(id)].coords)
        if xy and np.linalg.norm(np.array(xy[-1])-coords[-1])<np.linalg.norm(np.array(xy[-1])-coords[0]):coords.reverse()
        xy.extend(coords if not xy else coords[1:])
    project=Transformer.from_crs(4326,32722,always_xy=True).transform
    return transform(project,LineString(xy)),transform(project,Point(GAUGE_LON,GAUGE_LAT))

def connected_capacity(z,valid,channel,upstream,stage,half_width,datum_shift=0.):
    height=GAUGE_ZERO+stage+datum_shift
    passable=(valid&(z<=height))|channel
    connected=binary_propagation(channel,mask=passable,structure=np.ones((3,3),bool))
    land=connected&valid&~channel&upstream
    volume=float(np.maximum(height-z[land],0).sum()*4)
    return int(land.sum())*4.,volume,land

def main():
    ap=argparse.ArgumentParser();ap.add_argument('grid',type=Path);ap.add_argument('network',type=Path);ap.add_argument('audit',type=Path);args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    dem=ROOT/'assets/data/mucum_inundacao/mdt/mdt_mucum_drone_1m.tif'
    interp=geoid_interpolator(args.grid);line,gauge=route(args.network,args.audit)
    with rasterio.open(dem) as src:
        tx,w,h=calculate_default_transform(src.crs,32722,src.width,src.height,*src.bounds,resolution=2.)
        z=np.full((h,w),np.nan,dtype='float32')
        reproject(rasterio.band(src,1),z,src_transform=src.transform,src_crs=src.crs,src_nodata=src.nodata,dst_transform=tx,dst_crs=32722,dst_nodata=np.nan,resampling=Resampling.average)
        source_size=list(src.shape);source_res=list(src.res)
    rr,cc=np.indices(z.shape);xx=tx.c+(cc+.5)*2;yy=tx.f-(rr+.5)*2
    inverse=Transformer.from_crs(32722,4326,always_xy=True);lon,lat=inverse.transform(xx,yy)
    n=interp(np.column_stack([lat.ravel(),lon.ravel()])).reshape(z.shape)
    z=(z-n).astype('float32');valid=np.isfinite(z)
    points=shapely.points(xx.ravel(),yy.ravel());chain=shapely.line_locate_point(line,points).reshape(z.shape)
    gauge_s=line.project(gauge);upstream=chain<gauge_s-1.
    manifest=dict(status='LOCAL_TERRAIN_CAPACITY_COMPUTED_NOT_FIELD_OR_HYDRODYNAMIC_VALIDATION',
        gauge=dict(code='86510000',zero_orthometric_m=GAUGE_ZERO,zero_source=SOURCE_URL,longitude=GAUGE_LON,latitude=GAUGE_LAT,
            nearest_BHO6_centerline_distance_m=line.distance(gauge),source_decimal_coordinates_differ_from_DMS=True,
            coordinate_rule='Use full DMS in source table; snap only for along-river terrain partition, never to redefine station coordinates'),
        terrain=dict(source=str(dem.relative_to(ROOT)),source_shape=source_size,source_degree_spacing=source_res,
            analysis_resolution_m=2.,crs='EPSG:32722',valid_area_m2=int(valid.sum())*4,
            raw_vertical_reference='ellipsoidal hypothesis inherited from source pipeline; original flight/GCP vertical report not recovered',
            transformation='H_MAPGEO2015 = raw_drone_h - bilinear_MAPGEO2015_N',
            local_MAPGEO2015_N_min_m=float(n.min()),local_MAPGEO2015_N_max_m=float(n.max()),
            geoid_at_gauge_m=float(interp([[GAUGE_LAT,GAUGE_LON]])[0]),
            no_submerged_bed_recovery=True),
        geometry=dict(reference_inundation_stage_m=18.,reference_is_not_a_surveyed_bankfull_elevation=True,
            connected_rule='8-connected wet cells touching BHO6 river buffer; river ribbon seeds connectivity across water/NoData only; invalid land never receives capacity',
            upstream_rule='Nearest along-river chainage before gauge cross section; local source footprint only',
            channel_exclusion_half_widths_m=[50,100,150],channel_bank_lines_measured=False,
            water_surface='horizontal local stage surface; slope/backwater and filling dynamics not solved'),
        scientific_limits=['No new field measurements were made. Quantities are derived from the archived drone surface.',
            'Original flight date/epoch and control-point report were not recovered; terrain may postdate the November 2023 event.',
            'The drone footprint does not cover the entire Linha Jose Julio to Mucum reach; local volume cannot be relabeled as reach-total measured storage.',
            'Original drone datum and vertical accuracy still need flight/control-point metadata; MAPGEO conversion is explicit and sensitivity is reported.',
            'A single horizontal surface cannot represent the Guapore backwater or longitudinal flood surface.',
            'Side-storage release/conveyance is not measured by a terrain volume calculation.'],
        fingerprints={str(dem.relative_to(ROOT)):hashlib.sha256(dem.read_bytes()).hexdigest(),
            'MAPGEO2015_SIRGAS2000.txt':hashlib.sha256(args.grid.read_bytes()).hexdigest(),
            'BHO6_network':hashlib.sha256(args.network.read_bytes()).hexdigest()})
    profile=dict(driver='GTiff',height=h,width=w,count=1,crs='EPSG:32722',transform=tx,dtype='float32',nodata=-9999.,compress='deflate')
    with rasterio.open(OUT/'mucum_terreno_MAPGEO2015_2m.tif','w',**profile) as dst:dst.write(np.where(valid,z,-9999.).astype('float32'),1)
    features=[];rows=[];cases=[]
    stages=sorted(set(np.round(np.arange(1.7,26.5001,.25),3).tolist()+[18.,PEAK_STAGE,26.11,26.5]))
    for width in [50,100,150]:
        channel=rasterize([(mapping(line.buffer(width)),1)],out_shape=z.shape,transform=tx,fill=0,dtype='uint8').astype(bool)
        for partition,mask in [('upstream_of_gauge',upstream),('entire_local_drone_footprint',np.ones_like(upstream))]:
            reference=connected_capacity(z,valid,channel,mask,18.,width)[1]
            for stage in stages:
                area,vol,wet=connected_capacity(z,valid,channel,mask,stage,width)
                rows.append(dict(channel_half_width_m=width,domain=partition,gauge_stage_m=stage,water_elevation_MAPGEO2015_m=GAUGE_ZERO+stage,
                    connected_floodplain_area_m2=area,connected_floodplain_total_volume_m3=vol,incremental_volume_above_stage18_m3=max(0,vol-reference)))
                if width==100 and partition=='upstream_of_gauge' and stage in [18.,PEAK_STAGE,26.11]:
                    geoms=[shape(g) for g,val in shapes(wet.astype('uint8'),mask=wet,transform=tx) if val==1]
                    poly=unary_union(geoms).simplify(2.,preserve_topology=True) if geoms else None
                    if poly is not None:features.append(dict(type='Feature',properties=rows[-1],geometry=mapping(transform(inverse.transform,poly))))
        for shift in [-1.,-.5,0.,.5,1.]:
            area,vol,_=connected_capacity(z,valid,channel,upstream,PEAK_STAGE,width,shift)
            cases.append(dict(channel_half_width_m=width,water_minus_terrain_bias_m=shift,peak_stage_m=PEAK_STAGE,area_m2=area,total_volume_m3=vol))
    with (OUT/'curva_cota_area_volume.csv').open('w',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    save(OUT/'planicie_conectada.geojson',dict(type='FeatureCollection',features=features))
    manifest['peak_stage_2023_11_telemetry_m']=PEAK_STAGE;manifest['datum_and_width_sensitivity']=cases
    manifest['representative_capacity']=next(r for r in rows if r['channel_half_width_m']==100 and r['domain']=='upstream_of_gauge' and r['gauge_stage_m']==PEAK_STAGE)
    save(OUT/'terrain_capacity_manifest.json',manifest)
    print(json.dumps(manifest['representative_capacity'],ensure_ascii=False))

if __name__=='__main__':main()
