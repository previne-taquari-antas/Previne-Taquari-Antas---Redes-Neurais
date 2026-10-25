#!/usr/bin/env python3
"""Export auditable topography, native HMS cases and honest physical limits."""
import argparse,ast,copy,csv,hashlib,io,json,os,shutil,zipfile
from datetime import timedelta,timezone
from pathlib import Path
import numpy as np
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from shapely.geometry import shape,mapping
from shapely.ops import transform
from pyproj import Transformer
import build_mucum_floodplain_storage as geo
import export_mucum_estrela_event_calibration as independent
import run_hec_hms_g040_e1_hindcast as hms
from PIL import Image

BRT=timezone(timedelta(hours=-3))
LABELS={'V3_conceptual_reference':'V3 · retenção conceitual',
 'unmodified_upstream_no_extra_storage':'Canal recalibrado · sem retenção externa',
 'local_terrain_Modified_Puls':'Canal + planície local · pico refinado',
 'previous_local_terrain_Modified_Puls':'Planície local · calibração anterior',
 'reach_lateral_capacity_constrained':'Trecho com armazenamento lateral limitado'}

def write_csv(path,rows):
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);atomic_bytes(path,stream.getvalue().encode())

def atomic_bytes(path,data):
    pending=path.with_name(path.name+'.pending')
    with pending.open('wb') as fh:fh.write(data);fh.flush();os.fsync(fh.fileno())
    pending.replace(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('destination',type=Path);args=ap.parse_args();dest=args.destination.resolve();dest.mkdir(parents=True,exist_ok=True)
    pack=dest/'Mucum_planicie_topografia_HEC_2026-10-24'
    if pack.exists():shutil.rmtree(pack)
    pack.mkdir();meta=json.loads((geo.OUT/'terrain_capacity_manifest.json').read_text());audit=json.loads((geo.OUT/'native_geometry_verification.json').read_text());summary=json.loads((geo.OUT/'native_diagnostic_summary.json').read_text())
    if summary['scoring_clock_offset_minutes']!=0:raise RuntimeError('Final comparison must report raw archived clock')
    raw=json.loads((hms.BASE/'historical_calibration_forcing/E24_NOV2023/hydro.json').read_text());strict=copy.deepcopy(raw)
    for c in strict['controls']:
        if str(c['code'])=='86510000':
            for r in c['recent_rows']:
                if r.get('level_source_unit') is None or r['level_source_unit']>1500:r['flow_m3s']=None
    qa=json.loads((geo.OUT/'native_diagnostic/full_Q_clock_corrected.json').read_text())
    records=[];simulations={};pairs_out=[];field_time=hms.utc('2023-11-19T02:45:00Z')
    models=list(summary['models']);prior_path=geo.OUT/'prior_native_diagnostic_summary.json'
    if prior_path.exists():
        previous=copy.deepcopy(next(r for r in json.loads(prior_path.read_text())['models'] if r['name']=='local_terrain_Modified_Puls'))
        if previous['result_file']!=next(r for r in models if r['name']=='local_terrain_Modified_Puls')['result_file']:
            previous['name']='previous_local_terrain_Modified_Puls';models.append(previous)
    lateral=geo.OUT/'lateral_reach_hypothesis/verified_isolated/result.json'
    if lateral.exists():
        ld=json.loads(lateral.read_text())
        if not ld.get('quality_gate_passed') or not ld['isolated_lateral_audit'].get('regional_incremental_capacity',{}).get('passed'):raise RuntimeError('Lateral case lacks independent capacity verification')
        models.append(dict(name='reach_lateral_capacity_constrained',result_file=str(lateral.relative_to(geo.ROOT)),scores=ld['scores'],strict_scores=ld['strict_scores'],
            parameters=dict(channel=json.loads((lateral.parents[1]/'channel_parameters.json').read_text()),lateral=ld['parameters_lateral']),isolated_compute_verified=True))
    for row in models:
        result=geo.ROOT/row['result_file'];d=json.loads(result.read_text());sim=independent.model(result.parent/'project/hec_output_values.csv','86510000')
        pp=independent.independent_pairs(sim,raw,'86510000',d['window']);mm=independent.metrics(pp);sm=independent.metrics(independent.independent_pairs(sim,strict,'86510000',d['window']));qm=independent.metrics(independent.independent_pairs(sim,qa,'86510000',d['window']))
        for k in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(mm[k]-row['scores']['86510000'][k])>1e-8:raise RuntimeError('Independent raw-clock mismatch '+row['name']+' '+k)
        peak_t,peak_q=max(sim,key=lambda z:z[1]);crest=field_time
        rise=[(o,q) for t,o,q in pp if 0<=(crest-t).total_seconds()/3600<=24];fall=[(o,q) for t,o,q in pp if t>crest]
        record=dict(model=row['name'],clock_offset_minutes=0,pairs=mm['pairs'],NSE_raw_clock=mm['nse'],KGE_raw_clock=mm['kge'],bias_pct=mm['pbias_pct'],NSE_strict_15m_raw_clock=sm['nse'],
            peak_error_vs_available_telemetry_pct=100*(peak_q/max(o for t,o,q in pp)-1),peak_minus_SGB_reported_time_h=(peak_t-field_time).total_seconds()/3600,
            rise_relative_MAE=sum(abs(o-q) for o,q in rise)/sum(o for o,q in rise),recession_relative_MAE=sum(abs(o-q) for o,q in fall)/sum(o for o,q in fall),
            NSE_if_QA105_applied_to_same_native_series=qm['nse'],source_flow_transformed=(row['name']=='V3_conceptual_reference'))
        # Conditional stage diagnostic using the same archived high-stage rating,
        # not an independent hydraulic water-surface solution.
        stage=(peak_q/31.3809)**(1/1.85)-2.05
        record.update(peak_stage_from_dated_rating_m=stage,stage_difference_vs_SGB_sensor_23_02_m=stage-23.02)
        records.append(record);simulations[row['name']]=sim
        for t,o,q in pp:pairs_out.append(dict(model=row['name'],time_utc=independent.iso(t),observed_telemetry_Q_m3s=o,simulated_Q_m3s=q))
        name={'V3_conceptual_reference':'REFERENCIA_V3_CONCEITUAL','unmodified_upstream_no_extra_storage':'CANAL_SEM_RETENCAO_EXTERNA','local_terrain_Modified_Puls':'HEC_PLANICIE_LOCAL_NATIVO','previous_local_terrain_Modified_Puls':'HEC_PLANICIE_LOCAL_ANTERIOR','reach_lateral_capacity_constrained':'HEC_ARMAZENAMENTO_LATERAL_LIMITADO'}[row['name']]
        case=pack/name;shutil.copytree(result.parent/'project',case)
        for f in case.iterdir():
            if f.is_file() and (f.name=='run.script' or f.suffix in ['.log','.access','.pending']):f.unlink()
        geo.save(case/'parametros_resultados.json',dict(parameters=row['parameters'],metrics=record,native_result=d,research_only=True))
    write_csv(pack/'comparacao_modelos_mesma_base.csv',records);write_csv(pack/'pares_observado_simulado_relogio_bruto.csv',pairs_out)
    geo.save(pack/'manifesto_modelos.json',dict(summary,models=models))
    r=next(r for r in summary['models'] if r['name']=='local_terrain_Modified_Puls');rp=geo.ROOT/r['result_file'];script=(rp.parent/'project/run.script').read_text();source=ast.literal_eval(next(l for l in script.splitlines() if l.startswith('source_values=')).split('=',1)[1])['86472000']
    native=json.loads(rp.read_text());axis=hms.hourly_axis(hms.utc(native['window']['start_utc']),hms.utc(native['window']['end_utc']));original=hms.source_hourly(raw,'86472000',axis)
    if any(a!=b for a,b in zip(source,original)):raise RuntimeError('Native geometry case modified upstream Q')
    write_csv(pack/'montante_original_e_entrada_HEC.csv',[dict(time_utc=independent.iso(t),original_Q_m3s=a,HEC_input_Q_m3s=b) for t,a,b in zip(axis,original,source)])
    geometry=pack/'GEOMETRIA';geometry.mkdir()
    for f in ['curva_cota_area_volume.csv','curva_armazenamento_descarga_HMS.csv','mapgeo2015_local_grid.json','mucum_terreno_MAPGEO2015_2m.tif','planicie_conectada.geojson','terrain_capacity_manifest.json','native_geometry_verification.json','native_diagnostic_QA105_summary.json','rawclock_channel_selection.json']:
        shutil.copy2(geo.OUT/f,geometry/f)
    shutil.copy2(geo.OUT/'native_diagnostic_rawclock/scoring_clock_manifest.json',pack/'auditoria_relogio.json')
    shutil.copy2(rp.parent/'project/reservoir_native_values.csv',geometry/'reservatorio_saida_nativa.csv')
    for f in ['archived_rating_consistency_audit.json','archived_rating_comparison.csv','peak_timing_selection.json','peak_timing_selected_parameters.json','balanced_selection.json','balanced_selected_parameters.json']:
        if (geo.OUT/f).exists():shutil.copy2(geo.OUT/f,pack/f)
    if (geo.OUT/'peak_timing_search/evaluations.json').exists():shutil.copy2(geo.OUT/'peak_timing_search/evaluations.json',pack/'busca_parametros_resultados.json')
    if lateral.exists():
        reach=pack/'HIPOTESE_TRECHO';reach.mkdir();source=lateral.parents[1]
        for name in ['screening.json','isolated_verification.json','regional_capacity_screening.json','regional_hourly_capacity.json','regional_terrain_MAPGEO2015_30m.tif','unconstrained_screening.json','unconstrained_isolated_verification.json','unconstrained_regional_capacity_screening.json']:
            shutil.copy2(source/name,reach/name)
        for name in ['anadem_reach_egm2008.tif','anadem_reach_egm2008.tif.source.json','egm2008_local_geoid.tif','egm2008_local_geoid.tif.source.json']:
            shutil.copy2(geo.ROOT.parent/'inputs'/name,reach/name)
    geo.save(geo.OUT/'independent_model_comparison.json',records)
    # Figure: show the actual mapped footprint, capacity envelope and raw-clock
    # hydrograph. The volume bars explicitly retain their different domains.
    fig,axes=plt.subplots(2,2,figsize=(16,11));fig.subplots_adjust(left=.065,right=.98,top=.86,bottom=.15,hspace=.37,wspace=.25)
    with rasterio.open(geo.OUT/'mucum_terreno_MAPGEO2015_2m.tif') as ds:
        z=ds.read(1,masked=True);extent=[ds.bounds.left/1000,ds.bounds.right/1000,ds.bounds.bottom/1000,ds.bounds.top/1000]
    ax=axes[0,0];ax.imshow(z,extent=extent,origin='upper',cmap='terrain',vmin=32,vmax=115,alpha=.8)
    polygons=json.loads((geo.OUT/'planicie_conectada.geojson').read_text());to_utm=Transformer.from_crs(4326,32722,always_xy=True).transform
    for f in polygons['features']:
        if f['properties']['gauge_stage_m']!=geo.PEAK_STAGE:continue
        p=transform(to_utm,shape(f['geometry']))
        for poly in ([p] if p.geom_type=='Polygon' else p.geoms):
            xy=np.array(poly.exterior.coords);ax.fill(xy[:,0]/1000,xy[:,1]/1000,color='#087fa5',alpha=.85,zorder=3)
    gx,gy=to_utm(geo.GAUGE_LON,geo.GAUGE_LAT);ax.scatter([gx/1000],[gy/1000],marker='*',s=140,c='#d5382f',edgecolors='white',zorder=5)
    ax.text(gx/1000+.035,gy/1000+.035,'Régua Muçum',fontsize=10,fontweight='bold')
    ax.set_title('Terreno de drone e planície local conectada',loc='left',fontweight='bold',fontsize=12);ax.set_xlabel('Leste UTM 22S (km)');ax.set_ylabel('Norte UTM 22S (km)')
    cap=meta['representative_capacity'];ax.text(.02,.97,f'Cenário central: {cap["connected_floodplain_area_m2"]/10000:.2f} ha a montante\nCota da série horária: 22,975 m · grade de análise: 2 m',va='top',transform=ax.transAxes,fontsize=9,bbox=dict(facecolor='white',alpha=.9,edgecolor='none'))
    ax.plot([extent[0]+.1,extent[0]+.6],[extent[2]+.08]*2,color='#25333d',lw=3);ax.text(extent[0]+.35,extent[2]+.11,'500 m',ha='center',fontsize=9)
    ax=axes[0,1];allrows=list(csv.DictReader((geo.OUT/'curva_cota_area_volume.csv').open()));colors={50:'#aab8c0',100:'#087f8c',150:'#87939c'}
    for width in [50,100,150]:
        rr=[r for r in allrows if int(r['channel_half_width_m'])==width and r['domain']=='upstream_of_gauge'];ax.plot([float(r['gauge_stage_m']) for r in rr],[float(r['connected_floodplain_total_volume_m3'])/1e6 for r in rr],lw=2 if width==100 else 1.2,color=colors[width],label=f'Exclusão do canal: ±{width} m')
    ax.axvline(geo.PEAK_STAGE,color='#ad6139',ls=':',lw=1.4,label='Pico da telemetria horária');ax.set_xlim(10,26.5);ax.set_ylabel('Volume no recorte a montante (milhão de m³)');ax.set_xlabel('Cota da régua (m), usando zero SGB 33,985 m');ax.legend(fontsize=8,frameon=False,loc='upper left');ax.set_title('Curva cota–volume derivada do terreno',loc='left',fontweight='bold',fontsize=12)
    ax=axes[1,0]
    for name,col,lw in [('V3_conceptual_reference','#bd893b',1.5),('previous_local_terrain_Modified_Puls','#8295af',1.1),('local_terrain_Modified_Puls','#087f8c',2.)]:
        if name not in simulations:continue
        sim=simulations[name];ax.plot([t for t,q in sim],[q for t,q in sim],color=col,lw=lw,label=LABELS[name])
    obs=next(c for c in raw['controls'] if str(c['code'])=='86510000')['recent_rows']
    for high in [False,True]:
        rr=[r for r in obs if r.get('flow_m3s') is not None and (r.get('level_source_unit',0)>1500)==high]
        ax.scatter([hms.utc(r['time_utc']) for r in rr],[r['flow_m3s'] for r in rr],s=12,facecolors='white' if high else '#29394b',edgecolors='#8a98a4' if high else '#29394b',zorder=4,label='Q >15 m: curva-chave incerta' if high else 'Q disponível · relógio bruto')
    ax.axvline(field_time,color='#7e8992',ls=':',label='Hora do pico publicada pelo SGB');ax.xaxis.set_major_locator(mdates.DayLocator(interval=2,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=BRT));ax.set_xlabel('Novembro/2023 · horário de Brasília');ax.set_ylabel('Vazão (m³/s)');ax.legend(fontsize=7.5,frameon=False);ax.set_title('Saídas do HEC comparadas sem deslocar a observação',loc='left',fontweight='bold',fontsize=12)
    ax=axes[1,1];local=[r for r in allrows if float(r['channel_half_width_m'])==100 and float(r['gauge_stage_m'])==geo.PEAK_STAGE]
    whole=next(float(r['connected_floodplain_total_volume_m3']) for r in local if r['domain']=='entire_local_drone_footprint')
    volumes=[cap['connected_floodplain_total_volume_m3']/1e6,whole/1e6,audit['V3_conceptual_max_storage_m3']/1e6]
    ax.barh([2,1,0],volumes,color=['#087f8c','#9eafb9','#bd893b'],height=.55)
    ax.set_yticks([2,1,0],['Recorte a montante\nno MDT local','Todo MDT local\n(inclui jusante)','Retenção V3\naplicada na entrada JJ'])
    ax.set_xlim(0,max(volumes)*1.14)
    for y,x in zip([2,1,0],volumes):ax.text(x+1,y,f'{x:.2f}',va='center',fontsize=10,fontweight='bold')
    ax.set_xlabel('Milhão de m³');ax.set_title('Escalas de armazenamento e seus domínios',loc='left',fontweight='bold',fontsize=12)
    ax.text(.02,.97,'O MDT local não cobre o trecho inteiro de 44 km.\nSeus volumes não validam a retenção distribuída da V3.',transform=ax.transAxes,va='top',fontsize=9)
    for ax in axes.ravel():ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.13)
    fig.suptitle('Muçum · topografia da planície e hipótese testada no HEC-HMS',x=.025,y=.975,ha='left',fontweight='bold',fontsize=19)
    fig.text(.025,.918,'Zero da régua recuperado no SGB + MAPGEO2015 oficial + terreno existente. Sem nova campanha de campo.',fontsize=12,color='#4a5965')
    fig.text(.025,.035,'Capacidade derivada do MDT, com datum do voo ainda dependente de metadados de controle. Canal e limites de margem são aproximações testadas em sensibilidade.\nModelo HEC: Modified Puls para a planície local e propagação calibrada por evento; montante original preservado. Curva-chave extrema, batimetria e remanso não são validados por este teste.',fontsize=9,color='#4a5965')
    image=dest/'Mucum_planicie_topografia_HEC_2026-10-24.png';buffer=io.BytesIO();fig.savefig(buffer,format='png',dpi=170,facecolor='white');plt.close(fig)
    content=buffer.getvalue();Image.open(io.BytesIO(content)).verify();atomic_bytes(image,content);atomic_bytes(pack/image.name,content)
    table='\n'.join(f'| {LABELS[r["model"]]} | {r["NSE_raw_clock"]:.4f} | {r["peak_error_vs_available_telemetry_pct"]:+.2f}% | {r["peak_minus_SGB_reported_time_h"]:+.2f} h | {r["NSE_strict_15m_raw_clock"]:.4f} |' for r in records)
    notes=f'''# Muçum: planície quantificada por topografia e teste nativo HEC-HMS

Foi calculada uma curva cota–área–volume para a parte da planície coberta pelo MDT de drone existente, e ela foi inserida como tabela Storage-Outflow em um reservatório Modified Puls nativo do HEC-HMS 4.13, imediatamente antes do controle Muçum. Isso é uma hipótese de armazenamento concentrado, não uma nova barragem nem uma solução hidráulica 1D/2D validada.

## Resultado geométrico e domínio

O raster de origem é `mdt_mucum_drone_1m.tif`, com {meta['terrain']['valid_area_m2']/1e6:.3f} km² válidos no recorte de análise. A grade foi reamostrada para 2 m em UTM 22S. O SGB publica o zero da régua 86510000 em 33,985 m, com referência MAPGEO2015 (Tabela 2 do trabalho de Marcuzzo, Silva e Mendes, 2025). A nota de marcas de 2024 usa 33,96 m; a diferença é 0,025 m e não autoriza tratar a altitude cadastral de 240 m como zero da régua.

A grade oficial MAPGEO2015 foi recuperada do instalador público do IBGE, sem executar o programa Windows. A interpolação no local da régua resulta em N={meta['terrain']['geoid_at_gauge_m']:.4f} m, coerente com os 6,47 m da nota de campo do SGB. O MDT bruto é tratado como altitude elipsoidal conforme o gerador original do projeto: H=h−N. O arquivo anterior `_ortho` usa hgeoHNOR2020 e não foi misturado silenciosamente com MAPGEO2015. A data do voo, a referência original e a acurácia vertical dos pontos de controle ainda precisam do relatório do levantamento. Não houve novo levantamento de campo.

Na cota de 22,975 m da série horária de novembro/2023, a superfície correspondente está em 56,960 m MAPGEO2015. No cenário central, a parte coberta pelo drone e atribuída a montante da régua soma {cap['connected_floodplain_area_m2']/10000:.2f} ha conectados, {cap['connected_floodplain_total_volume_m3']/1e6:.3f} milhão de m³ de volume fora da faixa adotada para o canal, e {cap['incremental_volume_above_stage18_m3']/1e6:.3f} milhão de m³ adicionais em relação à cota 18 m. Os 18 m são referência de início de danos do SGB, não levantamento da borda física do canal.

A meia largura excluída do canal foi testada em 50, 100 e 150 m, pois as linhas de margem medidas não foram recuperadas. Na cota do pico, o volume a montante varia aproximadamente de 0,125 a 2,451 milhões de m³. Há ainda teste de desnível água–terreno de ±0,5 e ±1 m no manifesto. Foram mantidos apenas pixels válidos, hidrologicamente conectados à faixa fluvial; depressões isoladas e NoData não viraram armazenamento. A repartição montante/jusante usa a projeção mais próxima ao longo do eixo BHO6, não limites administrativos.

O MDT local inclui áreas a jusante da régua. Todo o seu recorte soma cerca de {whole/1e6:.2f} milhões de m³ no cenário central; esse total não foi usado como armazenamento a montante. O domínio mapeado não cobre o trecho completo de Linha José Júlio a Muçum. A capacidade da planície local não explica, sozinha, os {audit['V3_conceptual_max_storage_m3']/1e6:.2f} milhões de m³ máximos retidos na hipótese conceitual V3. Isso não prova a impossibilidade desse volume no vale inteiro: o restante do trecho não tem aqui a mesma cobertura de drone.

## Relógio e comparação na mesma base

O artigo original de Marcuzzo e Pinto relata o pico em 18/11/2023 às 23h45 locais, com 23,02 m no sensor e 23,20 m por leitura da Defesa Civil. A série horária arquivada tem seu máximo de 22,975 m entre 02h e 03h UTC de 19/11, intervalo que contém 02h45 UTC. A antiga correção de −105 min desloca esse intervalo para mais cedo e não é corroborada por esse registro independente para novembro/2023. Isso favorece o relógio bruto neste evento, sem provar todos os horários da série ou invalidar outros eventos. Os dados originais e a hipótese QA105 permanecem preservados.

Todos os modelos abaixo foram reavaliados com os horários brutos originais. Não se compara o NSE 0,9972 da V3 sob QA105 diretamente com um NSE calculado em outro relógio. O CSV fornece também o NSE sob QA105 para a mesma saída nativa, tornando a diferença auditável. A propagação Muskingum foi recalibrada apenas para Muçum/novembro de 2023; cada cidade e evento continuam com parâmetros próprios.

| Modelo | NSE, relógio bruto | Erro do pico contra Q disponível | Pico menos horário publicado pelo SGB | NSE até 15 m |
| --- | --- | --- | --- | --- |
{table}

O cenário de planície local mantém **todas as vazões observadas de montante intactas**. O gerador não aplica a retenção externa da V3. Nesse teste de planície local, a área e a curva de armazenamento são fixadas pelo terreno; somente a propagação do canal e os parâmetros de perdas/transformação/recessão das áreas incrementais foram calibrados na busca. A curva de descarga foi tomada dos segmentos ANA arquivados com vigência 06/09–31/12/2023, em metros, sem ajustar seus coeficientes ao hidrograma alvo. Os rótulos derivados h0_cm/h0_m desse arquivo têm ambiguidade de unidade; foram usados os coeficientes brutos e a equação A(h−h0)^n. Trata-se de vazão extrema condicionada à curva-chave, não medição independente de cheia.

## Verificação nativa e abertura

Abra `g040_e1_hindcast.hms` em cada pasta e compute `Hindcast` no HEC-HMS 4.13. `HEC_PLANICIE_LOCAL_NATIVO` é o modelo com geometria; `CANAL_SEM_RETENCAO_EXTERNA` isola o efeito da planície; `REFERENCIA_V3_CONCEITUAL` conserva o ajuste anterior como comparação, incluindo sua entrada efetiva modificada.

O modelo geométrico foi copiado e computado novamente em pasta isolada, com 4.781 valores de 3 min em cada um dos seis controles e no reservatório. O DSS retorna armazenamento em `1000 M3`; a conversão foi conferida contra a curva geométrica em m³. O máximo nativo foi {audit['native_storage_max_m3']/1e6:.3f} milhão de m³, correspondente à cota simulada e não necessariamente à cota observada. O balanço nativo integrado apresentou resíduo de {audit['native_storage_balance_residual_m3']:.3g} m³. A diferença máxima entre a entrada de montante do modelo geométrico e o observado original foi {audit['unmodified_upstream_max_abs_difference_m3s']:.1f} m³/s. As métricas exportadas foram recalculadas com NumPy a partir das séries nativas. Não há preenchimento de Q ausente.

## Alcance e pendências concretas

O resultado entregue é uma geometria topográfica derivada do levantamento existente, associada a uma referência de régua medida pelo SGB. Não é uma nova planície levantada em campo nem validação hidráulica completa. Faltam o relatório de pontos de controle/data do voo, linhas de margem, batimetria numérica, estruturas e cobertura do vale a montante. A superfície horizontal local não resolve declive longitudinal, remanso do Guaporé ou tempos de troca com a planície. O terreno pode ser posterior às cheias de 2023/2024 e não estabelece a geometria histórica sem essa verificação. O pico residual e os compromissos das métricas constam da tabela: não foram escondidos por nova alteração do hidrograma observado.

## Fontes e reprodução

- Marcuzzo, F. F. N.; Silva, E. D.; Mendes, D. V. Levantamento dos zeros ortométricos das estações fluviométricas da hidrologia do SGB no RS e SC. 2025. Tabela 2 e métodos: {geo.SOURCE_URL}
- Marcuzzo, F. F. N.; Pinto, E. J. A. Inundações históricas de 2023 na bacia do rio Taquari-Antas no município de Muçum/RS e os seus tempos de retorno. 2024. p. 4–5: https://rigeo.sgb.gov.br/bitstreams/98db393c-19a5-4a87-9d29-46b3a2985e74/download
- SGB. Nota técnica de levantamento dos níveis das marcas da grande cheia de maio/2024, versão 2, Tabela 2: https://rigeo.sgb.gov.br/bitstream/doc/24939.5/1/nota_tecnica_levantamento_cheias_2024_rs_versao%202.pdf
- IBGE. MAPGEO2015, grade SIRGAS2000 do instalador oficial: {geo.MAPGEO_URL}
- USACE. Outflow Curve Routing, HEC-HMS 4.13: https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.13/reservoir-elements/outflow-curve-routing

Os scripts `build_mucum_floodplain_storage.py`, `refine_mucum_native_rawclock.py`, `test_mucum_terrain_storage_native.py`, `verify_mucum_terrain_storage.py` e `export_mucum_floodplain_research.py` estão no repositório PREVINE, PR 278. A grade geoidal local em JSON acompanha o pacote e pode substituir a grade completa na reprodução da geometria. O MDT bruto e o eixo BHO6 permanecem no repositório; o raster derivado, curvas, polígonos, auditorias e projetos portáveis acompanham este pacote.
'''
    if any(r['model']=='previous_local_terrain_Modified_Puls' for r in records):
        new=next(r for r in records if r['model']=='local_terrain_Modified_Puls');old=next(r for r in records if r['model']=='previous_local_terrain_Modified_Puls')
        selection=json.loads((geo.OUT/'peak_timing_selection.json').read_text());rating_audit=json.loads((geo.OUT/'archived_rating_consistency_audit.json').read_text())
        notes+=f'''\n## Refinamento do pico e custo no tempo de chegada\n\nA nova busca executou {selection['evaluations']} casos nativos de canal no mesmo evento. A escolha limita o desvio da hora publicada do pico a 1 h, NSE total mínimo 0,98, NSE até 15 m mínimo 0,95 e viés absoluto máximo 3%. Dentro desse conjunto foi minimizado o erro absoluto do pico, com penalidade de 0,5 ponto percentual por hora de desvio. Essa é seleção e calibração no mesmo evento, sem validação em outro evento. A geometria e a vazão de montante ficaram fixas.\n\nO erro do pico caiu de {old['peak_error_vs_available_telemetry_pct']:.2f}% para {new['peak_error_vs_available_telemetry_pct']:.2f}%; o desvio de horário passou de {old['peak_minus_SGB_reported_time_h']:.2f} h para {new['peak_minus_SGB_reported_time_h']:.2f} h. O NSE mudou de {old['NSE_raw_clock']:.5f} para {new['NSE_raw_clock']:.5f}; o NSE até 15 m mudou de {old['NSE_strict_15m_raw_clock']:.5f} para {new['NSE_strict_15m_raw_clock']:.5f}. Portanto há melhora da amplitude com perda de precisão temporal e de ajuste global; a pasta HEC_PLANICIE_LOCAL_ANTERIOR permanece disponível para quem prioriza a chegada da onda. A subida e a recessão de cada candidato estão no CSV, sem ocultar a troca.\n\nA auditoria de {rating_audit['compared_pairs']} pares horários também identificou que a vazão arquivada e a curva-chave datada não coincidem. No nível horário de 22,975 m, a curva datada retorna 12.124,32 m³/s, enquanto o par arquivado contém 11.434,925 m³/s, diferença de aproximadamente 6,03%. O importador recupera Vazao e Nivel separadamente do serviço ANA/SGB; não aplica essa curva localmente. A média de uma relação não linear difere da relação aplicada à média, e os pares originais sub-horários não estão neste arquivo, impedindo atribuir exatamente a causa à agregação ou à revisão de curva. Nenhum Q observado foi substituído. O ajuste empírico incluído é apenas diagnóstico, sem estatuto de curva oficial.\n\nInvertendo a curva datada, o pico simulado equivale a {new['peak_stage_from_dated_rating_m']:.3f} m, contra 23,02 m do sensor e 23,20 m de leitura manual publicados pelo SGB. Essa conversão é condicional à curva-chave e não constitui solução hidráulica ou medição independente da lâmina. O erro de vazão extrema continua condicionado à consistência da curva usada pelo serviço.\n'''
    balanced_path=geo.OUT/'balanced_selection.json'
    if balanced_path.exists():
        balanced=json.loads(balanced_path.read_text())
        if balanced['selected'] is None:
            notes+=f"\nTambém foram testadas {balanced['additional_cases']} combinações adicionais próximas à calibração anterior, totalizando {balanced['evaluations_total']} casos de canal. Nenhuma satisfez simultaneamente a redução do erro do pico, NSE do canal ≥0,986, NSE até 15 m ≥0,9675 e desvio do horário do pico ≤15 min. Isso descreve esta busca limitada, sem provar impossibilidade de outro ajuste. Por isso a alternativa de pico refinado não substitui silenciosamente a versão anterior como melhor modelo global.\n"
    if lateral.exists():
        ld=json.loads(lateral.read_text());lm=ld['independent_metrics'];la=ld['isolated_lateral_audit'];cap=la['regional_incremental_capacity'];lp=ld['parameters_lateral']
        notes+=f'''\n## Nova hipótese: armazenamento lateral limitado no trecho completo\n\nA alternativa **HEC_ARMAZENAMENTO_LATERAL_LIMITADO** melhora conjuntamente o pico, a subida, a recessão e o ajuste global neste evento. Ela conserva a entrada original de Linha José Júlio e o relógio bruto, e mantém a curva da planície local. Uma bifurcação nativa Inflow-Diversion Table envia uma fração de Q acima do limiar a um reservatório Modified Puls nativo. A água retorna ao mesmo sistema fluvial por uma junção, antes da propagação no canal. Trata-se de representação concentrada de armazenamento lateral do trecho, não de uma barragem real nem de localização hidráulica dos intercâmbios.\n\nO limiar calibrado é {lp['threshold_m3s']:.1f} m³/s, a fração acima do limiar é {lp['fraction']:.4f} e o tempo de retorno linear é {lp['tau_h']:.2f} h. A propagação total JJ–Muçum foi recalibrada para {lp['k_g1']:.3f} h. O limiar de intercâmbio não é uma margem medida. A tabela de armazenamento usa retorno linear até 99% da capacidade do cenário; acima desse ponto, representa retorno de emergência ao rio, impedindo tratar o reservatório como armazenamento ilimitado. Esse ramo de emergência não foi acionado no evento calibrado.\n\nA hipótese inicialmente otimizada, sem limite regional, reproduziu muito bem o hidrograma mas exigiu cerca de 82,02 milhões de m³ adicionais. Ela foi rejeitada como escolha final diante do teste geométrico incremental e permanece documentada apenas como diagnóstico. A seleção final foi reotimizada com limite de armazenamento.\n\nPara esse limite foi recuperado um recorte regional **ANADEM de 30 m**, sem misturá-lo ao drone. A referência EGM2008 foi convertida explicitamente: H_MAPGEO2015 = H_ANADEM_EGM2008 + N_EGM2008 − N_MAPGEO2015, usando a grade EGM2008 distribuída pelo PROJ e a MAPGEO2015 do IBGE. O perfil longitudinal da água é uma interpolação linear entre os níveis observados nas duas réguas, com zeros SGB 61,140 m em JJ e 33,985 m em Muçum. As faixas de canal de ±50/100/150 m e desvios verticais de ±1 m estão no teste de sensibilidade. ANADEM, resolução de 30 m e perfil linear são triagem geométrica, não levantamento de margens, batimetria ou solução de remanso. A permanência dos zeros entre a época do evento e a referência publicada e as mudanças morfológicas do vale ainda dependem de controle histórico.\n\nO cenário central tem máximo horário de {cap['max_event_land_volume_m3']/1e6:.2f} milhões de m³ fora da faixa do canal. Antes da primeira derivação, {cap['reference_at_first_diversion_m3']/1e6:.2f} milhões de m³ já estavam preenchidos. Portanto, o limite adicional é {cap['additional_capacity_m3']/1e6:.2f} milhões de m³, com orçamento de {cap['budget_with_two_percent_margin_m3']/1e6:.2f} milhões após margem computacional de 2%, que não representa a incerteza do levantamento. O máximo nativo final foi {cap['required_native_max_storage_m3']/1e6:.2f} milhões de m³ adicionais. Não se comparou armazenamento novo a volume total já inundado. O limite usa a capacidade máxima do evento; a retenção na recessão pressupõe histerese/água represada na planície. A superfície real da água armazenada e a troca dinâmica com o rio ainda não foram validadas.\n\nResultado do recálculo isolado: NSE {lm['nse']:.5f}; KGE {lm['kge']:.5f}; NSE até 15 m {lm['strict_NSE']:.5f}; erro do pico {lm['peak_error_pct']:+.2f}%; pico menos horário publicado pelo SGB {lm['peak_time_minus_SGB_h']:+.2f} h; viés {lm['pbias_pct']:+.2f}%; erro relativo médio na subida {lm['rise_NMAE']*100:.2f}% e na recessão {lm['recession_NMAE']*100:.2f}%. A hora observada provém de publicação e a série é horária: o passo de 3 min do modelo não cria precisão observacional de 3 min.\n\nO projeto entregue foi copiado e computado com os DSS existentes, **sem reescrever a entrada nem as tabelas**. As 4.781 amostras de cada série se repetiram, a diferença da entrada original foi zero, o resíduo máximo da divisão de vazões foi {la['diversion_split_max_residual_m3s']:.3g} m³/s e o balanço do armazenamento adicional apresentou resíduo de {la['FP_REACH']['balance_residual_m3']:.3g} m³. A água derivada entra no reservatório e toda a descarga retornada entra na junção, com armazenamento remanescente explicitado.\n\nOs critérios de bom ajuste adotados antes da escolha final foram: NSE ≥0,99, KGE ≥0,95, NSE até 15 m ≥0,97, módulo do erro do pico ≤5%, desvio do pico ≤1 h, módulo do viés ≤3% e erros relativos na subida/recessão ≤5%. Todos foram atendidos no evento de calibração. Isso é calibração específica de Muçum/novembro de 2023, condicionada aos dados de vazão e às hipóteses geométricas, **sem validação independente em outro evento ou comprovação hidráulica de campo**. Estrela mantém modelos separados.\n\nFontes regionais: ANADEM/UFRGS/ANA, https://hge-iph.github.io/anadem/ ; Nota Técnica ANA nº 3/2025/CCOGI/SHE-SEI (referência vertical EGM2008), https://metadados.snirh.gov.br/geonetwork/srv/api/records/93664c15-1ff8-4e87-bbed-2bb69d321309/attachments/SEI_0031152_Nota_Tecnica_3.pdf ; grade EGM2008, https://cdn.proj.org/us_nga_egm08_25.tif ; documentação USACE sobre desvio e retorno nativo, https://www.hec.usace.army.mil/confluence/hmsdocs/hmsum/4.13/source-junction-diversion-and-sink-elements/diversion .\n'''
        # Keep the earlier terrain figure inside the package; the main preview
        # now shows the actual calibration improvement and storage constraint.
        shutil.copy2(image,pack/'Geometria_local_etapa_anterior.png')
        from plot_mucum_lateral_calibration import make_figure
        content=make_figure(records,simulations,raw,ld,lateral.parent/'project/lateral_native_values.csv')
        atomic_bytes(image,content);atomic_bytes(pack/image.name,content)
    atomic_bytes(pack/'LEIA-ME.md',notes.encode());atomic_bytes(geo.ROOT/'docs/HEC_MUCUM_PLANICIE_20261024.md',notes.encode())
    geo.save(pack/'sha256.json',{str(p.relative_to(pack)):hashlib.sha256(p.read_bytes()).hexdigest() for p in pack.rglob('*') if p.is_file()})
    archive=dest/(pack.name+'.zip');pending=archive.with_suffix('.zip.pending')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pack.rglob('*')):
            if f.is_file():z.write(f,str(f.relative_to(dest)))
    with zipfile.ZipFile(pending) as z:
        if z.testzip():raise RuntimeError('Invalid ZIP CRC')
        for name in z.namelist():
            if name.endswith('.png'):Image.open(io.BytesIO(z.read(name))).verify()
    with pending.open('rb') as f:os.fsync(f.fileno())
    pending.replace(archive)
    print(json.dumps(dict(archive=str(archive),image=str(image),comparison=records),ensure_ascii=False))

if __name__=='__main__':main()
