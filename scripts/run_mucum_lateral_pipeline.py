#!/usr/bin/env python3
"""Build and independently verify the selected capacity-constrained hypothesis."""
import json,subprocess,sys
from pathlib import Path
import build_mucum_floodplain_storage as geo
from search_mucum_lateral_storage import OUT

def main():
    hec=str(Path(sys.argv[1]).resolve());selected=json.loads((OUT/'screening.json').read_text())['selected']
    if not selected.get('regional_capacity_constraint'):raise RuntimeError('Final pipeline requires regional capacity constraint')
    p=json.loads((geo.OUT/'rawclock_selected_channel_parameters.json').read_text());p.update({k:selected['parameters'][k] for k in ['k_g1','baseflow_specific','baseflow_recession']})
    geo.save(OUT/'channel_parameters.json',p)
    commands=[['test_mucum_terrain_storage_native.py',hec,'--rating-archive',str(geo.ROOT.parent/'inputs/mucum_official_rating.csv'),'--raw-clock','--geometry-parameters',str(OUT/'channel_parameters.json'),'--output-tag','native_lateral_base'],
        ['run_mucum_native_lateral_storage.py',hec],['verify_mucum_native_lateral_storage.py',hec],['check_mucum_reach_capacity.py']]
    summary_path=geo.OUT/'native_diagnostic_summary.json'
    prior_summary=summary_path.read_bytes() if summary_path.exists() else None
    try:
        for args in commands:
            print('START',args[0],flush=True);cp=subprocess.run([sys.executable,'-B',str(geo.ROOT/'scripts'/args[0])]+args[1:],cwd=geo.ROOT,capture_output=True,text=True)
            (OUT/(args[0]+'.log')).write_text(cp.stdout+'\n'+cp.stderr)
            if cp.returncode:raise RuntimeError(args[0]+' failed\n'+cp.stdout[-1200:]+cp.stderr[-2000:])
            print('OK',args[0],cp.stdout.strip().splitlines()[-1],flush=True)
    finally:
        # Retain the caller's comparison portfolio, including on a failed run.
        # No untracked historical backup is required for reproduction.
        if prior_summary is not None:summary_path.write_bytes(prior_summary)
    print('LATERAL_CAPACITY_CONSTRAINED_PIPELINE_VERIFIED',flush=True)

if __name__=='__main__':main()
