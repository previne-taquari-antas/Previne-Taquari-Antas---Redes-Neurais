#!/usr/bin/env python3
"""Select improvements against V2 and independently reexecute portable projects."""
import copy,hashlib,json,sys
from datetime import datetime,timezone
import improve_event_members_v3 as search
import isolate_verify_event_members_v2 as isolate
import audit_hec_incremental_water_budget as audit
v=search.v

def acceptable(r,b):
    c=r['target_code'];m=r['metrics'][c];bm=b['metrics'][c]
    return (m['full_Q_nse']>=bm['full_Q_nse'] and
        abs(m['full_peak_error_vs_recorded_telemetry_pct'])<=2.0 and
        abs(m['stage_crest_timing_h'])<=.75 and abs(m['paired_bias_pct'])<=2.0 and
        m['rising_limb_nmae']<=bm['rising_limb_nmae'] and
        r['refinement_metrics']['full_nmae']<=b['refinement_metrics']['full_nmae'] and
        r['refinement_metrics']['recession_nmae']<=b['refinement_metrics']['recession_nmae'] and
        (c!='86510000' or (m['strict_domain_nse']>=bm['strict_domain_nse'] and
            r['refinement_metrics']['strict_nmae']<=b['refinement_metrics']['strict_nmae'])) and
        (c!='86879300' or r['low_stage_constraint']['pass_with_10pct_model_tolerance']))

def phase_ratios(r,b):
    keys=['full_nmae','rise_nmae','recession_nmae']+(['strict_nmae'] if r['target_code']=='86510000' else [])
    return {k:r['refinement_metrics'][k]/b['refinement_metrics'][k] for k in keys}

def rank(r,b):
    ratios=list(phase_ratios(r,b).values())
    # Prefer a balanced reduction in every phase rather than a large reduction
    # in one phase that conceals smaller gains elsewhere. Squared residuals
    # generate candidates; phase MAE ratios choose the delivered member.
    return max(ratios),sum(ratios)/len(ratios),r['refinement_objective']

def main():
    hec=sys.argv[1];ctx=search.setup();rows=v.load(v.OUT/'refinement_evaluations.json');baseline=[];selected=[]
    for c in search.CITIES:
        rr=[r for r in rows if r['target_code']==c];b=rr[0];baseline.append(b)
        candidates=[r for r in rr if acceptable(r,b)]
        best=min(candidates,key=lambda r:rank(r,b))
        if best['refinement_objective']>=b['refinement_objective']*.99:
            raise RuntimeError('No material joint improvement against V2 yet: '+c)
        # Recheck all metrics from the original screening project before isolation.
        fresh,z=search.evaluate(hec,c,best['parameters'],ctx)
        if abs(fresh['refinement_objective']-best['refinement_objective'])>1e-10:raise RuntimeError('Screening output changed')
        fresh.update(serial_reexecution_verified=False)
        fresh['phase_error_ratios_against_V2']=phase_ratios(fresh,b)
        selected.append(fresh)
    prior=v.load(search.V2/'selection_manifest.json')
    paths=[v.ROOT/'scripts'/name for name in ['improve_event_members_v3.py','run_hec_hms_g040_e1_hindcast.py','g040_overbank_storage.py']]
    paths += [v.BASE/'historical_calibration_forcing'/v.EVENT/f for f in ['hydro.json','rain.json','scenario.json']]
    paths += [v.OUT/'full_Q_clock_corrected.json',v.OUT/'strict_Q_domain.json',*list((v.OUT/'baseline_v2_delivered').glob('*.csv'))]
    s=dict(event_id=v.EVENT,revision='V3',generated_at_utc=datetime.now(timezone.utc).isoformat(),
      selection_unit=prior['selection_unit'],selected=selected,baseline=baseline,
      original_level_crests=ctx[3],low_stage_bound=ctx[4],
      target_evaluations=len(rows),no_independent_forecast_validation_claim=True,
      unique_successful_native_members=len({r['run_id'] for r in rows}),
      fingerprints={str(p.relative_to(v.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
      selection_rule='Full NSE, full/rising/recession relative MAE cannot regress; Muçum strict-domain NSE and MAE cannot regress. Peak within 2%, crest within 0.75h, bias within 2%; retain Estrela level constraint. Among passing candidates minimize the largest phase MAE ratio to V2, then mean phase ratio, then squared-residual objective. This avoids trading a large gain in one phase against small gains elsewhere.',
      residual_weights=dict(Mucum=dict(full=.2,strict=.4,rise=.2,recession=.2),Estrela=dict(full=.35,strict=.05,rise=.3,recession=.3)),
      peak_residual_weight=4,bias_residual_weight=.49,
      caveats=['Retrospective November 2023 calibration, with observed upstream discharge and rain throughout event.',
       'Muçum full-Q fit is conditional on uncertain rating; <=15m diagnostic reported separately.',
       'Conceptual causal lateral storage does not establish measured floodplain hydraulics.',
       'Estrela Q gap is not filled; level constraint supplies only a monotonic upper bound.',
       'Separate city/event parameter sets, no universal model or cross-event success requirement.'])
    v.save(v.OUT/'selected_models.json',s)
    isolate.v.OUT=v.OUT;sys.argv=[sys.argv[0],hec];isolate.main()
    s=v.load(v.OUT/'selected_models.json')
    # Restore component diagnostics and check metrics after isolated native Compute.
    for r in s['selected']:
        rr=next(q for q in selected if q['target_code']==r['target_code'])
        r['serial_reexecution_verified']=True
        if not acceptable(r,next(b for b in baseline if b['target_code']==r['target_code'])):raise RuntimeError('Final native member does not dominate V2')
    v.save(v.OUT/'selected_models.json',s)
    audit.CAL=v.OUT;audit.main()
    compact=copy.deepcopy(s)
    for k in ['selected','baseline']:
      for r in compact[k]:r.pop('scores',None);r.pop('strict_scores',None)
    v.save(v.OUT/'selection_manifest.json',compact)
    print(json.dumps(dict(selected=[dict(city=r['target_name'],metrics=r['metrics'][r['target_code']],segments=r['refinement_metrics']) for r in s['selected']]),ensure_ascii=False))

if __name__=='__main__':main()
