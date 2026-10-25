#!/usr/bin/env python3
"""Independently verify V2/V3 pairs; export native projects and audit figures."""
import ast,csv,hashlib,json,os,shutil,sys,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import improve_event_members_v3 as search
import export_mucum_estrela_event_calibration as independent
from finalize_event_members_v3 import acceptable
v=search.v;BRT=timezone(timedelta(hours=-3))

def write_csv(path,rows):
    with path.open('w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def error_line(pairs):
    times=[];errors=[];previous=None
    for t,o,q in pairs:
        if previous is not None and (t-previous).total_seconds()>3600:
            times.append(previous+timedelta(hours=1));errors.append(float('nan'))
        times.append(t);errors.append(q-o);previous=t
    return times,errors

def diagnostics(sim,full,strict,c,window,crest):
    pairs=independent.independent_pairs(sim,full,c,window);calc=independent.metrics(pairs)
    sp=independent.independent_pairs(sim,strict,c,window);sm=independent.metrics(sp)
    peak_t,peak_q=max(sim,key=lambda z:z[1]);rise=[(o,q) for t,o,q in pairs if 0<=(crest-t).total_seconds()/3600<=24]
    fall=[(o,q) for t,o,q in pairs if t>crest]
    return pairs,dict(full_Q_nse=calc['nse'],full_Q_kge=calc['kge'],paired_bias_pct=calc['pbias_pct'],
      full_peak_error_vs_recorded_telemetry_pct=100*(peak_q/max(o for t,o,q in pairs)-1),
      stage_crest_timing_h=(peak_t-crest).total_seconds()/3600,
      rising_limb_nmae=sum(abs(q-o) for o,q in rise)/sum(o for o,q in rise),
      recession_nmae=sum(abs(q-o) for o,q in fall)/sum(o for o,q in fall),
      strict_domain_nse=sm['nse'],strict_domain_nmae=sum(abs(q-o) for t,o,q in sp)/sum(o for t,o,q in sp),
      paired_Q_nmae=sum(abs(q-o) for t,o,q in pairs)/sum(o for t,o,q in pairs),pairs=len(pairs))

def main():
    v.OUT=search.OUT
    dest=Path(sys.argv[1]).resolve();dest.mkdir(parents=True,exist_ok=True)
    s=v.load(v.OUT/'selected_models.json');full=v.load(v.OUT/'full_Q_clock_corrected.json');strict=v.load(v.OUT/'strict_Q_domain.json')
    pack=dest/'HEC_Mucum_Estrela_modelos_2026-10-24'
    if pack.exists():shutil.rmtree(pack)
    pack.mkdir();records=[];paired=[];index=[];tables=[]
    fig,axes=plt.subplots(2,3,figsize=(18,9));fig.subplots_adjust(left=.058,right=.987,top=.84,bottom=.16,hspace=.43,wspace=.24)
    for i,r in enumerate(s['selected']):
        c=r['target_code'];city=r['target_name'];rp=v.ROOT/r['result_file'];native=v.load(rp)
        crest=v.hms.utc(s['original_level_crests'][c]['time_utc'])
        output=rp.parent/'project/hec_output_values.csv'
        start=v.hms.utc(native['window']['start_utc']);end=v.hms.utc(native['window']['end_utc'])
        expected=int((end-start).total_seconds()/180)+1
        for checkpoint in v.hms.MAIN_CHECKPOINTS:
            values=independent.model(output,checkpoint)
            if len(values)!=expected or values[0][0]!=start or values[-1][0]!=end:raise RuntimeError('Incomplete native checkpoint '+checkpoint)
            if any(not np.isfinite(q) or q<0 for t,q in values):raise RuntimeError('Nonfinite or negative native flow')
            if any((t2-t1).total_seconds()!=180 for (t1,q1),(t2,q2) in zip(values,values[1:])):raise RuntimeError('Native interval gap')
        sim=independent.model(output,c)
        b=next(b for b in s['baseline'] if b['target_code']==c)
        # A true copy of the previously delivered V2 series, not a substitute fit.
        bp=v.OUT/'baseline_v2_delivered'/f'{c}.csv';before=independent.model(bp,c)
        pairs,after=diagnostics(sim,full,strict,c,native['window'],crest)
        before_pairs,prior=diagnostics(before,full,strict,c,native['window'],crest)
        for label,metrics,row in [('V2',prior,b),('V3',after,r)]:
            for key,value in row['metrics'][c].items():
                if key in metrics and abs(metrics[key]-value)>1e-8:raise RuntimeError('Independent mismatch '+label+' '+city+' '+key)
            if abs(metrics['recession_nmae']-row['refinement_metrics']['recession_nmae'])>1e-8:raise RuntimeError('Recession mismatch')
            records.append(dict(city=city,event_id=v.EVENT,version=label,**metrics))
        if not acceptable(r,b):raise RuntimeError('V3 export cannot regress joint selection criteria')
        key=('MUCUM' if c=='86510000' else 'ESTRELA')+'_E24_NOV2023_V3';case=pack/key
        shutil.copytree(rp.parent/'project',case)
        for p in case.iterdir():
            if p.is_file() and (p.name=='run.script' or p.suffix in ['.log','.access','.pending']):p.unlink()
        v.save(case/'parametros_resultados.json',dict(city=city,event_id=v.EVENT,parameters=r['parameters'],independent_metrics=after,native_result=native))
        script=(rp.parent/'project/run.script').read_text();line=next(x for x in script.splitlines() if x.startswith('source_values='))
        effective=ast.literal_eval(line.split('=',1)[1])['86472000'];axis=v.hms.hourly_axis(v.hms.utc(native['window']['start_utc']),v.hms.utc(native['window']['end_utc']))
        raw=v.load(v.BASE/'historical_calibration_forcing'/v.EVENT/'hydro.json');original=v.hms.source_hourly(raw,'86472000',axis)
        storage=native.get('upstream_boundary_overbank_storage_experiment')
        remaining=storage['remaining_storage_m3'] if storage else 0.
        balance=float(np.sum(np.array(original)-np.array(effective))*3600-remaining)
        if abs(balance)>max(1.,sum(original)*3600)*1e-9:raise RuntimeError('Independent effective-source water balance failed')
        v.save(case/'auditoria_entrada_montante.json',dict(input_interval='hourly interval means; rectangular integration, matching conceptual storage solver',remaining_storage_m3=remaining,independent_balance_error_m3=balance,physical_hypothesis_validated=False))
        write_csv(case/'montante_original_e_entrada_modelo.csv',[dict(time_utc=v.v1.iso(t),original_observed_Q_m3s=a,effective_model_input_Q_m3s=e) for t,a,e in zip(axis,original,effective)])
        peakv=after['full_peak_error_vs_recorded_telemetry_pct'];risev=100*after['rising_limb_nmae'];fallv=100*after['recession_nmae']
        tables.append(f'| {city} | {prior["full_Q_nse"]:.4f} → {after["full_Q_nse"]:.4f} | {100*prior["rising_limb_nmae"]:.2f}% → {risev:.2f}% | {100*prior["recession_nmae"]:.2f}% → {fallv:.2f}% | {peakv:+.2f}% |')
        for t,o,q in pairs:paired.append(dict(city=city,time_utc=v.v1.iso(t),observed_telemetry_Q_m3s=o,V2_simulated_Q_m3s=dict(before)[t],V3_simulated_Q_m3s=q,within_strict_domain=t in v.hms.target_hourly(strict,c,axis)))
        index.append(dict(city=city,event_id=v.EVENT,model_key=key,native_project=key+'/g040_e1_hindcast.hms',fit_only=True,operationally_validated=False))
        obs=next(x for x in full['controls'] if str(x['code'])==c)['recent_rows']
        observed=[(v.hms.utc(x['time_utc']),x['flow_m3s'],x.get('level_source_unit')) for x in obs if x.get('flow_m3s') is not None]
        for j,ax in enumerate(axes[i]):
            if j<2:
                ax.plot([t for t,q in before],[q for t,q in before],color='#b98335',lw=1.4,label='V2 entregue')
                ax.plot([t for t,q in sim],[q for t,q in sim],color='#087c83',lw=1.9,label='V3 por cidade/evento')
                for uncertain in [False,True]:
                    rr=[(t,q) for t,q,h in observed if (c=='86510000' and (h is None or h>1500))==uncertain]
                    if rr:ax.scatter([t for t,q in rr],[q for t,q in rr],s=13 if j==0 else 21,facecolors='white' if uncertain else '#283849',edgecolors='#8c99a5' if uncertain else '#283849',label='Muçum >15 m: curva incerta' if uncertain else 'Telemetria disponível',zorder=4)
                ax.set_ylabel('Vazão (m³/s)')
                if j==1:ax.set_xlim(crest-timedelta(hours=24),crest+timedelta(hours=18))
                ax.axvline(crest,color='#8e99a2',ls=':',lw=1)
            else:
                ax.axhline(0,color='#7c8793',lw=.8)
                ax.plot(*error_line(before_pairs),color='#b98335',lw=1.3,label='Erro V2')
                ax.plot(*error_line(pairs),color='#087c83',lw=1.6,label='Erro V3')
                ax.set_xlim(crest,v.hms.utc(native['window']['end_utc']));ax.set_ylabel('Simulado − telemetria (m³/s)')
                ax.text(.02,.98,f'MAE relativo após a crista\n{100*prior["recession_nmae"]:.2f}% → {fallv:.2f}%',va='top',transform=ax.transAxes,fontsize=10,bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
            ax.set_title(city+' · '+['evento completo','subida e pico','erro na recessão'][j],loc='left',fontweight='bold',fontsize=12)
            ax.grid(axis='y',alpha=.17);ax.spines[['top','right']].set_visible(False)
            if j==1:
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=12,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%Hh',tz=BRT))
            else:
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=2,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=BRT))
            ax.set_xlabel('Novembro/2023 · horário de Brasília')
            if j==0:ax.legend(loc='upper right',fontsize=7,frameon=False)
        axes[i,1].text(.02,.98,f'V3: subida {risev:.2f}% · pico {peakv:+.2f}%',va='top',transform=axes[i,1].transAxes,fontsize=10,bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
    fig.suptitle('Muçum e Estrela · refinamento V3 por cidade e evento',x=.025,y=.975,ha='left',fontweight='bold',fontsize=20)
    fig.text(.025,.916,'Mesma chuva, montante, observações e período da V2. Seleção exige melhora conjunta da subida, recessão e NSE.',fontsize=12,color='#4d5b67')
    fig.text(.025,.037,'Calibração retrospectiva de novembro/2023. Muçum: relógio −105 min; vazões >15 m dependem de curva-chave incerta; armazenamento lateral conceitual.\nEstrela: 142/240 h com Q; lacuna não preenchida. Chuva: mediana de 3 postos/h. Observações horárias. Projetos E1 por ramos; sem validação de previsão em tempo real.',fontsize=9,color='#4d5b67')
    image=dest/'HEC_Mucum_Estrela_calibracao_2026-10-24.png';fig.savefig(image,dpi=170,facecolor='white');plt.close(fig)
    shutil.copy2(image,pack/'comparacao_V2_V3.png')
    write_csv(pack/'comparacao_V2_V3.csv',records);write_csv(pack/'pares_observado_simulado.csv',paired);write_csv(pack/'biblioteca_cidade_evento.csv',index)
    trials=v.load(v.OUT/'refinement_evaluations.json')
    chosen={(r['target_code'],r['run_id']) for r in s['selected']}
    screening=[dict(city=r['target_name'],event_id=v.EVENT,run_id=r['run_id'],selected=(r['target_code'],r['run_id']) in chosen,
        refinement_objective=r['refinement_objective'],**r['metrics'][r['target_code']],recession_nmae=r['refinement_metrics']['recession_nmae']) for r in trials]
    write_csv(v.OUT/'screening_summary.csv',screening);shutil.copy2(v.OUT/'screening_summary.csv',pack/'screening_summary.csv')
    for f in ['selection_manifest.json','native_water_budget_audit.json']:shutil.copy2(v.OUT/f,pack/f)
    notes='''# HEC-HMS — revisão V3, Muçum e Estrela

Dois modelos independentes, calibrados para novembro/2023 (E24 q62 / E12 Muçum 2h). Não se exige que um conjunto de parâmetros funcione em outra cheia ou cidade.

## Comparação com a V2 realmente entregue

| Cidade | NSE completo | Erro relativo na subida | Erro relativo após a crista | Erro do pico V3 |
| --- | --- | --- | --- | --- |
'''+ '\n'.join(tables)+'''

Os erros relativos por trecho são soma dos erros absolutos dividida pela soma das vazões observadas nos pares disponíveis. Subida: 24h antes da crista de nível; recessão: todos os pares depois da crista. Não são média dos erros percentuais horários. O NSE e o viés usam somente os pares disponíveis. O pico usa o máximo da série simulada completa e o máximo da telemetria disponível, na mesma base da V2.

`comparacao_V2_V3.csv` inclui os valores exatos, NSE restrito, viés e erro de horário. A comparação é recalculada com NumPy, independentemente do cálculo de seleção, contra uma cópia da saída nativa efetivamente entregue na V2. Não se exige melhora em todos os indicadores: NSE completo e MAE relativo completo, da subida e da recessão não podem piorar; em Muçum também não podem regredir NSE e MAE até 15m. Pico deve ficar até 2%, horário até 0,75h e viés até 2%; Estrela deve cumprir a restrição por nível.

A busca gera candidatos minimizando resíduos quadráticos normalizados, com pesos explícitos no manifesto. A seleção para entrega prioriza equilíbrio entre trechos: entre candidatos aprovados, minimiza a maior razão MAE_V3/MAE_V2 dos trechos (completo, subida, recessão e, em Muçum, até 15m). Empates usam média das razões e depois o objetivo quadrático. Isso impede que um grande ganho em um trecho esconda um ganho pequeno nos demais. É uma seleção com o evento de calibração inteiro; não é avaliação independente.

## Abrir e executar

HEC-HMS 4.13: abra `g040_e1_hindcast.hms` dentro de cada pasta e compute `Hindcast`. Cada projeto leva seus DSS de entrada e referências relativas. Os dois projetos foram copiados para pastas isoladas e computados novamente, em série. Todos os seis controles devem ter 4.781 valores a cada 3min e métricas iguais às da seleção. Os parâmetros exatos e resultados nativos estão no JSON da respectiva cidade. Arquivos temporários e scripts com caminhos absolutos foram removidos do pacote.

Muçum usa SCS, recessão, Muskingum e armazenamento lateral conceitual causal aplicado à entrada de montante. A série efetiva acompanha o DSS. O CSV `montante_original_e_entrada_modelo.csv` conserva a distinção entre observado original e entrada efetiva; não se reclassifica a entrada modificada como medição. Para regenerar essa entrada a partir dos dados originais, use o gerador de projetos e os parâmetros no PR associado. Estrela usa perdas Initial+Constant, Clark, recessão e Muskingum; CN/lag legados em seus argumentos são ignorados por Initial+Constant/Clark.

## Limites da interpretação

Domínio E1 BHO6 por ramos de Linha José Júlio a Porto Mariante, diferente do projeto original completo de 145 sub-bacias. Chuva e vazão de montante de todo o evento são conhecidas: é ajuste retrospectivo, sem comprovação de previsão em tempo real. A chuva tem mediana de três postos por hora e pode produzir compensação entre parâmetros. Não há promoção operacional.

Muçum: correção de relógio de −105min somente na observação para comparação, seguindo o QA fornecido e dentro da vigência documentada; observados e entradas originais não foram sobrescritos. NSE até 15m permanece separado. As vazões de cotas maiores dependem da curva-chave da telemetria; bom ajuste não confirma independentemente a vazão extrema. Armazenamento lateral é hipótese conceitual, sem geometria hidráulica medida. A auditoria de componentes é uma checagem numérica e de escala, não validação física da planície ou aquífero.

Estrela: 142/240h de Q disponíveis, com lacuna de 63h. Nenhuma Q ausente foi inventada; em 32h de nível baixo sem Q, usa-se apenas o limite superior decorrente da monotonicidade da mesma relação nível/vazão, com tolerância de 10%. Observações são horárias; diferenças de minutos na saída de 3min não representam precisão de campo.

Os parâmetros foram escolhidos usando este mesmo evento completo. Os ganhos informados são de calibração; não são resultados de validação independente. Cada evento futuro deve ser identificado por seu próprio membro e por sua evidência.
'''
    (pack/'LEIA-ME.md').write_text(notes)
    v.save(pack/'sha256.json',{str(f.relative_to(pack)):hashlib.sha256(f.read_bytes()).hexdigest() for f in pack.rglob('*') if f.is_file()})
    archive=dest/(pack.name+'.zip');pending=archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pack.rglob('*')):
            if f.is_file():z.write(f,str(f.relative_to(dest)))
    with zipfile.ZipFile(pending) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failure')
    with pending.open('rb') as fh:os.fsync(fh.fileno())
    pending.replace(archive);v.save(v.OUT/'comparison_independent.json',records)
    shutil.copy2(pack/'LEIA-ME.md',v.ROOT/'docs/HEC_EVENTOS_V3_20261024.md')
    print(json.dumps(dict(archive=str(archive),image=str(image),comparison=records),ensure_ascii=False))

if __name__=='__main__':main()
