import json,re,math,hashlib,subprocess
from pathlib import Path
import numpy as np
import run_hec_hms_g040_e1_hindcast as hms
import export_mucum_estrela_event_calibration as ind
ROOT=Path(__file__).resolve().parents[1];FORCING=ROOT/'assets/data/hec_hms_g040_full_basin/historical_calibration_forcing/E27_MAY2024';OUT=ROOT/'assets/data/g040_hydro_stack/estrela_may2024_20261024'
ZONES=['BRANCH_86595000','CORE_INC_86510000_86720000','CORE_INC_86720000_86743000','BRANCH_86746000','CORE_INC_86743000_86879000','CORE_INC_86879000_86879300'];GROUPS=['guapore','residual','residual','forqueta','residual','residual'];DOWNS=['J_JOIN_86595000','J_86720000','J_86743000','J_JOIN_86746000','J_86879000','J_86879300']
KEYS=[v+'_'+g for g in ['guapore','forqueta','residual'] for v in ['initial','loss','tc','r','gw_k','fraction']]+['k_up','k_down','baseflow_specific','recession'];LOW=[x for _ in range(3) for x in [0,.02,.3,.3,.3,0]]+[.4,.4,.001,.85];HIGH=[x for _ in range(3) for x in [180,15,60,100,100,1]]+[10,20,.3,.9999]
SEED={k:v for g in ['guapore','forqueta','residual'] for k,v in zip([v+'_'+g for v in ['initial','loss','tc','r','gw_k','fraction']],[10,2,6,12,12,.4])};SEED.update(k_up=1,k_down=2,baseflow_specific=.05,recession=.96,gw_steps=2)
def load(p):return json.loads(Path(p).read_text())
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def prepare():
 rain=load(FORCING/'rain.json');hydro=load(FORCING/'hydro.json');src=next(c for c in hydro['controls'] if c['code']=='86510000')['recent_rows'];times=[hms.utc(r['time_utc']) for r in src];q=[r['flow_m3s'] for r in src];assert times==hms.hourly_axis(times[0],times[-1]) and all(v is not None and v>=0 for v in q)
 comp={c['component_id']:c for c in rain['components']};values={};areas={}
 for z in ZONES:
  areas[z]=comp[z]['support_area_km2'];d={hms.utc(r['time_local']+'-03:00'):r['mm'] for r in comp[z]['series']};values[z]=[d[t] for t in times];assert all(v is not None and v>=0 for v in values[z])
 rr=next(c for c in hydro['controls'] if c['code']=='86879300')['recent_rows'];low=min([r for r in rr if r['flow_m3s'] is not None],key=lambda r:r['level_source_unit']);bound=dict(Q_upper_bound_m3s=low['flow_m3s'],stage_ceiling_cm=low['level_source_unit'],times_utc=[r['time_utc'] for r in rr if r['flow_m3s'] is None and r['level_source_unit']<low['level_source_unit']]);digest=hashlib.sha256((FORCING/'rain.json').read_bytes()+(FORCING/'hydro.json').read_bytes()).hexdigest();audit=dict(event='E27_MAY2024',city='Estrela',target='86879300',source='86510000',source_hours=len(times),Q_pairs=132,stage_hours=len(rr),low_stage_constraint=bound,input_sha256=digest,area_incremental_km2=sum(areas.values()),area_upstream_km2=15965.207,rain_diagnostics=rain['rain_diagnostics'],role='Event-specific conditional hindcast calibration, not independent forecast validation',observation_clock_shift_minutes=0,area_note='Existing regional component support areas; not newly surveyed floodplain or catchment area.')
 save(OUT/'input_audit.json',audit);return times,q,values,areas,hydro,digest,audit

