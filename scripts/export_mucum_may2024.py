#!/usr/bin/env python3
"""Package verified, event-specific May HEC projects, observations and figures."""
import argparse,csv,hashlib,io,json,os,shutil,zipfile
from datetime import timedelta
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as dates
from PIL import Image
import calibrate_mucum_may2024 as m

NAME='Mucum_HEC_Maio2024_2026-10-24'

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.pending')
    with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def csv_bytes(rows):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);return s.getvalue().encode()

def png(fig):
    b=io.BytesIO();fig.savefig(b,format='png',dpi=170,facecolor='white');plt.close(fig);data=b.getvalue();Image.open(io.BytesIO(data)).verify();return data

def main():
    ap=argparse.ArgumentParser();ap.add_argument('destination',type=Path);args=ap.parse_args();dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=True);pack=dest/NAME
    if pack.exists():shutil.rmtree(pack)
    pack.mkdir();selected=m.load(m.OUT/'selection.json');base=m.load(m.OUT/'baseline.json');ctx=m.prepare();times,rain,hydro,digest=ctx
    if not selected.get('verification',{}).get('joint_improvement_against_same_rainfall_baseline'):raise RuntimeError('Final native verification missing')
    if selected['input_sha256']!=digest:raise RuntimeError('Forcing changed after calibration')
    sims={};records=[];pairrows=[]
    for key,d,folder in [('baseline',base,'REFERENCIA_MAIO_MESMA_CHUVA'),('selected',selected,'HEC_MUCUM_MAIO2024_CALIBRADO')]:
        src=m.ROOT/d['project'];sim=m.ind.model(src/'hec_output_values.csv','86510000');pairs=m.ind.independent_pairs(sim,hydro,'86510000',dict(start_utc=times[0].isoformat(),end_utc=times[-1].isoformat()));stats=m.ind.metrics(pairs)
        for field in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(stats[field]-d['metrics']['86510000'][field])>1e-8:raise RuntimeError('Exporter independent metric mismatch '+key+' '+field)
        record=dict(model=key,**d['metrics']['86510000']);records.append(record);sims[key]=sim;shutil.copytree(src,pack/folder)
        for p in (pack/folder).iterdir():
            if p.is_file() and (p.name=='run.script' or p.suffix in ['.log','.access','.pending']):p.unlink()
            if p.is_file() and p.suffix in ['.hms','.gage','.met','.basin','.run','.control']:
                if '/workspace/' in p.read_text():raise RuntimeError('Non-portable native file '+p.name)
        m.save(pack/folder/'parametros_e_metricas.json',d)
        for t,o,q in pairs:pairrows.append(dict(model=key,time_utc=t.isoformat(),observed_Q_m3s=o,native_HEC_Q_m3s=q))
    atomic(pack/'comparacao_mesmas_312_horas.csv',csv_bytes(records));atomic(pack/'pares_observado_HEC.csv',csv_bytes(pairrows))
    inputs=pack/'ENTRADAS_E_AUDITORIA';inputs.mkdir()
    for name in ['rain.json','hydro.json','scenario.json']:shutil.copy2(m.FORCING/name,inputs/name)
    m.save(m.OUT/'parameters_MAY2024.json',selected['parameters'])
    for name in ['parameters_MAY2024.json','input_audit.json','proxy_comparison.json','screening.json','scs_screening.json','response_screening.json','initial_state_screening.json','hybrid_screening.json','selection.json','legacy_may_native_series.csv']:
        if (m.OUT/name).exists():shutil.copy2(m.OUT/name,inputs/name)
    source_manifest=m.ROOT.parent/'may_inputs_source_manifest.json'
    if source_manifest.exists():shutil.copy2(source_manifest,inputs/source_manifest.name)
    rr=[]
    for t in times:
        row=dict(time_utc=t.isoformat(),time_Brasilia=t.astimezone(m.hms.BRT).isoformat())
        for sid in m.ZONES:row[sid+'_mm']=rain[sid][times.index(t)]
        rr.append(row)
    atomic(inputs/'chuva_observada_por_zona.csv',csv_bytes(rr))
    j=next(c for c in hydro['controls'] if c['code']=='86472000');observed_jj=[r for r in j['recent_rows'] if r.get('flow_m3s') is not None];mu=next(c for c in hydro['controls'] if c['code']=='86510000');obs=mu['recent_rows'];crest=m.hms.utc(max(obs,key=lambda r:r['flow_m3s'])['time_utc']);start=m.hms.utc(obs[0]['time_utc']);end=m.hms.utc(obs[-1]['time_utc'])
    old=base['metrics']['86510000'];new=selected['metrics']['86510000'];jjstats=selected['metrics']['86472000'];network=m.load(m.FORCING/'rain.json');diag=network['rain_diagnostics']
    fig,axes=plt.subplots(2,2,figsize=(16,10.8));fig.subplots_adjust(left=.07,right=.97,top=.83,bottom=.13,hspace=.42,wspace=.25)
    colors={'baseline':'#8594a9','selected':'#85294e'};labels={'baseline':'Referência · mesmos 57 postos','selected':'Calibração própria de maio · HEC-HMS'}
    for ax in axes[0]:
        for key in ['baseline','selected']:
            sim=sims[key];ax.plot([t for t,q in sim],[q for t,q in sim],color=colors[key],lw=2.2 if key=='selected' else 1.25,label=labels[key])
        ax.scatter([m.hms.utc(r['time_utc']) for r in obs],[r['flow_m3s'] for r in obs],s=12,color='#273b46',zorder=4,label='Vazão arquivada ANA/SGB')
        ax.axvline(crest,color='#5c6c77',ls=':',lw=1.1,label='Pico da série horária arquivada');ax.set_ylabel('Vazão (m³/s)');ax.grid(alpha=.13);ax.spines[['top','right']].set_visible(False)
    axes[0,0].set_xlim(start,end);axes[0,0].set_title('Evento completo · 312 horas de comparação',loc='left',fontweight='bold',fontsize=12);axes[0,0].legend(fontsize=8,frameon=False,loc='upper right')
    axes[0,0].xaxis.set_major_locator(dates.DayLocator(interval=2,tz=m.hms.BRT));axes[0,0].xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT));axes[0,0].set_xlabel('Abril–maio/2024 · horário de Brasília')
    axes[0,1].set_xlim(crest-timedelta(hours=24),crest+timedelta(hours=24));axes[0,1].set_ylim(6500,15500);axes[0,1].xaxis.set_major_locator(dates.HourLocator(interval=8,tz=m.hms.BRT));axes[0,1].xaxis.set_major_formatter(dates.DateFormatter('%d/%m\n%Hh',tz=m.hms.BRT));axes[0,1].set_title('Detalhe do pico da cheia',loc='left',fontweight='bold',fontsize=12)
    axes[0,1].text(.03,.96,f"NSE: {old['nse']:.4f} → {new['nse']:.4f}\nErro do pico: {old['peak_error_pct']:+.2f}% → {new['peak_error_pct']:+.2f}%\nDefasagem: {old['peak_time_minus_telemetry_h']:.2f} h → {new['peak_time_minus_telemetry_h']:.2f} h",va='top',transform=axes[0,1].transAxes,fontsize=10.5,fontweight='bold',bbox=dict(facecolor='white',alpha=.92,edgecolor='none'))
    jj=m.ind.model(m.ROOT/selected['project']/'hec_output_values.csv','86472000');ax=axes[1,0];ax.plot([t for t,q in jj],[q for t,q in jj],color='#256b7c',lw=1.8,label='JJ gerado pelo modelo de chuva')
    ax.scatter([m.hms.utc(r['time_utc']) for r in observed_jj],[r['flow_m3s'] for r in observed_jj],color='#273b46',s=18,zorder=4,label='Q de JJ disponível · 77 horas');last=m.hms.utc(observed_jj[-1]['time_utc']);ax.axvspan(last,end,color='#dce2e7',alpha=.5,label='Período sem Q observado de JJ');ax.set_xlim(start,end);ax.set_ylabel('Vazão em Linha José Júlio (m³/s)');ax.set_xlabel('Abril–maio/2024 · horário de Brasília');ax.set_title('Montante: dado disponível e geração pela chuva',loc='left',fontweight='bold',fontsize=12);ax.legend(fontsize=8,frameon=False,loc='upper right');ax.text(.97,.035,f'NSE nas 77 horas de JJ: {jjstats["nse"]:.4f}',va='bottom',ha='right',transform=ax.transAxes,fontsize=9.5,bbox=dict(facecolor='white',alpha=.8,edgecolor='none'))
    ax.xaxis.set_major_locator(dates.DayLocator(interval=2,tz=m.hms.BRT));ax.xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT));ax.grid(alpha=.13);ax.spines[['top','right']].set_visible(False)
    ax=axes[1,1];ax.axis('off');ax.set_title('Comparação nativa · mesma chuva e relógio',loc='left',fontweight='bold',fontsize=12,pad=12)
    table_rows=[]
    for label,key,scale,fmt in [('NSE','nse',1,'.4f'),('KGE','kge',1,'.4f'),('Erro do pico (%)','peak_error_pct',1,'+.2f'),('Defasagem do pico (h)','peak_time_minus_telemetry_h',1,'+.2f'),('Viés (%)','pbias_pct',1,'+.2f'),('Erro relativo na subida (%)','rising_NMAE',100,'.2f'),('Erro relativo na recessão (%)','recession_NMAE',100,'.2f'),('RMSE (m³/s)','rmse_m3s',1,'.1f')]:table_rows.append([label,format(old[key]*scale,fmt),format(new[key]*scale,fmt)])
    table=ax.table(cellText=table_rows,colLabels=['Indicador','Referência','Maio calibrado'],colWidths=[.55,.2,.25],cellLoc='left',bbox=[0,.2,1,.77]);table.auto_set_font_size(False);table.set_fontsize(9.5)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor('white');cell.set_facecolor('#e9eef1' if r==0 else ('#f5f7f8' if r%2 else 'white'))
        if r==0:cell.set_text_props(fontweight='bold')
        elif c==2:cell.set_text_props(fontweight='bold',color='#85294e')
    ax.text(0,.055,'5 zonas · 15.965,207 km² · 7 dias antecedentes\nSem vazão observada entrando como Source no modelo.',transform=ax.transAxes,fontsize=10,color='#43515c')
    fig.suptitle('Muçum · maio/2024 · calibração própria no HEC-HMS',x=.035,y=.965,ha='left',fontsize=20,fontweight='bold');fig.text(.035,.902,f"57 estações recuperadas · mínimo de {diag['minimum_valid_station_count']} por hora no evento · observações e chuva sem deslocamento artificial de horário.",fontsize=11.5,color='#43515c')
    fig.text(.035,.035,'Saídas nativas HEC-HMS 4.13, recalculadas em pasta isolada. A vazão observada de Muçum foi desconectada em teste e não alterou a simulação.\nResultado de calibração em maio, sem validação independente de evento. A recessão e a segunda onda ainda concentram erro; a marca de campo de 26,00 m não substituiu a telemetria.',fontsize=9,color='#43515c')
    image=dest/(NAME+'.png');data=png(fig);atomic(image,data);atomic(pack/image.name,data)
    # Additional rainfall evidence remains bundled with the native project.
    f,ax=plt.subplots(figsize=(15,5))
    for sid in m.ZONES:
        daily={}
        for t,v in zip(times,rain[sid]):daily[t.astimezone(m.hms.BRT).date()]=daily.get(t.astimezone(m.hms.BRT).date(),0)+v
        ax.plot(list(daily),list(daily.values()),marker='o',ms=3,lw=1.5,label=sid)
    ax.set_title('Chuva observada espacializada · sete dias antecedentes e evento de maio/2024',loc='left',fontweight='bold');ax.set_ylabel('Chuva diária por zona (mm)');ax.legend(frameon=False,fontsize=8);ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False);f.tight_layout();atomic(pack/'Chuva_observada_Maio2024.png',png(f))
    notes=f'''# Muçum — calibração própria de maio de 2024

O modelo HEC-HMS 4.13 foi calibrado para E27_MAY2024 e é separado do ajuste de novembro/2023. A simulação usa chuva observada desde 21/04/2024, com sete dias antecedentes, e compara 312 horários reais de Muçum de 28/04 a 10/05/2024. Os parâmetros não foram tratados como universais.

## Resultado e abertura

Abra `HEC_MUCUM_MAIO2024_CALIBRADO/g040_e1_hindcast.hms` e compute `Hindcast`. O observado de Muçum está associado como Observed Hydrograph Gage para inspeção gráfica; não é entrada de vazão. `REFERENCIA_MAIO_MESMA_CHUVA` conserva o ponto de partida, com as mesmas chuvas, área, janela e relógio.

| Indicador | Referência | Maio calibrado |
| --- | ---: | ---: |
| Horas pareadas | {old['pairs']} | {new['pairs']} |
| NSE | {old['nse']:.6f} | {new['nse']:.6f} |
| KGE | {old['kge']:.6f} | {new['kge']:.6f} |
| Erro do pico contra telemetria | {old['peak_error_pct']:+.3f}% | {new['peak_error_pct']:+.3f}% |
| Pico menos horário da telemetria | {old['peak_time_minus_telemetry_h']:+.2f} h | {new['peak_time_minus_telemetry_h']:+.2f} h |
| Viés nas horas pareadas | {old['pbias_pct']:+.3f}% | {new['pbias_pct']:+.3f}% |
| NMAE na subida | {old['rising_NMAE']*100:.2f}% | {new['rising_NMAE']*100:.2f}% |
| NMAE na recessão | {old['recession_NMAE']*100:.2f}% | {new['recession_NMAE']*100:.2f}% |
| RMSE | {old['rmse_m3s']:.2f} m³/s | {new['rmse_m3s']:.2f} m³/s |

O pico nativo final é {new['full_simulated_peak_m3s']:.2f} m³/s em {new['full_simulated_peak_time_utc']}, equivalente a {m.hms.utc(new['full_simulated_peak_time_utc']).astimezone(m.hms.BRT).strftime('%d/%m/%Y às %Hh%M')} de Brasília. O máximo da série horária arquivada é {new['observed_peak_m3s']:.3f} m³/s em 02/05 às 07h de Brasília. A amostragem observada é horária; o passo nativo de 3 min não cria precisão observacional de 3 min. A subida usa as 24 h anteriores ao pico horário observado, e a recessão os horários posteriores até o final da janela. NMAE = soma dos erros absolutos / soma das vazões observadas no trecho; não é MAPE. As lacunas observadas não viram pares sintéticos.

## O que mudou na modelagem

Foram recuperadas 57 estações de chuva que reportaram no evento, com {diag['minimum_valid_station_count']} a {diag['maximum_valid_station_count']} estações por hora e mediana {diag['median_valid_station_count']}. Há 41 estações com pelo menos 75% dos horários do evento. As cinco zonas têm 480 horas de chuva completas, incluindo o antecedente. A chuva foi espacializada por IDW² na malha fixa de 600 células e integrada nas zonas. Não houve chuva ausente preenchida com zero. Os arquivos de chuva, inventário de suporte, vazões, parâmetros e hashes acompanham a entrega.

A série arquivada de Linha José Júlio tem apenas 77 observações horárias, a última em 02/05/2024 às 01h de Brasília, antes do pico de Muçum. O modelo, portanto, gera o escoamento por chuva em Prata, Antas residual, Carreiro, residual de Santa Tereza e incremento de Muçum. Não utiliza vazão observada como Source, não persiste a última leitura de JJ e não transforma Muçum observado em condição de entrada. JJ serve como controle auxiliar apenas nos 77 horários reais disponíveis: NSE parcial final {jjstats['nse']:.5f}. Isso não valida as horas posteriores sem observação de JJ.

As áreas nominais BHO6 somam 15.965,207 km². O suporte pluviométrico usa os polígonos regionais já existentes; sua área cartográfica total difere das áreas nominais dos elementos, diferença registrada nos diagnósticos de interseção. Não foram inventadas novas sub-bacias de campo nem somadas estações aninhadas como tributários independentes. Os parâmetros de Prata e Antas foram separados, e a perda inicial foi calibrada como estado antecedente efetivo. O método final é Initial+Constant / Clark / Recession com propagação Muskingum X=0. As perdas e tempos são parâmetros efetivos calibrados, não medições de solo ou de velocidade.

Foram exploradas alternativas SCS/Clark, separação da resposta Prata–Antas, estado inicial e uma hipótese de contorno híbrido observado/modelado. As triagens Python estão identificadas como `proxy_only`; não são resultados nativos nem substituem observações. A hipótese híbrida não foi adotada no projeto entregue. O modelo final mantém a arquitetura inteiramente chuva–vazão. A triagem foi comparada com a referência nativa antes da busca: RMSE de 0,258 m³/s e máximo de 1,081 m³/s entre o aproximador e a execução nativa de referência. Todos os números principais desta entrega são do HEC real, não desse aproximador.

## Verificação

O projeto final foi copiado e computado novamente com os DSS existentes, sem reescrever suas chuvas. Foram conferidas 9.581 amostras de 3 min por elemento, séries finitas, horários, unidades M3/S e MM, soma das áreas e todas as 480 horas de chuva em cada zona. A maior diferença de chuva entre os valores originais e o DSS foi inferior a 0,000001 mm, por precisão numérica do armazenamento.

Uma segunda cópia foi computada após remover a ligação da observação de Muçum. A diferença máxima da vazão simulada foi exatamente zero. As métricas foram recalculadas por dois caminhos independentes de código, com concordância numérica. O teste de melhora conjunta contra a referência, com entradas idênticas, passou para NSE, KGE, pico, horário, subida e recessão.

## Dados de nível e limites

A telemetria arquivada alcança 25,525 m. A nota técnica do SGB relata leitura de 26,00 m na madrugada de 02/05/2024 e também apresenta marcas niveladas em outros locais de Muçum. As posições têm gradiente e não são intercambiáveis com a régua. Essas referências foram preservadas separadamente: não se deslocou o relógio, não se elevou a série em 0,475 m e não se alterou Q para forçar concordância com a marca de campo.

A maior limitação remanescente é a forma da recessão e da segunda onda: o NMAE desse trecho ainda é {new['recession_NMAE']*100:.2f}%. O ajuste não comprova batimetria, remanso, operação das usinas ou transferência para outro evento. Por utilizar maio na escolha dos parâmetros, este resultado é **calibração específica de maio**, não validação independente de evento, mesmo que maio tenha sido reservado como holdout em antigos benchmarks de outros modelos. Novembro e Estrela continuam com modelos separados.

## Fontes e reprodução

- ANA/SGB: arquivo histórico de E27_MAY2024 e serviço DadosHidrometeorologicos; cópia integral dos controles em ENTRADAS_E_AUDITORIA/hydro.json. Chuva observada e metadados em rain.json.
- SGB. Nota técnica de levantamento das marcas da grande cheia de maio de 2024, v.3, seção 4.1: https://rigeo.sgb.gov.br/bitstream/doc/24939.5/3/nota_tecnica_levantamento_cheia_2024_v.3.pdf . A leitura de 26,00 m é relatada no texto; não é criada uma vazão medida independente a partir dela.
- USACE. Clark Unit Hydrograph Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/clark-unit-hydrograph-model .
- USACE. Recession Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model .
- Código e registros: repositório PREVINE, branch research/mucum-estrela-eventos-20261024, PR 278. Scripts calibrate_mucum_may2024.py, search_mucum_may2024.py, refine_mucum_may_initial_state.py, verify_mucum_may2024.py e export_mucum_may2024.py. Para recalcular o projeto entregue basta o HEC-HMS 4.13: os DSS necessários estão nas pastas dos projetos. Para reproduzir a busca, restaure os arquivos rain/hydro/scenario de ENTRADAS_E_AUDITORIA em historical_calibration_forcing/E27_MAY2024.
'''
    atomic(pack/'LEIA-ME.md',notes.encode());atomic(m.ROOT/'docs/HEC_MUCUM_MAIO2024_20261024.md',notes.encode())
    m.save(pack/'sha256.json',{str(p.relative_to(pack)):hashlib.sha256(p.read_bytes()).hexdigest() for p in pack.rglob('*') if p.is_file()})
    archive=dest/(NAME+'.zip');tmp=archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pack.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(dest)))
    with zipfile.ZipFile(tmp) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failed')
        for name in z.namelist():
            if name.endswith('.png'):Image.open(io.BytesIO(z.read(name))).verify()
    tmp.replace(archive);print(json.dumps(dict(archive=str(archive),image=str(image),comparison=records),ensure_ascii=False))

if __name__=='__main__':main()
