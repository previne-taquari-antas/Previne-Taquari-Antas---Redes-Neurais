#!/usr/bin/env python3
"""Audit native soil states, water partition and same-parameter ablation."""
import csv,json
from collections import defaultdict
from datetime import datetime,timezone
import numpy as np
import calibrate_mucum_may2024 as m

def main():
 selected=m.load(m.OUT/'selection.json');p=selected['parameters'];ctx=m.prepare();raw=m.ROOT/selected['project']/'native_soil_process_3min.csv';series=defaultdict(dict);units={}
 with raw.open() as f:
  for r in csv.DictReader(f):
   key=(r['element'],r['variable']);t=int(r['time_value']);v=float(r['value'])
   if t in series[key] and abs(series[key][t]-v)>1e-8:raise RuntimeError('Conflicting native process duplicate')
   series[key][t]=v;units[key]=r['units']
 zones={};begin=datetime(2024,5,4,tzinfo=timezone.utc);end=datetime(2024,5,6,tzinfo=timezone.utc)
 for i,z in enumerate(m.ZONES):
  name=m.hms.hec_subbasin_name(z)
  def values(var):return np.array([v for t,v in sorted(series[(name,var)].items())])
  deficit=values('MOISTURE DEFICIT');infil=values('INFILTRATION');perc=values('PERC-SOIL');excess=values('PRECIP-EXCESS');bf=values('FLOW-BASE-1');t=sorted(series[(name,'MOISTURE DEFICIT')]);times=[m.hms.dss_time_to_utc(x) for x in t];saturated=[v for tt,v in zip(times,deficit) if begin<=tt<=end];group=['prata','up','carreiro','down','down'][i];fraction=p.get('gw_fraction_'+group,p['gw_fraction']);area=m.AREAS[i];water_in=sum(perc)*area*1000*fraction;water_out=float(np.trapezoid(bf,dx=180));balance=sum(infil)-sum(perc)-(deficit[0]-deficit[-1]);rain=sum(ctx[1][z][1:]);rain_residual=sum(excess)+sum(infil)-rain
  if abs(balance)>.03 or abs(rain_residual)>.03:raise RuntimeError('Native water partition failed '+z+' '+str((balance,rain_residual)))
  if water_out>water_in*1.001+.01:raise RuntimeError('Subsurface output exceeds allocated percolation '+z)
  zones[z]=dict(native_values=len(t),initial_deficit_mm=float(deficit[0]),final_deficit_mm=float(deficit[-1]),max_deficit_May4_to_May6_mm=float(max(saturated)),native_soil_saturated_during_second_wave=bool(max(saturated)<1e-5),rain_integrated_mm=float(rain),infiltration_mm=float(sum(infil)),percolation_mm=float(sum(perc)),direct_excess_mm=float(sum(excess)),soil_balance_residual_mm=float(balance),rain_partition_residual_mm=float(rain_residual),percolation_to_stream_fraction=fraction,subsurface_inflow_m3=float(water_in),subsurface_outflow_m3=water_out,inferred_subsurface_storage_at_end_m3=float(water_in-water_out))
 sim=m.ind.model(m.ROOT/selected['project']/'hec_output_values.csv','86510000');pairs=m.ind.independent_pairs(sim,ctx[2],'86510000',dict(start_utc=ctx[0][0].isoformat(),end_utc=ctx[0][-1].isoformat()));second=[(t,o,q) for t,o,q in pairs if begin<=t<datetime(2024,5,7,tzinfo=timezone.utc)];obs_peak=max(second,key=lambda r:r[1]);qs=[(t,q) for t,q in sim if begin<=t<datetime(2024,5,7,tzinfo=timezone.utc)];peak_t,peak_q=max(qs,key=lambda r:r[1]);old=m.load(m.OUT/'before_revision2_selection.json');oldsim=m.ind.model(m.ROOT/old['project']/'hec_output_values.csv','86510000');oldpairs=m.ind.independent_pairs(oldsim,ctx[2],'86510000',dict(start_utc=ctx[0][0].isoformat(),end_utc=ctx[0][-1].isoformat()));oldsecond=[(t,o,q) for t,o,q in oldpairs if begin<=t<datetime(2024,5,7,tzinfo=timezone.utc)]
 ab=m.load(m.OUT/'soil_ablation_native.json');audit=dict(event='E27_MAY2024',native_model='Deficit and Constant + Clark + Linear Reservoir + Muskingum',zones=zones,second_wave=dict(window='2024-05-04T00:00Z to 2024-05-07T00:00Z, end exclusive',pairs=len(second),previous_NMAE=sum(abs(o-q) for t,o,q in oldsecond)/sum(o for t,o,q in oldsecond),new_NMAE=sum(abs(o-q) for t,o,q in second)/sum(o for t,o,q in second),observed_hourly_peak_m3s=obs_peak[1],observed_hourly_peak_utc=obs_peak[0].isoformat(),native_peak_m3s=peak_q,native_peak_utc=peak_t.isoformat(),peak_error_pct=100*(peak_q/obs_peak[1]-1),peak_time_h=(peak_t-obs_peak[0]).total_seconds()/3600),ablation=dict(description=ab['ablation_description'],native_metrics=ab['metrics']['86510000'],not_recalibrated=True,causal_interpretation='Shows dependence on subsurface contribution within this calibrated model; not independent proof of actual soil moisture or unique field mechanism.'),interpretation='In this event model, initial soil deficits are exhausted before the second wave; delayed percolation contributes to the river. No artificial dry-state reset between waves. Soil moisture is inferred, not observed.',limitations=['No soil-moisture observations used.','May target and partial JJ observations were used in calibration; no independent event validation.','Maximum deficit 200 mm is fixed and not identifiable without ET extraction.','Some effective surface-response parameters reach bounds; component decomposition is uncertain.'])
 m.save(m.OUT/'soil_hypothesis_audit.json',audit)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 import matplotlib.dates as dates
 fig,axes=plt.subplots(2,1,figsize=(14,9));fig.subplots_adjust(top=.85,bottom=.12,hspace=.42,left=.09,right=.97)
 ax=axes[0]
 for z,label in zip(m.ZONES,['Prata','Antas residual','Carreiro','Santa Tereza residual','Incremento de Muçum']):
  data=sorted(series[(m.hms.hec_subbasin_name(z),'MOISTURE DEFICIT')].items());ax.plot([m.hms.dss_time_to_utc(t) for t,v in data],[v for t,v in data],lw=1.7,label=label)
 ax.axvspan(begin,end,color='#dde8eb',alpha=.5);ax.set_title('Déficit de solo calculado · zero significa saturação na formulação',loc='left',fontweight='bold');ax.set_ylabel('Déficit (mm)');ax.legend(frameon=False,ncol=3,fontsize=9)
 ax=axes[1];ab_sim=m.ind.model(m.ROOT/ab['project']/'hec_output_values.csv','86510000');ax.plot([t for t,q in sim],[q for t,q in sim],color='#85294e',lw=2,label='Modelo completo');ax.plot([t for t,q in ab_sim],[q for t,q in ab_sim],color='#8594a9',lw=1.5,label='Mesmos parâmetros, sem retorno da percolação');ax.scatter([t for t,o,q in pairs],[o for t,o,q in pairs],s=9,color='#273b46',label='Vazão observada');ax.set_xlim(pairs[0][0],pairs[-1][0]);ax.set_ylabel('Vazão em Muçum (m³/s)');ax.set_title('Teste nativo de retirada da contribuição subsuperficial · sem recalibrar',loc='left',fontweight='bold');ax.legend(frameon=False,fontsize=9)
 for ax in axes:
  ax.grid(alpha=.13);ax.spines[['top','right']].set_visible(False);ax.xaxis.set_major_locator(dates.DayLocator(interval=2,tz=m.hms.BRT));ax.xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT));ax.set_xlabel('Abril–maio/2024 · horário de Brasília')
 fig.suptitle('Muçum · hipótese de solo saturado e água armazenada',x=.04,y=.96,ha='left',fontsize=20,fontweight='bold');fig.text(.04,.895,'Estados e vazões do HEC-HMS. O modelo retém a memória da chuva antecedente e encaminha parte da infiltração ao rio.',fontsize=11,color='#43515c');fig.text(.04,.035,'O solo saturado é um estado inferido pelo modelo, sem medida local de umidade. O teste mostra a importância do mecanismo nesta calibração;\nnão comprova que seja a única explicação física. A faixa sombreada destaca 4–6 de maio.',fontsize=9,color='#43515c');fig.savefig(m.OUT/'soil_diagnostic.png',dpi=160,facecolor='white');plt.close(fig)
 print(json.dumps(audit,ensure_ascii=False))
if __name__=='__main__':main()
