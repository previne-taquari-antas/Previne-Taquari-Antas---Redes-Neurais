import csv,json,shutil,subprocess,zipfile,hashlib
from pathlib import Path
from datetime import timedelta
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as dates
from PIL import Image
import calibrate_estrela_may2024 as m
from verify_mucum_may2024 import export_script
ctx=m.prepare();d=m.load(m.OUT/'latest_native.json');base=m.load(m.OUT/'baseline.json');src=m.ROOT/d['project'];proj=m.OUT/'verified/project';proj.parent.mkdir(parents=True,exist_ok=True)
if proj.exists():shutil.rmtree(proj)
shutil.copytree(src,proj);(proj/'output.dss').unlink();(proj/'run.script').write_text(export_script(proj));hec=m.ROOT.parent/'runtime/HEC-HMS-4.13/hec-hms.sh';cp=subprocess.run([str(hec),'-s',str(proj/'run.script')],cwd=hec.parent,capture_output=True,text=True,timeout=300);(proj.parent/'compute.log').write_text(cp.stdout+'\n'+cp.stderr);assert 'MAY_EXISTING_DSS_COMPUTE_OK' in cp.stdout
new=m.evaluate(proj,ctx);before=m.hms.read_output_csv(src/'hec_output_values.csv');after=m.hms.read_output_csv(proj/'hec_output_values.csv')
for name in after:
 assert len(after[name])==len(before[name]) and max(abs(q-v) for (t,q),(u,v) in zip(after[name],before[name]))<1e-8
source=dict(after['SRC_86510000']);source_error=max(abs(source[t]-q) for t,q in zip(ctx[0],ctx[1]));assert source_error<.01
rain=list(csv.DictReader((proj/'native_rain_values.csv').open()));rain_errors={}
for z in m.ZONES:
 v={m.hms.dss_time_to_utc(r['time_value']):float(r['mm']) for r in rain if r['zone']==z};error=max(abs(v[t]-q) for t,q in zip(ctx[0],ctx[2][z]));assert error<1e-4;rain_errors[z]=error
assert new['nse']>base['metrics']['nse'] and new['low_stage_bound_pass'];d.update(project=str(proj.relative_to(m.ROOT)),metrics=new,verification=dict(isolated_native_recompute=True,values_per_element=6221,paired_actual_Q=132,stage_only_upper_bound_times=54,source_hourly_max_error_m3s=source_error,rain_max_errors_mm=rain_errors,target_observation_absent_from_forcing=True,only_source='86510000',clock_shift_minutes=0));m.save(m.OUT/'selection.json',d)
dest=m.ROOT.parent/'deliverables_estrela';dest.mkdir(exist_ok=True);name='Estrela_HEC_Maio2024_2026-10-24';pack=dest/name
if pack.exists():shutil.rmtree(pack)
pack.mkdir();sims={};records=[]
for key,data,folder in [('baseline',base,'REFERENCIA_MAIO'),('selected',d,'HEC_ESTRELA_MAIO2024_CALIBRADO')]:
 path=m.ROOT/data['project'];shutil.copytree(path,pack/folder)
 for p in (pack/folder).iterdir():
  if p.suffix in ['.script','.log','.access']:p.unlink()
  elif p.suffix in ['.hms','.run','.gage','.basin','.met','.control']:assert '/workspace/' not in p.read_text()
 m.save(pack/folder/'parametros_metricas.json',data);sims[key]=m.ind.model(path/'hec_output_values.csv','86879300');pairs=m.ind.independent_pairs(sims[key],ctx[4],'86879300',dict(start_utc=ctx[0][0].isoformat(),end_utc=ctx[0][-1].isoformat()));ind=m.ind.metrics(pairs)
 for k in ['nse','kge','pbias_pct','rmse_m3s']:assert abs(ind[k]-data['metrics'][k])<1e-8
 records.extend([dict(model=key,time_utc=t.isoformat(),observed_Q_m3s=o,native_Q_m3s=q) for t,o,q in pairs])
