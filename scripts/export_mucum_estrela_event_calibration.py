#!/usr/bin/env python3
"""Independently recompute selected calibration scores and package native models."""
from __future__ import annotations
import argparse,bisect,csv,hashlib,json,shutil,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'assets/data/hec_hms_g040_full_basin'
CAL=BASE/'mucum_estrela_event_calibration_20261024'
EPOCH=datetime(1899,12,31,tzinfo=timezone(timedelta(hours=-3)))

def load(p):return json.loads(Path(p).read_text())
def utc(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def iso(t):return t.isoformat().replace('+00:00','Z')
def model(path,code):
    by={}
    with Path(path).open() as fh:
        for r in csv.DictReader(fh):
            if r['element']=='J_'+code:
                t=(EPOCH+timedelta(minutes=int(r['time_value']))).astimezone(timezone.utc)
                by[t]=float(r['q_m3s'])
    return sorted(by.items())

def independent_pairs(sim,hydro,code,window):
    c=next(c for c in hydro['controls'] if str(c['code'])==code)
    rows=sorted((utc(r['time_utc']),float(r['flow_m3s'])) for r in c['recent_rows'] if r.get('flow_m3s') is not None)
    ts=[t for t,v in rows];s=dict(sim);pairs=[]
    t=utc(window['start_utc']);end=utc(window['end_utc'])
    while t<=end:
        i=bisect.bisect_left(ts,t);q=None
        if i<len(ts) and ts[i]==t:q=rows[i][1]
        elif 0<i<len(ts) and (ts[i]-ts[i-1]).total_seconds()<=3600:
            w=(t-ts[i-1]).total_seconds()/(ts[i]-ts[i-1]).total_seconds()
            q=rows[i-1][1]*(1-w)+rows[i][1]*w
        if q is not None and t in s:pairs.append((t,q,s[t]))
        t+=timedelta(hours=1)
    return pairs

def metrics(pairs):
    o=np.array([o for t,o,s in pairs]);s=np.array([s for t,o,s in pairs])
    return dict(pairs=len(o),nse=float(1-np.sum((s-o)**2)/np.sum((o-o.mean())**2)),
      kge=float(1-np.linalg.norm([np.corrcoef(o,s)[0,1]-1,s.std()/o.std()-1,s.mean()/o.mean()-1])),
      pbias_pct=float(100*(s-o).sum()/o.sum()),rmse_m3s=float(np.sqrt(np.mean((s-o)**2))))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);args=ap.parse_args()
    dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=True)
    summary=load(CAL/'selected_models.json');search=load(CAL/'search_results.json')
    for row in summary['selected']:
        if row['target_code']=='86879300' and not (row.get('low_stage_constraint') or {}).get('pass_with_10pct_model_tolerance'):
            raise RuntimeError('Estrela has not passed the observed low-stage consistency check; export refused')
    hydro=load(CAL/'score_hydro_quality_controlled.json')
    raw=load(BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json')
    pack=dest/'HEC_Mucum_Estrela_modelos_2026-10-24';pack.mkdir(exist_ok=True)
    records=[];series=[];hashes={};fig,axes=plt.subplots(2,1,figsize=(13,8.8),layout='constrained')
    colors={'old':'#d08d2d','new':'#087b8c','obs':'#243447'}
    for ax,best in zip(axes,summary['selected']):
        code=best['target_code'];name=best['target_name'];rpath=ROOT/best['result_file'];result=load(rpath)
        sim=model(rpath.parent/'project/hec_output_values.csv',code)
        pp=independent_pairs(sim,hydro,code,result['window']);mm=metrics(pp)
        for k in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(mm[k]-best['scores'][code][k])>1e-8:raise RuntimeError(f'Independent metric mismatch {name} {k}')
        # Compare to the documented native baseline under the identical QA.
        candidates=[r for r in search if r['target_code']==code and 'baseflow_specific' not in r['parameters']]
        baseline=min(candidates,key=lambda r:r['objective']);brp=ROOT/baseline['result_file'];bj=load(brp)
        bs=model(brp.parent/'project/hec_output_values.csv',code)
        bmm=metrics(independent_pairs(bs,hydro,code,result['window']))
        stage_crest=utc(best['observed_stage_crest']['time_utc'])
        peak_t,peak_q=max(sim,key=lambda z:z[1]);timing=(peak_t-stage_crest).total_seconds()/3600
        record=dict(city=name,station=code,event='novembro/2023',model_id=f'{"MUCUM" if code=="86510000" else "ESTRELA"}_NOV2023_RECESSION_V1',
          **mm,observed_pairs_coverage=mm['pairs']/result['window']['hours'],stage_crest_timing_error_h=timing,
          paired_Q_peak_error_pct=best['scores'][code]['peak_error_pct'] if code!='86510000' else None,
          full_model_peak_m3s=peak_q,baseline_nse=bmm['nse'],baseline_bias_pct=bmm['pbias_pct'],
          scope='Q below 15 m, documented clock correction -105 min' if code=='86510000' else 'Partial actual Q observations',
          operationally_validated=False)
        records.append(record)
        case=pack/record['model_id'];shutil.copytree(rpath.parent/'project',case,dirs_exist_ok=True)
        # Native GUI projects are portable. The generated batch script contains
        # this workspace's absolute paths and is replaced with rerun guidance.
        (case/'run.script').unlink(missing_ok=True)
        for f in case.iterdir():
            if f.is_file() and f.suffix in ['.access','.log']:f.unlink()
        (case/'parametros_e_resultados.json').write_text(json.dumps(dict(record=record,parameters=best['parameters'],native_run=result),ensure_ascii=False,indent=2)+'\n')
        hashes[record['model_id']]={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in case.iterdir() if f.is_file()}
        ax.plot([t for t,q in bs],[q for t,q in bs],color=colors['old'],lw=1.5,label=f'Anterior, reavaliado · NSE {bmm["nse"]:.3f}')
        ax.plot([t for t,q in sim],[q for t,q in sim],color=colors['new'],lw=2,label=f'Calibrado agora · NSE {mm["nse"]:.3f}')
        c=next(c for c in hydro['controls'] if str(c['code'])==code)
        obs=[(utc(r['time_utc']),r['flow_m3s']) for r in c['recent_rows'] if r.get('flow_m3s') is not None]
        ax.scatter([t for t,q in obs],[q for t,q in obs],s=9,color=colors['obs'],zorder=4,label='Vazão observada usada no ajuste')
        if code=='86510000':
            c0=next(c for c in raw['controls'] if str(c['code'])==code)
            high=[(utc(r['time_utc'])-timedelta(minutes=105),r['flow_m3s']) for r in c0['recent_rows'] if r.get('flow_m3s') is not None and r.get('level_source_unit',0)>1500]
            ax.scatter([t for t,q in high],[q for t,q in high],s=17,facecolors='none',edgecolors='#9ca9b4',label='Acima de 15 m: fora da calibração de vazão')
        ax.axvline(stage_crest,color='#7c8791',lw=1,ls=':',label='Horário do pico de nível observado')
        ax.set_title(f'{name} · novembro de 2023',loc='left',fontweight='bold',fontsize=14)
        ax.text(.99,.96,f'KGE {mm["kge"]:.3f}  |  viés {mm["pbias_pct"]:+.1f}%  |  pico {timing:+.2f} h',transform=ax.transAxes,ha='right',va='top',fontsize=10)
        ax.set_ylabel('Vazão (m³/s)');ax.grid(axis='y',alpha=.18);ax.spines[['top','right']].set_visible(False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=timezone(timedelta(hours=-3))))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1,tz=timezone(timedelta(hours=-3))))
        ax.legend(loc='upper right',bbox_to_anchor=(1,.87),fontsize=8,frameon=False)
        for t,o,s in pp:series.append(dict(city=name,time_utc=iso(t),observed_q_m3s=o,simulated_q_m3s=s))
    fig.suptitle('HEC-HMS · modelos calibrados para Muçum e Estrela',fontsize=19,fontweight='bold',x=.01,ha='left')
    axes[-1].set_xlabel('Data · horário de Brasília')
    fig.get_layout_engine().set(rect=(0,.09,1,.86))
    fig.text(.012,.017,'Calibração histórica com chuva e vazão de montante observadas. Novembro: mediana de 3 pluviômetros/h.\nMuçum: vazão ajustada até 15 m; correção de relógio conforme relatório fornecido. Estrela: 142 h de vazão disponíveis. Não demonstra previsão operacional.',fontsize=9,color='#495662')
    image=dest/'HEC_Mucum_Estrela_calibracao_2026-10-24.png';fig.savefig(image,dpi=180,facecolor='white');plt.close(fig)
    for filename,rows in [('metricas_conferidas.csv',records),('pares_observado_simulado.csv',series)]:
        with (pack/filename).open('w',newline='') as fh:
            w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (pack/'manifesto_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    audit=CAL/'native_water_budget_audit.json'
    if audit.exists():shutil.copy2(audit,pack/'auditoria_componentes_balanco.json')
    if summary.get('observed_low_stage_constraint'):
        (pack/'restricao_pelo_nivel_observado.json').write_text(json.dumps(summary['observed_low_stage_constraint'],ensure_ascii=False,indent=2)+'\n')
    (pack/'busca_parametros.json').write_text(json.dumps(search,ensure_ascii=False,indent=2)+'\n')
    notes='''# Modelos HEC-HMS calibrados — Muçum e Estrela

Data: 24/10/2026. Motor: HEC-HMS 4.13. Evento de calibração: novembro/2023 (E24 do catálogo antigo q62; E12 do catálogo Muçum 2h).

Cada pasta contém um projeto nativo. Abra `g040_e1_hindcast.hms` no HEC-HMS; selecione a simulação `Hindcast`. Os arquivos de entrada DSS e os resultados estão incluídos. A versão 4.13 foi a executada; versões mais recentes não foram testadas. `parametros_e_resultados.json` fixa os parâmetros e a execução. O CSV de pares permite conferir as métricas.

## O que mudou

Foi acrescentada a opção de vazão de base por recessão nativa do HEC somente às áreas incrementais de chuva–vazão, mantendo a vazão de Linha José Júlio como condição de montante. Os parâmetros CN, lag e propagação foram ajustados por cidade. O modelo de cada cidade tem seu próprio conjunto; não é um conjunto universal. A opção antiga sem vazão de base permanece disponível.

O modelo é o E1 por ramos BHO6, de Linha José Júlio até Porto Mariante, com áreas incrementais e afluentes. Não é a reconstrução integral do projeto original de 145 sub-bacias. A vazão futura de Linha José Júlio e a chuva de todo o evento são conhecidas neste teste retrospectivo. Isso não é previsão emitida antes da cheia.

## Observações e limites

- Muçum: seguiu-se a nota técnica fornecida pela usuária, atualização de 06/10: correção de relógio de −105 min no período documentado; somente Q com nível até 15 m entra no objetivo. O pico de nível marca o horário da onda; a amplitude da vazão extrema não foi calibrada nem validada. A correção do relógio não foi medida novamente nesta execução. A série original permanece intacta.
- Estrela: só 142 das 240 horas têm vazão disponível (59,2%). Há uma lacuna de 63 h. Os resultados descrevem os pares observados; não provam toda a subida e descida durante a lacuna. Volume e viés se referem aos pares, não ao volume contínuo da cheia.
- A revisão rejeitou um pico secundário artificial em Estrela que o NSE sozinho escondia. Em 32 horas sem Q, o nível medido está abaixo do menor par nível–Q disponível (13,9875 m; 2.186,6 m³/s). Sob a mesma relação monotônica, isso fornece somente um limite superior de vazão. Nenhuma Q ausente foi preenchida. O modelo final deve respeitar esse limite com tolerância de erro de 10%.
- Novembro: mediana de 3 pluviômetros/h; os parâmetros podem compensar parte do erro de chuva. A disponibilidade do inventário não representa a cobertura efetiva do evento.
- Os CNs globais são parâmetros efetivos da calibração com esse forçamento; não são valores mapeados de solo/uso da terra e não devem ser transferidos automaticamente às 145 sub-bacias originais.
- A vazão de montante em grandes níveis também depende de curva-chave. A hipótese de recessão não identifica, por si só, a dinâmica real do aquífero. O método de recessão não garante conservação de massa automaticamente; avaliar o armazenamento antecedente antes de adotar para operação.
- NSEs de versões antigas que interpolavam lacunas ou usavam todo o intervalo da curva-chave não são diretamente comparáveis. O comparativo desta entrega recalcula os modelos anteriores com a mesma política de observação da nova rodada.
- Esta busca usa o evento completo para selecionar parâmetros; é calibração. Maio/junho de 2024 ficaram reservados, sem retreinamento nesta busca. O teste independente em outros eventos e com chuva prevista ainda é necessário.
- Nada desta entrega foi promovido ao modelo público.

## Referências de método

USACE HEC. Model Calibration. https://www.hec.usace.army.mil/confluence/hmsdocs/hmsrd/model-calibration-355276362.html

USACE HEC. Recession Model. https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model
'''
    (pack/'LEIA-ME.md').write_text(notes)
    (pack/'resumo_modelos.json').write_text(json.dumps(dict(models=records,search_count=summary['total_completed_runs'],configuration=summary['configuration']),ensure_ascii=False,indent=2)+'\n')
    archive=dest/(pack.name+'.zip')
    temporary=archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(pack.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(dest))
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:raise RuntimeError('Archive integrity check failed')
    temporary.replace(archive)
    (dest/'verified_metrics.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(models=records,archive=str(archive),image=str(image)),ensure_ascii=False))

if __name__=='__main__':main()
