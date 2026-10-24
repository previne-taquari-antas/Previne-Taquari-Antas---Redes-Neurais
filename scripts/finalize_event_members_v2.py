#!/usr/bin/env python3
"""Select the city/event library and repeat each final native run serially."""
import copy,hashlib,json,sys
from datetime import datetime,timezone
import calibrate_event_members_v2 as v

def acceptable(r):
    c=r['target_code'];m=r['metrics'][c]
    return (abs(m['full_peak_error_vs_recorded_telemetry_pct'])<=5
       and abs(m['stage_crest_timing_h'])<=1.5 and abs(m['paired_bias_pct'])<=5
       and m['full_Q_nse']>=.975 and m['strict_domain_nse']>=.965
       and m['rising_limb_nmae']<=.08
       and (c!='86879300' or r['low_stage_constraint']['pass_with_10pct_model_tolerance']))

def rank(r):
    c=r['target_code'];m=r['metrics'][c]
    # The less uncertain <=15 m domain retains an explicit weight for Muçum.
    return m['loss']+(2*(1-m['strict_domain_nse']) if c=='86510000' else 0)

def main():
    hec=sys.argv[1];raw,full,strict,crests,bound=v.prepare();rows={}
    sources=['evaluations.json','supplement_evaluations.json','balanced_refinement.json']
    for name in sources:
        for r in v.load(v.OUT/name):rows[(r['target_code'],r['run_id'])]=r
    rows=list(rows.values());chosen=[];names={'86510000':'Muçum','86879300':'Estrela'}
    for c in names:
        candidates=[r for r in rows if r['target_code']==c and acceptable(r)]
        if not candidates:raise RuntimeError('No complete city/event candidate satisfies the working calibration criteria: '+c)
        prior=min(candidates,key=rank);rp=v.ROOT/prior['result_file']
        # Force a new serial native compute rather than relying on cached scores.
        if rp.exists():rp.replace(rp.with_name('result_before_serial_verification.json'))
        verified=v.execute(hec,prior['parameters'],raw,full,strict,crests,bound)
        verified.update(target_code=c,target_name=names[c],family=prior['family'],event_id=v.EVENT,serial_reexecution_verified=True)
        for k,val in prior['metrics'][c].items():
            if isinstance(val,(int,float)) and abs(val-verified['metrics'][c][k])>1e-8:raise RuntimeError('Serial native reexecution changed '+k)
        if not v.load(rp)['native_output_contract']['complete']:raise RuntimeError('Incomplete native outputs')
        chosen.append(verified)
    baseline=[r for r in rows if r['family']=='V1_SCS_reference']
    files=[v.ROOT/'scripts/run_hec_hms_g040_e1_hindcast.py',v.ROOT/'scripts/g040_overbank_storage.py',
        *[(v.BASE/'historical_calibration_forcing'/v.EVENT/f) for f in ['rain.json','hydro.json','scenario.json']],
        v.OUT/'full_Q_clock_corrected.json',v.OUT/'strict_Q_domain.json']
    summary=dict(event_id=v.EVENT,generated_at_utc=datetime.now(timezone.utc).isoformat(),
        selection_unit='one independent parameter member for each city and historical event; no universal-model requirement',
        target_evaluations=len(rows),unique_successful_native_members=len({r['run_id'] for r in rows}),selected=chosen,baseline=baseline,
        original_level_crests=crests,low_stage_bound=bound,
        working_fit_criteria=dict(peak_error_max_pct=5,stage_crest_error_max_h=1.5,paired_bias_max_pct=5,full_Q_nse_min=.975,
            strict_Q_nse_min=.965,rising_limb_relative_MAE_max=.08,Estrela_low_stage_Q_bound_tolerance_pct=10),
        no_independent_forecast_validation_claim=True,
        fingerprints={str(p.relative_to(v.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    v.save(v.OUT/'selected_models.json',summary)
    print(json.dumps(dict(selected=[dict(city=r['target_name'],run=r['run_id'],parameters=r['parameters'],metrics=r['metrics'][r['target_code']]) for r in chosen]),ensure_ascii=False))

if __name__=='__main__':main()