def basin(p,c):
 text='''Basin: G040 E1 Hindcast
     Description: Estrela May2024 own downstream calibration, observed Muçum boundary
     Version: 4.13
     Filepath Separator: \\
     Unit System: Metric
     Missing Flow To Zero: No
     Enable Flow Ratio: No
     Compute Local Flow At Junctions: No
     Unregulated Output Required: No
     Enable Sediment Routing: No
End:
'''+hms.source_block('86510000','R_86510000_JOIN_86595000',15965.207)
 for z,group,down in zip(ZONES,GROUPS,DOWNS):
  g=p.get('zone_groups',{}).get(z,group)
  initial,loss,tc,r=[p[v+'_'+g] for v in ['initial','loss','tc','r']];b=hms.subbasin_block(hms.hec_subbasin_name(z),c[3][z],down,50,120,(p['baseflow_specific'],p['recession'],.01),(initial,loss,tc,r));b=re.sub(r'     LossRate: Initial\+Constant\n     Percent Impervious Area: 0.0\n     Initial Loss: [^\n]+\n     Constant Loss Rate: [^\n]+',f'     LossRate: Deficit Constant\n     Percent Impervious Area: 0.0\n     Initial Deficit: {initial:.9f}\n     Maximum Deficit: 200\n     Percolation Rate: {loss:.9f}\n     Recovery Factor: 1.0',b);b=re.sub(r'     Baseflow: Recession\n.*?     Threshold Flow to Peak Ratio: [^\n]+',f'     Baseflow: Linear Reservoir\n     Groundwater Layer: 1\n     GW-1 Baseflow Fraction: {p["fraction_"+g]:.9f}\n     GW-1 Number Reservoirs: {p.get("gw_steps_"+g,p["gw_steps"])}\n     GW-1 Routing Coefficient: {p["gw_k_"+g]:.9f}\n     GW-1 Initial Flow/Area Ratio: 0\n     Groundwater Layer: 2\n     GW-2 Baseflow Fraction: 0\n     GW-2 Number Reservoirs: 1\n     GW-2 Routing Coefficient: {-24/math.log(p["recession"]):.9f}\n     GW-2 Initial Flow/Area Ratio: {p["baseflow_specific"]:.9f}',b,flags=re.S);text+=b
 for name,down in [('J_JOIN_86595000','R_JOIN_86595000_86720000'),('J_86720000','R_86720000_86743000'),('J_86743000','R_86743000_JOIN_86746000'),('J_JOIN_86746000','R_JOIN_86746000_86879000'),('J_86879000','R_86879000_86879300'),('J_86879300',None)]:text+=hms.junction_block(name,down,True)
 for name,up,down,length,g in hms.active_reaches('86510000'):
  if g=='g4':continue
  text+=hms.reach_block(name,down,p['k_up' if g=='g2' else 'k_down']*length/hms.GROUP_LENGTH[g],p.get('routing_x',0),1)
 assert re.findall(r'^Source: (.*)$',text,re.M)==['SRC_86510000'];return text

def evaluate(proj,c):
 by=hms.read_output_csv(proj/'hec_output_values.csv');sim=by['J_86879300'];assert len(sim)==6221 and all(q>=0 and np.isfinite(q) for t,q in sim);pairs=ind.independent_pairs(sim,c[4],'86879300',dict(start_utc=c[0][0].isoformat(),end_utc=c[0][-1].isoformat()));s=ind.metrics(pairs);ot,oq,_=max(pairs,key=lambda r:r[1]);pt,pq=max(sim,key=lambda r:r[1]);rise=[(o,q) for t,o,q in pairs if 0<=(ot-t).total_seconds()<=86400];fall=[(o,q) for t,o,q in pairs if t>ot];b=c[6]['low_stage_constraint'];d=dict(sim);ex=[max(0,d[hms.utc(t)]/b['Q_upper_bound_m3s']-1) for t in b['times_utc']];s.update(peak_error_pct=100*(pq/oq-1),peak_time_h=(pt-ot).total_seconds()/3600,peak_m3s=pq,peak_utc=pt.isoformat(),rising_NMAE=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise),recession_NMAE=sum(abs(o-q) for o,q in fall)/sum(o for o,q in fall),low_stage_bound_exceedance=max(ex),low_stage_bound_pass=max(ex)<=.1);return s

def compute(p,c):
 key=hashlib.sha256(json.dumps(p,sort_keys=True).encode()+c[5].encode()).hexdigest()[:12];dest=OUT/'runs'/key;proj=dest/'project';f=dest/'result.json'
 if f.exists():return load(f)
 proj.mkdir(parents=True,exist_ok=True)
 for name,t in [('g040_e1_hindcast.hms',hms.build_project()),('g040_e1_hindcast.run',hms.build_run()),('e1.control',hms.build_control(c[0][0],c[0][-1])),('e1.met',hms.build_met(ZONES)),('e1.basin',basin(p,c)),('g040_e1_hindcast.gage',hms.build_gage(c[0][0],c[0][-1],[],ZONES,'86510000'))]:(proj/name).write_text(t)
 script=hms.write_jython(proj,c[0],{'86510000':c[1]},c[2]);script.write_text(script.read_text().replace('Exit(1)','Exit(0)'));hec=ROOT.parent/'runtime/HEC-HMS-4.13/hec-hms.sh';cp=subprocess.run([str(hec),'-s',str(script)],cwd=hec.parent,capture_output=True,text=True,timeout=300);(dest/'compute.log').write_text(cp.stdout+'\n'+cp.stderr);assert 'G040_E1_HINDCAST_COMPUTE_OK' in cp.stdout
 d=dict(parameters=p,metrics=evaluate(proj,c),project=str(proj.relative_to(ROOT)),input_sha256=c[5],native=True,conditional_observed_boundary='Muçum 86510000',target_observation_used_as_inflow=False);save(f,d);print(json.dumps(d),flush=True);return d
if __name__=='__main__':
 import sys
 c=prepare();p=load(sys.argv[1]) if len(sys.argv)>1 else SEED;d=compute(p,c);save(OUT/('latest_native.json' if len(sys.argv)>1 else 'baseline.json'),d)
