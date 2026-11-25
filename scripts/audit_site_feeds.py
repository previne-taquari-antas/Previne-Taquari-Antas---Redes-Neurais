"""Read-only freshness audit. Never refresh a scientific timestamp or estimate missing data."""
import argparse,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
SOURCES={
 'previsao_ao_vivo.json':('consultado_em',1),
 'previsao_ao_vivo_mucum.json':('consultado_em',1),
 'assets/data/research_weather_santa_tereza_latest.json':('generated_at_utc',3),
 'assets/data/research_weather_mucum_latest.json':('generated_at_utc',3),
 'assets/data/research_probability_santa_tereza_latest.json':('generated_at_utc',36),
 'assets/data/research_probability_mucum_latest.json':('generated_at_utc',36),
 'assets/data/research_visual_patterns_santa_tereza_latest.json':('generated_at_utc',8),
 'assets/data/research_visual_patterns_mucum_latest.json':('generated_at_utc',8),
}
def audit(root,now=None):
 now=now or datetime.now(timezone.utc); rows=[]
 for name,(field,limit) in SOURCES.items():
  data={}
  row={'path':name,'timestamp_field':field,'max_age_hours':limit}
  try:
   data=json.loads((Path(root)/name).read_text());stamp=data.get(field);row['timestamp']=stamp
   if not stamp:raise ValueError('missing timestamp')
   date=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
   if date.tzinfo is None:
    if field=='consultado_em':date=date.replace(tzinfo=timezone(timedelta(hours=-3)))
    else:raise ValueError('timestamp has no timezone')
   age=(now-date).total_seconds()/3600;row['age_hours']=round(age,3)
   row['state']='FUTURE_TIMESTAMP' if age < -0.1 else 'STALE' if age>limit else 'CURRENT'
  except (OSError,ValueError,TypeError,AttributeError) as exc:row.update(state='UNAVAILABLE',detail=str(exc))
  if field=='consultado_em' and 'data' in locals():
   stamp=data.get('nivel_rio_agora_em') or data.get('telemetria_ultima_em')
   observation={'path':name+'#observed','timestamp':stamp,'max_age_hours':1}
   try:
    date=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
    if date.tzinfo is None:date=date.replace(tzinfo=timezone(timedelta(hours=-3)))
    age=(now-date).total_seconds()/3600;observation['age_hours']=round(age,3)
    observation['state']='FUTURE_TIMESTAMP' if age < -0.1 else 'STALE' if age>1 else 'CURRENT'
   except (ValueError,TypeError):observation['state']='UNAVAILABLE'
   rows.append(observation)
  rows.append(row)
 return {'checked_at_utc':now.isoformat(),'status':'OK' if all(r['state']=='CURRENT' for r in rows) else 'ATTENTION','sources':rows}
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();report=audit(a.root)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('| Fonte | Estado | Idade (h) |\n|---|---|---|')
 for r in report['sources']:print(f"| {r['path']} | {r['state']} | {r.get('age_hours','—')} |")
 for row in report['sources']:
  if row['state']!='CURRENT':print('::warning::'+row['path']+' '+row['state'])
 return 1 if any(row['path'].startswith('previsao_ao_vivo') and row['state']!='CURRENT' for row in report['sources']) else 0
if __name__=='__main__':raise SystemExit(main())
