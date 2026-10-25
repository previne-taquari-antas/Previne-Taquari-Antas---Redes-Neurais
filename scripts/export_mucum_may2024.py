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
    pack.mkdir();selected=m.load(m.OUT/'selection.json');base=m.load(m.OUT/'baseline.json');previous=m.load(m.OUT/'before_revision2_selection.json');ctx=m.prepare();times,rain,hydro,digest=ctx
    if not selected.get('verification',{}).get('joint_improvement_against_same_rainfall_baseline'):raise RuntimeError('Final native verification missing')
    if selected['input_sha256']!=digest:raise RuntimeError('Forcing changed after calibration')
    sims={};records=[];pairrows=[]
    for key,d,folder in [('baseline',base,'REFERENCIA_MAIO_MESMA_CHUVA'),('previous',previous,'ANTERIOR_MAIO_NSE_0_9981'),('selected',selected,'HEC_MUCUM_MAIO2024_CALIBRADO'),('secondary_crest',m.load(m.OUT/'secondary_crest_native.json'),'VARIANTE_PICO_SEGUNDA_ONDA')]:
        src=m.ROOT/d['project'];sim=m.ind.model(src/'hec_output_values.csv','86510000');pairs=m.ind.independent_pairs(sim,hydro,'86510000',dict(start_utc=times[0].isoformat(),end_utc=times[-1].isoformat()));stats=m.ind.metrics(pairs)
        for field in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(stats[field]-d['metrics']['86510000'][field])>1e-8:raise RuntimeError('Exporter independent metric mismatch '+key+' '+field)
        record=dict(model=key,**d['metrics']['86510000']);records.append(record);sims[key]=sim;shutil.copytree(src,pack/folder)
        for p in (pack/folder).iterdir():
            if p.is_file() and (p.name=='native_soil_process_hourly.csv' or p.suffix in ['.script','.log','.access','.pending']):p.unlink()
            if p.is_file() and p.suffix in ['.hms','.gage','.met','.basin','.run','.control']:
                if '/workspace/' in p.read_text():raise RuntimeError('Non-portable native file '+p.name)
        m.save(pack/folder/'parametros_e_metricas.json',d)
        for t,o,q in pairs:pairrows.append(dict(model=key,time_utc=t.isoformat(),observed_Q_m3s=o,native_HEC_Q_m3s=q))
    atomic(pack/'comparacao_mesmas_312_horas.csv',csv_bytes(records));atomic(pack/'pares_observado_HEC.csv',csv_bytes(pairrows))
    inputs=pack/'ENTRADAS_E_AUDITORIA';inputs.mkdir()
    for name in ['rain.json','hydro.json','scenario.json']:shutil.copy2(m.FORCING/name,inputs/name)
    m.save(m.OUT/'parameters_MAY2024.json',selected['parameters'])
    for name in ['parameters_MAY2024.json','calibration_manifest.json','input_audit.json','proxy_comparison.json','screening.json','scs_screening.json','response_screening.json','initial_state_screening.json','hybrid_screening.json','spatial_screening.json','wetness_screening.json','wetness_native_proxy_audit.json','soil_storage_screening.json','soil_peak_screening.json','soil_cascade_screening.json','soil_cascade_high_screening.json','soil_hypothesis_audit.json','previous_accepted_selection.json','before_revision2_selection.json','second_wave_screening.json','second_wave_balance_screening.json','second_wave_fine_screening.json','second_wave_crest_screening.json','revision2_comparison.json','secondary_crest_native.json','selection.json','legacy_may_native_series.csv']:
        if (m.OUT/name).exists():shutil.copy2(m.OUT/name,inputs/name)
    source_manifest=m.ROOT.parent/'may_inputs_source_manifest.json'
    if source_manifest.exists():shutil.copy2(source_manifest,inputs/source_manifest.name)
    if (m.OUT/'soil_diagnostic.png').exists():shutil.copy2(m.OUT/'soil_diagnostic.png',pack/'Diagnostico_solo_e_armazenamento.png')
    if (m.OUT/'soil_ablation_native.json').exists():shutil.copy2(m.OUT/'soil_ablation_native.json',inputs/'soil_ablation_native.json')
    code=pack/'CODIGO_REPRODUCAO';code.mkdir()
    for pattern in ['*mucum_may*.py','calibrate_mucum_may2024.py','run_hec_hms_g040_e1_hindcast.py','export_mucum_estrela_event_calibration.py','g040_overbank_storage.py']:
        for p in (m.ROOT/'scripts').glob(pattern):shutil.copy2(p,code/p.name)
    rr=[]
    for t in times:
        row=dict(time_utc=t.isoformat(),time_Brasilia=t.astimezone(m.hms.BRT).isoformat())
        for sid in m.ZONES:row[sid+'_mm']=rain[sid][times.index(t)]
        rr.append(row)
    atomic(inputs/'chuva_observada_por_zona.csv',csv_bytes(rr))
    j=next(c for c in hydro['controls'] if c['code']=='86472000');observed_jj=[r for r in j['recent_rows'] if r.get('flow_m3s') is not None];mu=next(c for c in hydro['controls'] if c['code']=='86510000');obs=mu['recent_rows'];crest=m.hms.utc(max(obs,key=lambda r:r['flow_m3s'])['time_utc']);start=m.hms.utc(obs[0]['time_utc']);end=m.hms.utc(obs[-1]['time_utc'])
    soil_audit=m.load(m.OUT/'soil_hypothesis_audit.json');old=previous['metrics']['86510000'];new=selected['metrics']['86510000'];jjstats=selected['metrics']['86472000'];network=m.load(m.FORCING/'rain.json');diag=network['rain_diagnostics']
    fig,axes=plt.subplots(2,2,figsize=(16,10.8));fig.subplots_adjust(left=.07,right=.97,top=.83,bottom=.13,hspace=.42,wspace=.25)
    colors={'previous':'#8594a9','selected':'#85294e'};labels={'previous':'Anterior · NSE 0,9981','selected':'Novo · resposta própria por sub-bacia'}
    for ax in [axes[0,0],axes[0,1],axes[1,0]]:
        for key in ['previous','selected']:
            sim=sims[key];ax.plot([t for t,q in sim],[q for t,q in sim],color=colors[key],lw=2.2 if key=='selected' else 1.25,label=labels[key])
        ax.scatter([m.hms.utc(r['time_utc']) for r in obs],[r['flow_m3s'] for r in obs],s=12,color='#273b46',zorder=4,label='Vazão arquivada ANA/SGB')
        ax.axvline(crest,color='#5c6c77',ls=':',lw=1.1,label='Pico da série horária arquivada');ax.set_ylabel('Vazão (m³/s)');ax.grid(alpha=.13);ax.spines[['top','right']].set_visible(False)
    axes[0,0].set_xlim(start,end);axes[0,0].set_title('Evento completo · 312 horas de comparação',loc='left',fontweight='bold',fontsize=12);axes[0,0].legend(fontsize=8,frameon=False,loc='upper right')
    axes[0,0].xaxis.set_major_locator(dates.DayLocator(interval=2,tz=m.hms.BRT));axes[0,0].xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT));axes[0,0].set_xlabel('Abril–maio/2024 · horário de Brasília')
    axes[0,1].set_xlim(crest-timedelta(hours=24),crest+timedelta(hours=24));axes[0,1].set_ylim(6500,15500);axes[0,1].xaxis.set_major_locator(dates.HourLocator(interval=8,tz=m.hms.BRT));axes[0,1].xaxis.set_major_formatter(dates.DateFormatter('%d/%m\n%Hh',tz=m.hms.BRT));axes[0,1].set_title('Detalhe do pico da cheia',loc='left',fontweight='bold',fontsize=12)
    axes[0,1].text(.03,.96,f"NSE: {old['nse']:.4f} → {new['nse']:.4f}\nErro do pico: {old['peak_error_pct']:+.2f}% → {new['peak_error_pct']:+.2f}%\nDefasagem: {old['peak_time_minus_telemetry_h']:.2f} h → {new['peak_time_minus_telemetry_h']:.2f} h",va='top',transform=axes[0,1].transAxes,fontsize=10.5,fontweight='bold',bbox=dict(facecolor='white',alpha=.92,edgecolor='none'))
    ax=axes[1,0];ax.set_xlim(crest+timedelta(hours=36),crest+timedelta(hours=150));ax.set_ylim(1000,10500);ax.set_title('Segunda onda e recessão · onde estava o erro',loc='left',fontweight='bold',fontsize=12);ax.set_xlabel('Maio/2024 · horário de Brasília');ax.xaxis.set_major_locator(dates.DayLocator(tz=m.hms.BRT));ax.xaxis.set_major_formatter(dates.DateFormatter('%d/%m',tz=m.hms.BRT));ax.text(.97,.95,f"Erro da recessão\n{old['recession_NMAE']*100:.2f}% → {new['recession_NMAE']*100:.2f}%",ha='right',va='top',transform=ax.transAxes,fontsize=11,fontweight='bold',bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
    ax=axes[1,1];ax.axis('off');ax.set_title('Comparação nativa · anterior × refinamento espacial',loc='left',fontweight='bold',fontsize=11.5,pad=12)
    table_rows=[]
    for label,key,scale,fmt in [('NSE','nse',1,'.4f'),('KGE','kge',1,'.4f'),('Erro do pico (%)','peak_error_pct',1,'+.2f'),('Defasagem do pico (h)','peak_time_minus_telemetry_h',1,'+.2f'),('Viés (%)','pbias_pct',1,'+.2f'),('Erro relativo na subida (%)','rising_NMAE',100,'.2f'),('Erro relativo na recessão (%)','recession_NMAE',100,'.2f'),('RMSE (m³/s)','rmse_m3s',1,'.1f')]:table_rows.append([label,format(old[key]*scale,fmt),format(new[key]*scale,fmt)])
    table=ax.table(cellText=table_rows,colLabels=['Indicador','Anterior','Novo maio'],colWidths=[.55,.2,.25],cellLoc='left',bbox=[0,.2,1,.77]);table.auto_set_font_size(False);table.set_fontsize(9.5)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor('white');cell.set_facecolor('#e9eef1' if r==0 else ('#f5f7f8' if r%2 else 'white'))
        if r==0:cell.set_text_props(fontweight='bold')
        elif c==2:cell.set_text_props(fontweight='bold',color='#85294e')
    ax.text(0,.055,'5 zonas · 15.965,207 km² · 7 dias antecedentes\nSem vazão observada entrando como Source no modelo.',transform=ax.transAxes,fontsize=10,color='#43515c')
    fig.suptitle('Muçum · maio/2024 · refinamento da segunda onda',x=.035,y=.965,ha='left',fontsize=19,fontweight='bold');fig.text(.035,.902,f"57 estações · mesma chuva e 312 observações · déficit do solo + reservatórios de contribuição subsuperficial · HEC-HMS 4.13.",fontsize=11.5,color='#43515c')
    fig.text(.035,.035,'Saídas nativas recalculadas em pasta isolada. A observação de Muçum foi desconectada em teste e não alterou a vazão simulada.\nCalibração específica de maio; o ajuste apoia a hipótese de armazenamento e contribuição subsuperficial, sem comprovar a umidade real do solo em campo.',fontsize=9,color='#43515c')
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

## Resultado e abertura — revisão de solo e armazenamento

Abra `HEC_MUCUM_MAIO2024_CALIBRADO/g040_e1_hindcast.hms` e compute `Hindcast`. O observado de Muçum está associado como Observed Hydrograph Gage para inspeção gráfica; não é entrada de vazão. `ANTERIOR_MAIO_NSE_0_9981` conserva a versão imediatamente anterior (NSE 0,998069; NMAE de recessão 2,70%). A versão histórica de perda constante tinha NSE 0,972600 e NMAE de recessão 12,56%; suas métricas e parâmetros permanecem nos diagnósticos. `REFERENCIA_MAIO_MESMA_CHUVA` conserva o ponto de partida ainda anterior, com NSE 0,898014. As quatro versões usam as mesmas chuvas, área, 312 horários e relógio. A tabela abaixo compara a revisão atual diretamente com o modelo anterior que motivou esta melhora.

| Indicador | Anterior, perda constante | Novo, solo e armazenamento |
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

As áreas nominais BHO6 somam 15.965,207 km². O suporte pluviométrico usa os polígonos regionais já existentes; sua área cartográfica total difere das áreas nominais dos elementos, diferença registrada nos diagnósticos de interseção. Não foram inventadas novas sub-bacias de campo nem somadas estações aninhadas como tributários independentes. Os parâmetros de Prata, Antas e Carreiro foram separados. O método final é **Deficit and Constant / Clark / Linear Reservoir**, com propagação Muskingum X=0. O déficit inicial descreve o estado antecedente efetivo; depois de preenchido, o solo permanece saturado na formulação do evento. A água percolada é parcialmente encaminhada a cascatas de reservatórios lineares de contribuição subsuperficial, com ordens próprias por grupo: Prata {selected['parameters'].get('gw_steps_prata',8)}, Antas {selected['parameters'].get('gw_steps_up',8)}, Carreiro {selected['parameters'].get('gw_steps_carreiro',8)} e residuais inferiores {selected['parameters'].get('gw_steps',8)}, com tempos e frações diferentes por grupo espacial; a fração restante é recarga profunda. Um segundo reservatório representa o escoamento antecedente, sem receber percolação nova. Nenhuma fração soma mais que 1.

Na revisão anterior que introduziu o solo, a mudança decisiva foi deixar de descartar toda a água infiltrada como perda definitiva: parte dela agora reaparece com atraso no rio. O modelo histórico de perda constante também consumia a perda inicial uma única vez; ele **não reiniciava artificialmente um solo seco na segunda onda**. Logo, a melhora apoia uma hipótese de armazenamento e contribuição subsuperficial, e não demonstra que um reinício da perda inicial fosse o erro. A tentativa Green-Ampt, que reduz a capacidade de infiltração progressivamente, chegou a NMAE nativo de recessão de 10,47%, mas não resolveu a segunda onda. A formulação acoplada foi superior.

As perdas, déficits, frações e tempos são parâmetros efetivos calibrados, não medições de solo ou velocidade. Não há medições locais de umidade ou ET usadas para comprovar esses parâmetros. A versão de evento não impõe evapotranspiração estimada artificialmente entre as ondas; a hipótese de pouca secagem no intervalo curto fica explícita. O máximo de déficit foi fixado em 200 mm e não é identificável sem extração de água por ET nesta configuração. Alguns parâmetros chegaram perto dos limites da busca; a decomposição por sub-bacia continua incerta mesmo com ajuste forte em Muçum. O NSE parcial de JJ passou de {previous['metrics']['86472000']['nse']:.5f} para {jjstats['nse']:.5f}; ele permanece um controle auxiliar de calibração, sem alegar melhora em todos os postos. A cascata é uma representação conceitual de dispersão de tempos de trânsito, não camadas de solo medidas.

Foram exploradas alternativas SCS/Clark, separação da resposta Prata–Antas, estado inicial e uma hipótese de contorno híbrido observado/modelado. As triagens Python estão identificadas como `proxy_only`; não são resultados nativos nem substituem observações. A hipótese híbrida não foi adotada no projeto entregue. O modelo final mantém a arquitetura inteiramente chuva–vazão. A triagem foi comparada com a referência nativa antes da busca: RMSE de 0,258 m³/s e máximo de 1,081 m³/s entre o aproximador e a execução nativa de referência. Todos os números principais desta entrega são do HEC real, não desse aproximador. As novas triagens espaciais, Green-Ampt, solo e cascatas também são preservadas; as execuções descartadas não são apresentadas como resultados finais. Cascatas de 1, 2, 3, 4, 5, 6, 8 e 10 reservatórios foram comparadas; a presente revisão permite ordens diferentes por grupo e separa o coeficiente subsuperficial de Prata do coeficiente dos pequenos residuais. A busca incluiu objetivos explícitos para volume, tamanho e horário da segunda crista, mantendo os parâmetros constantes ao longo de todo o evento e as chuvas e observações inalteradas. As triagens finais usam 3 min, iguais ao passo nativo.

## Verificação

O projeto final foi copiado e computado novamente com os DSS existentes, sem reescrever suas chuvas. Foram conferidas 9.581 amostras de 3 min por elemento, séries finitas, horários, unidades M3/S e MM, soma das áreas e todas as 480 horas de chuva em cada zona. A maior diferença de chuva entre os valores originais e o DSS foi inferior a 0,000001 mm, por precisão numérica do armazenamento.

Uma segunda cópia foi computada após remover a ligação da observação de Muçum. A diferença máxima da vazão simulada foi exatamente zero. As métricas foram recalculadas por dois caminhos independentes de código, com concordância numérica. O teste de melhora conjunta contra a referência e contra o modelo anterior de maio, com entradas idênticas, passou para NSE, KGE, pico, horário, subida e recessão; contra o anterior, o viés absoluto também caiu. O CSV native_soil_process_3min.csv permite inspecionar déficit, saturação, infiltração, percolação e componentes de vazão calculados pelo próprio HEC. O diagnóstico soil_hypothesis_audit.json registra o teste de desligamento da contribuição subsuperficial, sem recalibrar os demais parâmetros.

Na janela da segunda onda de 04/05 às 00h UTC até 07/05 às 00h UTC, o NMAE caiu de {soil_audit['second_wave']['previous_NMAE']*100:.2f}% para {soil_audit['second_wave']['new_NMAE']*100:.2f}% em 72 pares reais. Seu pico nativo é {soil_audit['second_wave']['native_peak_m3s']:.1f} m³/s, contra {soil_audit['second_wave']['observed_hourly_peak_m3s']:.1f} m³/s observado, diferença de {soil_audit['second_wave']['peak_error_pct']:+.2f}% e atraso de {soil_audit['second_wave']['peak_time_h']:.2f} h. O erro de pico de {new['peak_error_pct']:+.3f}% da tabela refere-se ao pico principal, não a essa segunda crista.

No teste de retirada da contribuição de percolação, conservando os demais parâmetros, o NSE nativo caiu para {soil_audit['ablation']['native_metrics']['nse']:.4f}. As partições chuva = infiltração + excesso e infiltração = preenchimento do déficit + percolação foram conferidas com resíduos inferiores a 0,03 mm por zona. A saída subsuperficial integrada não ultrapassou a percolação alocada, e a diferença fica em armazenamento ao final. Isso verifica o mecanismo dentro do modelo, sem provar uma causa física única em campo.

## Variante para a crista da segunda onda

`VARIANTE_PICO_SEGUNDA_ONDA` é um segundo perfil nativo calibrado para o mesmo evento, com mais peso no tamanho e no horário da segunda crista. O projeto principal mantém o melhor ajuste global entre esses dois perfis. Os números completos, inclusive o compromisso entre NSE global e segunda crista, estão em `ENTRADAS_E_AUDITORIA/revision2_comparison.json` e `comparacao_mesmas_312_horas.csv`. A variante tem NSE {m.load(m.OUT/'secondary_crest_native.json')['metrics']['86510000']['nse']:.6f}, contra {new['nse']:.6f} no principal. No perfil da crista, o erro de magnitude da segunda onda é {m.load(m.OUT/'revision2_comparison.json')['profiles'][2]['second_wave']['peak_error_pct']:+.3f}% e a defasagem é {m.load(m.OUT/'revision2_comparison.json')['profiles'][2]['second_wave']['peak_time_h']:.2f} h, contra {soil_audit['second_wave']['peak_error_pct']:+.3f}% e {soil_audit['second_wave']['peak_time_h']:.2f} h no principal. O NMAE da janela inteira da segunda onda é menor no principal, razão pela qual ele foi selecionado. Nenhuma variante troca parâmetros em uma data do evento ou altera a chuva.

## Dados de nível e limites

A telemetria arquivada alcança 25,525 m. A nota técnica do SGB relata leitura de 26,00 m na madrugada de 02/05/2024 e também apresenta marcas niveladas em outros locais de Muçum. As posições têm gradiente e não são intercambiáveis com a régua. Essas referências foram preservadas separadamente: não se deslocou o relógio, não se elevou a série em 0,475 m e não se alterou Q para forçar concordância com a marca de campo.

O erro residual da recessão e da segunda onda foi reduzido substancialmente: o NMAE do trecho após o pico é {new['recession_NMAE']*100:.2f}%. O ajuste não comprova batimetria, remanso, operação das usinas ou transferência para outro evento. Por utilizar maio na escolha dos parâmetros, este resultado é **calibração específica de maio**, não validação independente de evento, mesmo que maio tenha sido reservado como holdout em antigos benchmarks de outros modelos. Novembro e Estrela continuam com modelos separados.

## Fontes e reprodução

- ANA/SGB: arquivo histórico de E27_MAY2024 e serviço DadosHidrometeorologicos; cópia integral dos controles em ENTRADAS_E_AUDITORIA/hydro.json. Chuva observada e metadados em rain.json.
- SGB. Nota técnica de levantamento das marcas da grande cheia de maio de 2024, v.3, seção 4.1: https://rigeo.sgb.gov.br/bitstream/doc/24939.5/3/nota_tecnica_levantamento_cheia_2024_v.3.pdf . A leitura de 26,00 m é relatada no texto; não é criada uma vazão medida independente a partir dela.
- USACE. Clark Unit Hydrograph Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/transform/clark-unit-hydrograph-model .
- USACE. Deficit and Constant Loss Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/deficit-and-constant-loss-model .
- USACE. Applying the Linear Reservoir Baseflow Method: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsguides/applying-baseflow-methods-in-hec-hms/applying-the-linear-reservoir-baseflow-method . O exemplo público atual usa 4.14; os arquivos entregues foram executados e verificados em 4.13.
- USACE. Green and Ampt Loss Model: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/green-and-ampt-loss-model .
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
