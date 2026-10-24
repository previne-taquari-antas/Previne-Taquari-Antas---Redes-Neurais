#!/usr/bin/env python3
"""Open copied native projects in isolated folders and independently rescore."""
import copy,json,os,shutil,subprocess,sys
import calibrate_event_members_v2 as v

def main():
    hec=sys.argv[1];s=v.load(v.OUT/'selected_models.json');full=v.load(v.OUT/'full_Q_clock_corrected.json');strict=v.load(v.OUT/'strict_Q_domain.json')
    verified=[]
    for row in s['selected']:
        old=v.ROOT/row['result_file'];dest=v.OUT/'verified_serial'/row['run_id'];proj=dest/'project'
        if proj.exists():shutil.rmtree(proj)
        shutil.copytree(old.parent/'project',proj)
        (proj/'output.dss').unlink(missing_ok=True)
        for p in proj.glob('*.access'):p.unlink()
        script=dest/'isolated_recompute.script';temp=proj/'verified_values.pending';out=proj/'hec_output_values.csv'
        script.write_text('''from hms.model.JythonHms import *
from hec.heclib.dss import HecDss
import csv,os
OpenProject("g040_e1_hindcast",%r)
Compute("Hindcast")
dss=HecDss.open(%r)
fo=open(%r,"wb");w=csv.writer(fo);w.writerow(["element","time_value","q_m3s","pathname"])
for path in dss.getCatalogedPathnames():
    p=path.split("/")
    if p[3]!="FLOW" or p[6]!="RUN:Hindcast":continue
    series=dss.get(path)
    for i in range(series.numberValues):
        q=float(series.values[i])
        if q>-1e20:w.writerow([p[2],int(series.times[i]),q,path])
fo.close();dss.close()
if os.path.exists(%r):os.remove(%r)
os.rename(%r,%r)
print("ISOLATED_NATIVE_COMPUTE_OK")
Exit(0)
'''%(str(proj),str(proj/'output.dss'),str(temp),str(out),str(out),str(temp),str(out)))
        cp=subprocess.run([str(__import__('pathlib').Path(hec).resolve()),'-s',str(script)],cwd=__import__('pathlib').Path(hec).resolve().parent,
            capture_output=True,text=True,timeout=240)
        (dest/'isolated_compute.log').write_text(cp.stdout+'\n'+cp.stderr)
        if cp.returncode or 'ISOLATED_NATIVE_COMPUTE_OK' not in cp.stdout:raise RuntimeError(cp.stdout[-1000:]+cp.stderr[-1000:])
        native=v.load(old);by=v.hms.read_output_csv(out);start=v.hms.utc(native['window']['start_utc']);end=v.hms.utc(native['window']['end_utc'])
        expected=int((end-start).total_seconds()/180)+1
        for c in v.hms.MAIN_CHECKPOINTS:
            r=by.get('J_'+c) or []
            if len(r)!=expected or r[0][0]!=start or r[-1][0]!=end:raise RuntimeError('Isolated native data not complete '+c)
        times=v.hms.hourly_axis(start,end);scores=v.hms.score_outputs(by,full,times,'86472000');ss=v.hms.score_outputs(by,strict,times,'86472000')
        c=row['target_code']
        for k in ['nse','kge','pbias_pct','rmse_m3s']:
            if abs(scores[c][k]-row['scores'][c][k])>1e-8:raise RuntimeError('Isolated project changed score '+c+' '+k)
        updated=copy.deepcopy(row);updated.update(result_file=str((dest/'result.json').relative_to(v.ROOT)),scores=scores,strict_scores=ss,isolated_native_recompute_verified=True)
        native.update(scores=scores,native_output_contract=dict(complete=True,expected_values_per_checkpoint=expected,isolated_project=True),
            original_research_result=str(old.relative_to(v.ROOT)))
        v.save(dest/'result.json',native);verified.append(updated)
        print(json.dumps(dict(city=row['target_name'],values_per_checkpoint=expected,nse=scores[c]['nse'])),flush=True)
    s['selected']=verified;v.save(v.OUT/'selected_models.json',s)

if __name__=='__main__':main()
