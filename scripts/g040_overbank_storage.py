#!/usr/bin/env python3
"""Research-only, mass-conserving, causal overbank storage of an upstream Q series.

This is a conceptual floodplain retention diagnostic and NOT an audited HEC-HMS
hydraulic reservoir. The observed boundary stays intact in the hydro package
and verification; only the effective model input is transformed, with the
transformation and mass balance saved alongside the simulated results.

The storage state starts empty. Use only for event windows starting well before
overbank conditions. Actual calibration requires floodplain elevation/storage
and independent stage/discharge validation.
"""
from __future__ import annotations
import math
from typing import Any

def route_overbank(
    inflow_m3s:list[float],
    *,
    threshold_m3s:float,
    diverted_fraction:float,
    release_tau_h:float,
    timestep_h:float=1.0,
)->tuple[list[float],dict[str,Any]]:
    if not (math.isfinite(threshold_m3s) and threshold_m3s>0):
        raise ValueError("threshold_m3s must be positive finite")
    if not (0<=diverted_fraction<=1 and math.isfinite(diverted_fraction)):
        raise ValueError("diverted_fraction must be within [0,1]")
    if not (math.isfinite(release_tau_h) and release_tau_h>0):
        raise ValueError("release_tau_h must be positive")
    if not (math.isfinite(timestep_h) and timestep_h>0):
        raise ValueError("timestep_h must be positive")
    dt=timestep_h*3600.0
    tau=release_tau_h*3600.0
    decay=math.exp(-dt/tau)
    storage=0.0
    output=[]
    largest_storage=0.0
    total_in=0.0
    total_out=0.0
    diverted_sum=0.0
    for q in inflow_m3s:
        q=float(q)
        if not math.isfinite(q) or q<0:
            raise ValueError("all input discharge must be finite nonnegative")
        diverted=diverted_fraction*max(q-threshold_m3s,0.0)
        # Linear reservoir receiving constant inflow for the interval.
        storage_end=storage*decay+diverted*tau*(1-decay)
        release_volume=storage+diverted*dt-storage_end
        qout=q-diverted+release_volume/dt
        if qout<0 and qout>-1e-8:
            qout=0.0
        if qout<0:
            raise ArithmeticError("negative routed discharge")
        output.append(qout)
        total_in+=q*dt
        total_out+=qout*dt
        diverted_sum+=diverted*dt
        storage=storage_end
        largest_storage=max(largest_storage,storage)
    balance_error=total_in-total_out-storage
    scale=max(total_in,1.0)
    if abs(balance_error)>scale*1e-9:
        raise ArithmeticError(f"overbank mass balance failure {balance_error} m3")
    return output,{
        "method":"conceptual_off_channel_linear_reservoir_causal_exact_interval_solution",
        "research_only":True,
        "not_a_measured_reservoir":True,
        "threshold_m3s":threshold_m3s,
        "diverted_fraction":diverted_fraction,
        "release_tau_h":release_tau_h,
        "input_total_volume_m3":total_in,
        "output_total_volume_m3":total_out,
        "remaining_storage_m3":storage,
        "maximum_storage_m3":largest_storage,
        "diverted_total_volume_m3":diverted_sum,
        "mass_balance_error_m3":balance_error,
        "initial_storage_m3":0.0,
        "observation_policy":"Original upstream observations remain untouched. Transformation is an unvalidated physical hypothesis."
    }
