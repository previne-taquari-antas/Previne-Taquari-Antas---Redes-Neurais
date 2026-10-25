#!/usr/bin/env python3
"""Regional terrain screening against calibrated incremental reach storage.

ANADEM is kept separate from drone geometry. A linear longitudinal water
surface between observed gauges is a screening hypothesis, not hydraulics.
"""
import csv,json
from pathlib import Path
import numpy as np
import rasterio,shapely
from rasterio.warp import calculate_default_transform,reproject,Resampling
from rasterio.features import rasterize
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import binary_propagation
from pyproj import Transformer
from shapely.geometry import LineString,Point,mapping
from shapely.ops import transform
import build_mucum_floodplain_storage as geo
import run_hec_hms_g040_e1_hindcast as hms
from search_mucum_lateral_storage import OUT

def main():
    inp=geo.ROOT.parent/'inputs';audit=json.loads((inp/'network_audit_latest.json').read_text());network=json.loads((inp/'bho6_taquari_antas_network.geojson').read_text())
    by={str(f['properties']['cotrecho']):f for f in network['features'] if 'cotrecho' in f['properties']}
    ids=audit['topology']['paths']['86472000_to_86472600']['segments']+audit['topology']['paths']['86472600_to_86510000']['segments'][1:]
    xy=[]
    for id in ids:
        coords=by[str(id)]['geometry']['coordinates']
        if xy and np.linalg.norm(np.array(xy[-1])-coords[-1])<np.linalg.norm(np.array(xy[-1])-coords[0]):coords=coords[::-1]
        xy.extend(coords if not xy else coords[1:])
    project=Transformer.from_crs(4326,32722,always_xy=True);inverse=Transformer.from_crs(32722,4326,always_xy=True)
    line=transform(project.transform,LineString(xy));j=audit['stations']['86472000'];mu=Point(geo.GAUGE_LON,geo.GAUGE_LAT)
    sj=line.project(transform(project.transform,Point(j['lon'],j['lat'])));sm=line.project(transform(project.transform,mu))
    with rasterio.open(inp/'anadem_reach_egm2008.tif') as src:
        tx,w,h=calculate_default_transform(src.crs,32722,src.width,src.height,*src.bounds,resolution=30.)
        z=np.full((h,w),np.nan,'float32');reproject(rasterio.band(src,1),z,src_transform=src.transform,src_crs=src.crs,src_nodata=src.nodata,dst_transform=tx,dst_crs=32722,dst_nodata=np.nan,resampling=Resampling.bilinear)
    rr,cc=np.indices(z.shape);xx=tx.c+(cc+.5)*30;yy=tx.f-(rr+.5)*30;lon,lat=inverse.transform(xx,yy)
    with rasterio.open(inp/'egm2008_local_geoid.tif') as egm:
        nn=egm.read(1);ys=egm.transform.f+(np.arange(egm.height)+.5)*egm.transform.e;xs=egm.transform.c+(np.arange(egm.width)+.5)*egm.transform.a
        egm_interp=RegularGridInterpolator((ys[::-1],xs),nn[::-1],bounds_error=True)
    map_interp=geo.geoid_interpolator(geo.OUT/'mapgeo2015_local_grid.json')
    points=np.column_stack([lat.ravel(),lon.ravel()]);ne=egm_interp(points).reshape(z.shape);nm=map_interp(points).reshape(z.shape)
    # h=H_EGM2008+N_EGM2008, H_MAPGEO2015=h-N_MAPGEO2015.
    z=(z+ne-nm).astype('float32');valid=np.isfinite(z)
    chain=shapely.line_locate_point(line,shapely.points(xx.ravel(),yy.ravel())).reshape(z.shape);within=(chain>=sj)&(chain<=sm)
    fraction=np.clip((chain-sj)/(sm-sj),0,1)
    with rasterio.open(OUT/'regional_terrain_MAPGEO2015_30m.tif','w',driver='GTiff',height=h,width=w,count=1,dtype='float32',crs=32722,transform=tx,nodata=-9999.,compress='deflate') as ds:ds.write(np.where(valid,z,-9999.).astype('float32'),1)
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text())
    def gauge(code,zero):
        c=next(c for c in raw['controls'] if str(c['code'])==code);rows=[r for r in c['recent_rows'] if r.get('level_source_unit') is not None]
        return np.array([hms.utc(r['time_utc']).timestamp() for r in rows]),np.array([zero+r['level_source_unit']/100 for r in rows])
    jt,jh=gauge('86472000',61.140);mt,mh=gauge('86510000',33.985)
    native=OUT/'verified_isolated/project';byq=hms.read_output_csv(native/'hec_output_values.csv');p=json.loads((OUT/'screening.json').read_text())['selected']['parameters']
    first=next(i for i,(t,q) in enumerate(byq['SRC_86472000']) if q>p['threshold_m3s']);initial=byq['SRC_86472000'][max(0,first-1)][0]
    storage=[r for r in csv.DictReader((native/'lateral_native_values.csv').open()) if r['element']=='FP_REACH' and r['variable']=='STORAGE'];smax=max(storage,key=lambda r:float(r['value']));smax_time=hms.dss_time_to_utc(smax['time_value']);peak_time=max(byq['J_86510000'],key=lambda z:z[1])[0]
    cases=[('before_first_diversion',initial),('maximum_model_storage',smax_time),('model_discharge_crest',peak_time)]
    results=[]
    for width in [50,100,150]:
        channel=rasterize([(mapping(line.buffer(width)),1)],out_shape=z.shape,transform=tx,fill=0,dtype='uint8').astype(bool)
        for shift in [-1.,0.,1.]:
            reference=None
            for name,t in cases:
                hj=float(np.interp(t.timestamp(),jt,jh));hm=float(np.interp(t.timestamp(),mt,mh));water=(1-fraction)*hj+fraction*hm+shift
                wet=(valid&(z<=water))|channel;conn=binary_propagation(channel,mask=wet,structure=np.ones((3,3),bool));land=conn&valid&~channel&within
                volume=float(np.maximum(water[land]-z[land],0).sum()*900);area=float(land.sum()*900)
                if reference is None:reference=volume
                results.append(dict(channel_half_width_m=width,water_minus_terrain_shift_m=shift,case=name,time_utc=t.isoformat(),JJ_water_MAPGEO2015_m=hj,Mu_water_MAPGEO2015_m=hm,
                    connected_land_area_m2=area,connected_land_volume_m3=volume,incremental_volume_above_first_diversion_m3=volume-reference))
    central=next(r for r in results if r['channel_half_width_m']==100 and r['water_minus_terrain_shift_m']==0 and r['case']=='maximum_model_storage')
    channel=rasterize([(mapping(line.buffer(100)),1)],out_shape=z.shape,transform=tx,fill=0,dtype='uint8').astype(bool)
    hourly=[]
    for t in hms.hourly_axis(byq['SRC_86472000'][0][0],byq['SRC_86472000'][-1][0]):
        hj=float(np.interp(t.timestamp(),jt,jh));hm=float(np.interp(t.timestamp(),mt,mh));water=(1-fraction)*hj+fraction*hm
        conn=binary_propagation(channel,mask=(valid&(z<=water))|channel,structure=np.ones((3,3),bool));land=conn&valid&~channel&within
        hourly.append(dict(time_utc=t.isoformat(),connected_land_volume_m3=float(np.maximum(water[land]-z[land],0).sum()*900),connected_land_area_m2=int(land.sum())*900))
    geo.save(OUT/'regional_hourly_capacity.json',dict(geometry_scenario='100 m channel half-width, 30 m ANADEM, central vertical datum, observed linear endpoint profile',
        hourly=hourly,max_connected_land_volume_m3=max(r['connected_land_volume_m3'] for r in hourly),capacity_is_scenario_not_measured_truth=True))
    report=dict(method='Regional 30 m ANADEM terrain screening with observed endpoint water levels and a linear along-river profile.',
        ANADEM_source='https://hge-iph.github.io/anadem/',EGM2008_geoid_source='https://cdn.proj.org/us_nga_egm08_25.tif',
        vertical_transform='H_MAPGEO2015=H_ANADEM_EGM2008+N_EGM2008-N_MAPGEO2015',analysis_resolution_m=30.,reach_length_between_gauges_m=sm-sj,
        channel_bank_lines_measured=False,water_surface_hydraulically_validated=False,regional_vertical_accuracy_verified=False,
        model_incremental_max_storage_m3=float(smax['value'])*1000,central_geometry_case=central,cases=results,maximum_hourly_connected_land_volume_m3=max(r['connected_land_volume_m3'] for r in hourly),
        interpretation='Compare incremental model storage with incremental terrain capacity, not with total already-flooded volume. This screening cannot validate flow exchange, water-surface curvature, bathymetry, or backwater.',
        local_drone_geometry_changed=False)
    geo.save(OUT/'regional_capacity_screening.json',report)
    print(json.dumps(dict(model_storage_m3=report['model_incremental_max_storage_m3'],central=central,incremental_range_m3=[min(r['incremental_volume_above_first_diversion_m3'] for r in results if r['case']=='maximum_model_storage'),max(r['incremental_volume_above_first_diversion_m3'] for r in results if r['case']=='maximum_model_storage')]),ensure_ascii=False))

if __name__=='__main__':main()