with (pack/'pares_reais.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
inputs=pack/'ENTRADAS_E_AUDITORIA';inputs.mkdir()
for n in ['rain.json','hydro.json','scenario.json']:shutil.copy2(m.FORCING/n,inputs/n)
for n in ['selection.json','baseline.json','screening.json','selected_parameters.json','input_audit.json']:shutil.copy2(m.OUT/n,inputs/n)
code=pack/'CODIGO';code.mkdir()
for n in ['calibrate_estrela_may2024.py','search_estrela_may2024.py','export_estrela_may2024.py','search_mucum_may2024.py','calibrate_mucum_may2024.py','export_mucum_estrela_event_calibration.py','run_hec_hms_g040_e1_hindcast.py','g040_overbank_storage.py','verify_mucum_may2024.py']:shutil.copy2(m.ROOT/'scripts'/n,code/n)
rr=next(c for c in ctx[4]['controls'] if c['code']=='86879300')['recent_rows'];obs=[r for r in rr if r['flow_m3s'] is not None];old=base['metrics'];fig,axes=plt.subplots(2,2,figsize=(16,10));fig.subplots_adjust(top=.84,bottom=.12,left=.07,right=.97,hspace=.4,wspace=.25)
for ax in [axes[0,0],axes[0,1],axes[1,0]]:
 for k,label,color in [('baseline','Referência própria · mesmos dados','#8d9bab'),('selected','Calibrado para Estrela · HEC-HMS','#266c7a')]:ax.plot([t for t,q in sims[k]],[q for t,q in sims[k]],label=label,color=color,lw=1.8)
 ax.scatter([m.hms.utc(r['time_utc']) for r in obs],[r['flow_m3s'] for r in obs],color='#273b46',s=12,zorder=4,label='Q arquivado · 132 horas reais');ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False);ax.set_ylabel('Vazão (m³/s)');ax.xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT))
axes[0,0].set_xlim(ctx[0][0],ctx[0][-1]);axes[0,0].set_title('Evento completo · lacunas observadas preservadas',loc='left',fontweight='bold');axes[0,0].legend(fontsize=8,frameon=False)
peak=m.hms.utc(new['peak_utc']);axes[0,1].xaxis.set_major_formatter(dates.DateFormatter('%d/%m\n%Hh',tz=m.hms.BRT));axes[0,1].set_ylim(12000,27000);axes[0,1].set_xlim(peak-timedelta(hours=24),peak+timedelta(hours=24));axes[0,1].set_title('Pico principal',loc='left',fontweight='bold');axes[0,1].text(.03,.97,f"NSE {old['nse']:.4f} → {new['nse']:.4f}\nErro do pico {old['peak_error_pct']:+.2f}% → {new['peak_error_pct']:+.2f}%",va='top',transform=axes[0,1].transAxes,bbox=dict(facecolor='white',alpha=.9,edgecolor='none'),fontweight='bold')
axes[1,0].set_xlim(m.hms.utc('2024-05-04T00:00Z'),ctx[0][-1]);axes[1,0].set_title('Recessão e controle nas lacunas',loc='left',fontweight='bold');bound=ctx[6]['low_stage_constraint'];axes[1,0].scatter([m.hms.utc(t) for t in bound['times_utc']],[bound['Q_upper_bound_m3s']]*54,marker='v',s=18,color='#bd8750',label='Teto por nível baixo · não é Q medido');axes[1,0].legend(fontsize=8,frameon=False)
ax=axes[1,1];ax.axis('off');ax.set_title('Comparação nativa · mesmos 132 pares',loc='left',fontweight='bold');rows=[]
for label,k,scale,fmt in [('NSE','nse',1,'.4f'),('KGE','kge',1,'.4f'),('RMSE (m³/s)','rmse_m3s',1,'.1f'),('Viés (%)','pbias_pct',1,'+.2f'),('Erro do pico (%)','peak_error_pct',1,'+.2f'),('Defasagem do pico (h)','peak_time_h',1,'+.2f'),('Erro na subida (%)','rising_NMAE',100,'.2f'),('Erro na recessão (%)','recession_NMAE',100,'.2f')]:rows.append([label,format(old[k]*scale,fmt),format(new[k]*scale,fmt)])
t=ax.table(cellText=rows,colLabels=['Indicador','Referência','Calibrado'],colWidths=[.55,.23,.22],bbox=[0,.12,1,.83],cellLoc='left');t.auto_set_font_size(False);t.set_fontsize(10)
for (r,c),cell in t.get_celld().items():
 cell.set_edgecolor('white');cell.set_facecolor('#e7eff1' if r==0 else '#f4f7f8' if r%2 else 'white')
 if r==0 or c==2:cell.set_text_props(fontweight='bold')
