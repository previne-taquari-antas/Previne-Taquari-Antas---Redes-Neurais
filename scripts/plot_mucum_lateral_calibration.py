#!/usr/bin/env python3
"""Scientific figure made only from verified native outputs and archived data."""
import csv,io
from datetime import timedelta,timezone
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from PIL import Image
import run_hec_hms_g040_e1_hindcast as hms

BRT=timezone(timedelta(hours=-3))

def make_figure(records,simulations,raw,native,values_path):
    fig,axes=plt.subplots(2,2,figsize=(16,10.6));fig.subplots_adjust(left=.07,right=.97,bottom=.13,top=.83,hspace=.4,wspace=.25)
    selected='reach_lateral_capacity_constrained';old='previous_local_terrain_Modified_Puls';peak='local_terrain_Modified_Puls'
    field=hms.utc('2023-11-19T02:45:00Z')
    obs=next(c for c in raw['controls'] if str(c['code'])=='86510000')['recent_rows']
    colors={old:'#8594a9',peak:'#c68c3e',selected:'#85294e'}
    labels={old:'Calibração anterior · planície local',peak:'Alternativa anterior · pico +8,15%',selected:'Novo HEC · armazenamento lateral limitado'}
    for ax in axes[0]:
        for name in [old,peak,selected]:
            sim=simulations[name];ax.plot([t for t,q in sim],[q for t,q in sim],color=colors[name],lw=2.2 if name==selected else 1.15,label=labels[name])
        for high in [False,True]:
            rr=[r for r in obs if r.get('flow_m3s') is not None and (r.get('level_source_unit',0)>1500)==high]
            ax.scatter([hms.utc(r['time_utc']) for r in rr],[r['flow_m3s'] for r in rr],s=13,facecolors='white' if high else '#263a46',edgecolors='#73828b' if high else '#263a46',lw=.7,zorder=5,label='Q arquivado acima de 15 m' if high else 'Q arquivado até 15 m')
        ax.axvline(field,color='#727e87',ls=':',lw=1.2,label='Hora do pico publicada pelo SGB')
        ax.set_ylabel('Vazão (m³/s)');ax.set_xlabel('Novembro/2023 · horário de Brasília')
    axes[0,0].xaxis.set_major_locator(mdates.DayLocator(interval=2,tz=BRT));axes[0,0].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=BRT))
    axes[0,0].set_title('Hidrograma completo · mesma entrada e observação',loc='left',fontweight='bold',fontsize=12)
    axes[0,0].legend(fontsize=7.5,frameon=False,loc='upper right')
    axes[0,1].set_xlim(field-timedelta(hours=17),field+timedelta(hours=18));axes[0,1].set_ylim(8000,13100)
    axes[0,1].xaxis.set_major_locator(mdates.HourLocator(interval=6,tz=BRT));axes[0,1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m\n%Hh',tz=BRT))
    axes[0,1].set_title('Detalhe da subida e do pico',loc='left',fontweight='bold',fontsize=12)
    new=next(r for r in records if r['model']==selected);before=next(r for r in records if r['model']==old);previous=next(r for r in records if r['model']==peak)
    axes[0,1].text(.03,.96,f"Último entregue → novo HEC\nErro do pico: +{previous['peak_error_vs_available_telemetry_pct']:.2f}% → +{new['peak_error_vs_available_telemetry_pct']:.2f}%\nNSE: {previous['NSE_raw_clock']:.4f} → {new['NSE_raw_clock']:.4f}",transform=axes[0,1].transAxes,va='top',fontsize=10.5,fontweight='bold',bbox=dict(facecolor='white',alpha=.92,edgecolor='none'))
    rows=sorted([r for r in csv.DictReader(open(values_path)) if r['element']=='FP_REACH' and r['variable']=='STORAGE'],key=lambda r:int(r['time_value']))
    times=[hms.dss_time_to_utc(r['time_value']) for r in rows];storage=np.array([float(r['value'])*1000/1e6 for r in rows])
    if len(set(times))!=len(times) or any(b<=a for a,b in zip(times,times[1:])):raise RuntimeError('Storage plot has unordered or duplicate native times')
    ax=axes[1,0];cap=native['isolated_lateral_audit']['regional_incremental_capacity'];available=cap['additional_capacity_m3']/1e6
    ax.fill_between(times,storage,color='#85294e',alpha=.15);ax.plot(times,storage,color='#85294e',lw=2,label='Armazenamento adicional nativo')
    ax.axhline(available,color='#435d6b',ls='--',lw=1.4,label=f'Capacidade adicional do cenário: {available:.2f} milhões de m³')
    ax.set_ylim(0,available*1.17);ax.set_ylabel('Armazenamento adicional (milhão de m³)');ax.set_xlabel('Novembro/2023 · horário de Brasília')
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2,tz=BRT));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m',tz=BRT));ax.legend(fontsize=8,frameon=False,loc='upper right')
    ax.set_title('Limite regional aplicado à hipótese de armazenamento',loc='left',fontweight='bold',fontsize=12)
    ax.text(.98,.48,f"Máximo nativo: {storage.max():.2f} milhões de m³\nCapacidade regional máxima menos\nvolume já preenchido antes do intercâmbio.",transform=ax.transAxes,ha='right',fontsize=9,color='#43515c')
    ax=axes[1,1];ax.axis('off');ax.set_title('Comparação no mesmo evento de calibração',loc='left',fontweight='bold',fontsize=12,pad=12)
    items=[('NSE',before['NSE_raw_clock'],new['NSE_raw_clock'],'.4f'),('KGE',before['KGE_raw_clock'],new['KGE_raw_clock'],'.4f'),
        ('NSE até 15 m',before['NSE_strict_15m_raw_clock'],new['NSE_strict_15m_raw_clock'],'.4f'),
        ('Erro do pico (%)',before['peak_error_vs_available_telemetry_pct'],new['peak_error_vs_available_telemetry_pct'],'+.2f'),
        ('Viés nas horas pareadas (%)',before['bias_pct'],new['bias_pct'],'+.2f'),
        ('Erro relativo na subida (%)',100*before['rise_relative_MAE'],100*new['rise_relative_MAE'],'.2f'),
        ('Erro relativo na recessão (%)',100*before['recession_relative_MAE'],100*new['recession_relative_MAE'],'.2f'),
        ('Pico menos hora SGB (min)',60*before['peak_minus_SGB_reported_time_h'],60*new['peak_minus_SGB_reported_time_h'],'+.0f')]
    previous_values=[previous['NSE_raw_clock'],previous['KGE_raw_clock'],previous['NSE_strict_15m_raw_clock'],previous['peak_error_vs_available_telemetry_pct'],previous['bias_pct'],100*previous['rise_relative_MAE'],100*previous['recession_relative_MAE'],60*previous['peak_minus_SGB_reported_time_h']]
    cells=[[name,format(a,fmt),format(p,fmt),format(b,fmt)] for (name,a,b,fmt),p in zip(items,previous_values)]
    table=ax.table(cellText=cells,colLabels=['Indicador','Base local','Último','Novo HEC'],colWidths=[.52,.16,.16,.16],cellLoc='left',bbox=[0,.2,1,.77]);table.auto_set_font_size(False);table.set_fontsize(9)
    for (r,c),cell in table.get_celld().items():
        cell.set_edgecolor('white');cell.set_facecolor('#e9eef1' if r==0 else ('#f5f7f8' if r%2 else 'white'))
        if r==0:cell.set_text_props(fontweight='bold',color='#263a46')
        elif c==3:cell.set_text_props(fontweight='bold',color='#85294e')
    ax.text(0,.05,'Entrada JJ preservada · relógio bruto · 238 pares horários\nRecalculado em pasta isolada com os DSS existentes.',transform=ax.transAxes,fontsize=10,color='#43515c')
    for ax in list(axes[0])+[axes[1,0]]:ax.spines[['top','right']].set_visible(False);ax.grid(alpha=.14)
    fig.suptitle('Muçum · novembro/2023 · melhora conjunta no HEC-HMS',x=.035,y=.965,ha='left',fontweight='bold',fontsize=20)
    fig.text(.035,.902,'Saídas nativas do HEC-HMS 4.13. Planície local fixa + hipótese de armazenamento lateral limitada pelo terreno regional.',fontsize=11.5,color='#43515c')
    fig.text(.035,.035,'Calibração específica do evento, condicionada à vazão arquivada. ANADEM 30 m, margens aproximadas e perfil de água linear definem um cenário de capacidade.\nTroca com a planície, histerese e remanso ainda não têm validação hidráulica independente. A série horária observada não ganha precisão de 3 min pelo passo do modelo.',fontsize=9,color='#43515c')
    stream=io.BytesIO();fig.savefig(stream,format='png',dpi=170,facecolor='white');plt.close(fig);content=stream.getvalue();Image.open(io.BytesIO(content)).verify();return content
