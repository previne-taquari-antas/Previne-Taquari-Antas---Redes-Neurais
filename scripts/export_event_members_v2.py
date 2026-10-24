#!/usr/bin/env python3
"""Independent metrics, event/city model archive, and full/crest comparisons."""
import argparse,ast,csv,hashlib,json,shutil,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import calibrate_event_members_v2 as v
import export_mucum_estrela_event_calibration as independent

BRT=timezone(timedelta(hours=-3))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('destination',type=Path);args=ap.parse_args()
    dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=True)
    s=v.load(v.OUT/'selected_models.json');full=v.load(v.OUT/'full_Q_clock_corrected.json');strict=v.load(v.OUT/'strict_Q_domain.json')
    pack=dest/'HEC_Mucum_Estrela_modelos_2026-10-24';pack.mkdir(exist_ok=True)
    records=[];paired=[];index=[]
    fig,axes=plt.subplots(2,2,figsize=(15.5,9.2));fig.subplots_adjust(left=.065,right=.985,top=.86,bottom=.16,hspace=.39,wspace=.16)
    for i,r in enumerate(s['selected']):
        c=r['target_code'];city=r['target_name'];rp=v.ROOT/r['result_file'];native=v.load(rp)
        sim=independent.model(rp.parent/'project/hec_output_values.csv',c)
        pairs=independent.independent_pairs(sim,full,c,native['window']);calc=independent.metrics(pairs)
        strict_m=independent.metrics(independent.independent_pairs(sim,strict,c,native['window']))
        for k in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(calc[k]-r['scores'][c][k])>1e-8:raise RuntimeError('Independent metric mismatch '+city+' '+k)
        if abs(strict_m['nse']-r['metrics'][c]['strict_domain_nse'])>1e-8:raise RuntimeError('Strict domain mismatch')
        baseline=next(b for b in s['baseline'] if b['target_code']==c);bp=v.ROOT/baseline['result_file']
        delivered_baseline=v.OUT/'baseline_v1_delivered'/f'{c}.csv'
        before=independent.model(delivered_baseline if delivered_baseline.exists() else bp.parent/'project/hec_output_values.csv',c)
        bcalc=independent.metrics(independent.independent_pairs(before,full,c,native['window']))
        if abs(bcalc['nse']-baseline['metrics'][c]['full_Q_nse'])>1e-8:
            raise RuntimeError('Delivered V1 baseline does not match the common evaluation base')
        crest=v.hms.utc(s['original_level_crests'][c]['time_utc'])
        peak_t,peak_q=max(sim,key=lambda t:t[1]);o=np.array([o for t,o,q in pairs])
        peak_error=100*(peak_q/o.max()-1)
        rise=[(o,q) for t,o,q in pairs if 0<=(crest-t).total_seconds()<=24*3600]
        rise_error=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise)
        if abs(peak_error-r['metrics'][c]['full_peak_error_vs_recorded_telemetry_pct'])>1e-8:raise RuntimeError('Peak recomputation mismatch')
        if abs(rise_error-r['metrics'][c]['rising_limb_nmae'])>1e-8:raise RuntimeError('Rising limb recomputation mismatch')
        for label,metrics in [('V1',baseline['metrics'][c]),('V2',r['metrics'][c])]:
            records.append(dict(city=city,event='novembro/2023',version=label,**metrics))
        key=('MUCUM' if c=='86510000' else 'ESTRELA')+'_E24_NOV2023_V2'
        case=pack/key
        if case.exists():shutil.rmtree(case)
        shutil.copytree(rp.parent/'project',case)
        for f in list(case.iterdir()):
            if f.is_file() and (f.name=='run.script' or f.suffix in ['.log','.access']):f.unlink()
        v.save(case/'parametros_resultados.json',dict(model_key=key,event_id=v.EVENT,city=city,parameters=r['parameters'],metrics=r['metrics'][c],native_result=native))
        # Derived audit series: never overwrite the original upstream hydro.
        script=(rp.parent/'project/run.script').read_text()
        line=next(x for x in script.splitlines() if x.startswith('source_values='))
        source=ast.literal_eval(line.split('=',1)[1])['86472000']
        axis=v.hms.hourly_axis(v.hms.utc(native['window']['start_utc']),v.hms.utc(native['window']['end_utc']))
        raw=v.load(v.BASE/'historical_calibration_forcing'/v.EVENT/'hydro.json');original=v.hms.source_hourly(raw,'86472000',axis)
        with (case/'montante_original_e_entrada_modelo.csv').open('w',newline='') as fh:
            w=csv.writer(fh);w.writerow(['time_utc','original_observed_Q_m3s','effective_model_input_Q_m3s'])
            w.writerows((v.v1.iso(t),a,b) for t,a,b in zip(axis,original,source))
        for t,o,q in pairs:paired.append(dict(city=city,time_utc=v.v1.iso(t),observed_telemetry_Q_m3s=o,simulated_Q_m3s=q))
        index.append(dict(city=city,event_id=v.EVENT,model_key=key,family=r['family'],native_project=key+'/g040_e1_hindcast.hms',calibration=True,independent_forecast_validation=False))
        control=next(x for x in full['controls'] if str(x['code'])==c)
        obs=[(v.hms.utc(x['time_utc']),x['flow_m3s'],x.get('level_source_unit')) for x in control['recent_rows'] if x.get('flow_m3s') is not None]
        for j,ax in enumerate(axes[i]):
            ax.plot([t for t,q in before],[q for t,q in before],color='#c98936',lw=1.55,label='V1 entregue')
            ax.plot([t for t,q in sim],[q for t,q in sim],color='#067788',lw=2,label='V2 calibrado por evento')
            low=[(t,q) for t,q,h in obs if c!='86510000' or (h is not None and h<=1500)]
            high=[(t,q) for t,q,h in obs if c=='86510000' and (h is None or h>1500)]
            ax.scatter([t for t,q in low],[q for t,q in low],s=10 if j==0 else 20,color='#293747',label='Telemetria usada na comparação',zorder=4)
            if high:ax.scatter([t for t,q in high],[q for t,q in high],s=18 if j==0 else 27,facecolors='white',edgecolors='#8794a1',label='Muçum >15 m: curva-chave incerta',zorder=4)
            ax.axvline(crest,ls=':',color='#8895a1',lw=1,label='Hora da crista de nível disponível')
            ax.set_title(city+(' · evento completo' if j==0 else ' · subida e pico'),loc='left',fontweight='bold',fontsize=13)
            ax.set_ylabel('Vazão (m³/s)');ax.grid(axis='y',alpha=.16);ax.spines[['top','right']].set_visible(False)
            if j==0:
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=2,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=BRT))
                ax.legend(loc='upper right',fontsize=7.5,frameon=False)
            else:
                ax.set_xlim(crest-timedelta(hours=24),crest+timedelta(hours=18))
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=6,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%Hh',tz=BRT))
                m=r['metrics'][c]
                ax.text(.02,.96,f'V2: erro do pico {m["full_peak_error_vs_recorded_telemetry_pct"]:+.1f}%\nerro relativo na subida {100*m["rising_limb_nmae"]:.1f}%',transform=ax.transAxes,va='top',fontsize=10,
                    bbox=dict(facecolor='white',alpha=.85,edgecolor='none'))
        for ax in axes[i]:ax.set_xlabel('Novembro de 2023 · horário de Brasília')
    fig.suptitle('Muçum e Estrela · novos modelos por cidade e evento',fontsize=19,fontweight='bold',x=.025,ha='left',y=.975)
    fig.text(.025,.918,'Comparação na mesma base de telemetria e no mesmo evento de novembro/2023; foco na subida, no pico e na recessão.',fontsize=11,color='#465564')
    fig.text(.025,.035,'Calibração retrospectiva: chuva e vazão de montante conhecidas. Muçum: correção de relógio de −105 min; grandes vazões dependem da curva da telemetria.\nEstrela: 142/240 h de Q disponíveis; checagem adicional por nível em 32 h sem Q. Chuva: mediana de 3 postos/h. Horários observados têm resolução horária.',fontsize=9,color='#495662')
    image=dest/'HEC_Mucum_Estrela_calibracao_2026-10-24.png';fig.savefig(image,dpi=170,facecolor='white');plt.close(fig)
    for filename,rows in [('comparacao_V1_V2.csv',records),('pares_observado_simulado.csv',paired),('biblioteca_cidade_evento.csv',index)]:
        with (pack/filename).open('w',newline='') as fh:w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    for filename in ['selected_models.json','native_water_budget_audit.json']:
        q=v.OUT/filename
        if q.exists():shutil.copy2(q,pack/filename)
    notes='''# HEC-HMS — biblioteca por cidade e evento, revisão V2

Evento: novembro/2023 (E24 do catálogo q62, E12 do catálogo Muçum 2h). Cada cidade tem parâmetros próprios. O bom ajuste de um evento não é condição para transferir o mesmo conjunto a outra cheia.

Abra o arquivo `g040_e1_hindcast.hms` dentro da pasta de cada cidade no HEC-HMS 4.13 e execute `Hindcast`. O DSS de entrada acompanha o projeto; as referências de execução são relativas. Os parâmetros e resultados estão em `parametros_resultados.json`; os pares e a comparação com a V1 estão nos CSVs.

## O que foi melhorado

- Comparação com toda a vazão de telemetria disponível, na mesma base antes/depois. A avaliação de Muçum até 15 m continua separada; a curva-chave das grandes cotas não foi transformada em medição de descarga independente.
- Subida avaliada nas 24 h anteriores à crista de nível registrada. Erro da crista, viés nos pares e recessão entram na seleção; o NSE não decide sozinho.
- Testes de perdas Initial+Constant e transformação Clark, além de SCS; calibração da propagação e testes do número de subtrechos Muskingum, sempre com coeficientes estáveis.
- Muçum pode usar armazenamento lateral conceitual, causal e com balanço de água fechado, antes da propagação nativa. O observado original permanece intacto e é comparado com a entrada efetiva em `montante_original_e_entrada_modelo.csv`. A geometria e a descarga da planície ainda não foram medidas; não se trata de reservatório hidráulico validado.
- Estrela mantém a restrição pelo nível em 32 horas sem Q. Nenhuma vazão ausente foi preenchida como observação.
- Cada modelo final foi executado novamente, em série, e exige saída nativa completa em todos os controles. As métricas exportadas são recalculadas independentemente a partir dos valores nativos.

## Alcance

O domínio é E1 BHO6 por ramos de Linha José Júlio até Porto Mariante. Não é o projeto original completo de 145 sub-bacias. Chuva e vazão de montante de todo o evento são conhecidas neste teste retrospectivo. Não há comprovação de previsão em tempo real, nem de transferência destes membros a outra cheia.

A chuva de novembro tem mediana de 3 postos/h. Estrela tem 142/240 h de Q e uma lacuna de 63 h; os erros e vieses são calculados nos pares disponíveis, não em observações fabricadas durante a lacuna. Os horários observados são horários agregados; diferenças de poucos minutos na simulação não representam precisão de campo de poucos minutos.

Em Muçum há dois diagnósticos: ajuste completo condicionado à curva da telemetria e ajuste até 15 m. A comparação dos CSVs mostra também qualquer compromisso entre eles; não se afirma melhora em todos os indicadores. O objetivo desta revisão foi corrigir principalmente a crista e a subida, que estavam mal representadas na entrega anterior.

Nenhum membro foi promovido ao painel público. Os critérios de seleção são critérios de trabalho para calibração deste evento, não certificação universal de desempenho.

## Referências

USACE HEC. Model Calibration. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsrd/model-calibration-355276362.html

USACE HEC. Applying the Muskingum Routing Method. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-reach-routing-methods-within-hec-hms/applying-the-muskingum-routing-method

USACE HEC. Recession Model. https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model
'''
    (pack/'LEIA-ME.md').write_text(notes)
    hashes={str(f.relative_to(pack)):hashlib.sha256(f.read_bytes()).hexdigest() for f in pack.rglob('*') if f.is_file()}
    v.save(pack/'sha256.json',hashes)
    v.save(dest/'v2_comparison.json',records)
    print(json.dumps(dict(image=str(image),pack=str(pack),comparison=records),ensure_ascii=False))

if __name__=='__main__':main()