fig.suptitle('Estrela · maio/2024 · calibração própria no HEC-HMS',x=.035,y=.965,ha='left',fontsize=20,fontweight='bold');fig.text(.035,.902,'Muçum observado na entrada · chuva em seis zonas laterais · parâmetros próprios para Estrela · passo nativo de 3 min.',fontsize=11,color='#43515c');fig.text(.035,.025,'Calibração histórica condicionada às observações de montante. Não é validação independente nem previsão antecipada.\nQ extremo depende da curva-chave; as lacunas não foram preenchidas e os níveis não foram convertidos em novos alvos de vazão.',fontsize=9,color='#43515c');png=dest/(name+'.png');fig.savefig(png,dpi=160);plt.close(fig);Image.open(png).verify();shutil.copy2(png,pack/png.name)
notes=f'''# Estrela — maio de 2024

Abra HEC_ESTRELA_MAIO2024_CALIBRADO/g040_e1_hindcast.hms e compute Hindcast.

Modelo próprio para Estrela (86879300), calibrado em 132 vazões arquivadas de maio/2024, com Muçum (86510000) como entrada observada completa de 312 horas. As áreas integradas por Muçum não são novamente somadas como chuva local. As seis zonas laterais somam {sum(ctx[3].values()):.3f} km² de suporte regional. Não se transferiram os parâmetros calibrados de Muçum. A comparação é com o ponto de partida da mesma arquitetura e dos mesmos dados, não com um evento independente.

NSE: {old['nse']:.6f} → {new['nse']:.6f}; KGE {new['kge']:.6f}; RMSE {old['rmse_m3s']:.1f} → {new['rmse_m3s']:.1f} m³/s; viés {new['pbias_pct']:+.3f}%; pico {new['peak_error_pct']:+.3f}%, defasagem {new['peak_time_h']:+.2f} h; NMAE da subida {new['rising_NMAE']*100:.2f}% e recessão {new['recession_NMAE']*100:.2f}%.

Deficit and Constant / Clark / Linear Reservoir, propagação Muskingum X=0. As respostas de Guaporé, Forqueta e residuais são calibradas separadamente, constantes ao longo do evento. Foram comparadas cascatas de 2, 4, 6 e 8 reservatórios. Parâmetros efetivos de um evento, sem medições de solo ou novas planícies medidas. O máximo de déficit é fixado em 200 mm e não é identificável sem ET nesta configuração. Alguns parâmetros atingem limites de busca. Não há pretensão de identificar mecanismos físicos únicos nem transferência entre cidades/eventos.

186 horários têm nível; 54 sem Q estão abaixo do menor nível com Q pareado. Sob a hipótese de monotonicidade da mesma relação arquivada, eles fornecem somente teto de Q de {bound['Q_upper_bound_m3s']} m³/s. Excesso máximo do modelo nesse teto: {new['low_stage_bound_exceedance']*100:.2f}%, dentro da tolerância de 10% adotada. Nenhuma Q foi inventada para preencher a lacuna. Não se afirma acurácia de nível pelo HEC-HMS, que aqui simula vazão. Vazões extremas dependem da curva-chave; marcas niveladas não são vazões medidas.

Verificação: recomputação nativa em pasta isolada com DSS existentes; 6.221 valores de 3 min por elemento; métricas por caminho independente; conferência de todas as chuvas e 312 valores da entrada Muçum, erro máximo {source_error:.6f} m³/s. A única Source é Muçum; a observação de Estrela nunca entra na simulação. Relógio bruto preservado; incerteza histórica do relógio de montante pode afetar tempos calibrados, que não são medidas de velocidade. Horas sem Q não contam como pares de validação.

Esta é uma calibração do evento completo, condicionada à chuva e à vazão futura de montante conhecidas retrospectivamente; não é desempenho de previsão antecipada. Muçum e novembro mantêm seus modelos separados. Não houve publicação operacional.

Fontes: arquivo histórico ANA/SGB E27_MAY2024, cópias integrais em ENTRADAS_E_AUDITORIA; chuva espacializada original da rede em rain.json. USACE, Deficit and Constant Loss Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/deficit-and-constant-loss-model ; Linear Reservoir Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/linear-reservoir-model .
''';(pack/'LEIA-ME.md').write_text(notes);m.save(pack/'sha256.json',{str(p.relative_to(pack)):hashlib.sha256(p.read_bytes()).hexdigest() for p in pack.rglob('*') if p.is_file()})
archive=dest/(name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in pack.rglob('*'):
  if p.is_file():z.write(p,str(p.relative_to(dest)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps(dict(archive=str(archive),image=str(png),metrics=new)))
