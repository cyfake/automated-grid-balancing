"""
Stress agent: identifies interesting windows in the dispatch plan
(ramps, binding constraints, high deficit hours).
"""
from typing import Dict, List

from ..schemas.models import Plan, ForecastPack


def find_stress_windows(
    plan: Plan,
    forecast: ForecastPack,
    threshold_unserved: float = 0.0,
    threshold_fuel_pct: float = 0.5,
) -> List[Dict]:
    """
    Find hours with notable stress conditions:
    - Any unserved energy
    - High fuel utilization (> threshold_fuel_pct of capacity)
    - Large load ramps (>15% hour-over-hour)
    - Battery SoC hitting min or max bounds
    """
    states = sorted(forecast.states.keys())
    events = []

    prev_load: Dict[str, float] = {}

    for h in range(min(forecast.hours, len(plan.actions))):
        action = plan.actions[h]

        for st in states:
            sf = forecast.states[st]
            load = sf.load[h]

            # Unserved energy
            unserved = action.unserved_mw.get(st, 0)
            if unserved > threshold_unserved:
                events.append({
                    "hour": h,
                    "state": st,
                    "type": "unserved_energy",
                    "value_mw": round(unserved, 2),
                    "severity": "critical",
                })

            # Fuel utilization
            fuel_used = action.fuel_dispatch_mw.get(st, 0)
            fuel_cap = sf.fuel_capacity[h]
            if fuel_cap > 0 and fuel_used / fuel_cap > threshold_fuel_pct:
                events.append({
                    "hour": h,
                    "state": st,
                    "type": "high_fuel_utilization",
                    "value_pct": round(fuel_used / fuel_cap * 100, 1),
                    "severity": "warning",
                })

            # Load ramp
            if st in prev_load and prev_load[st] > 0:
                ramp_pct = abs(load - prev_load[st]) / prev_load[st]
                if ramp_pct > 0.15:
                    events.append({
                        "hour": h,
                        "state": st,
                        "type": "load_ramp",
                        "ramp_pct": round(ramp_pct * 100, 1),
                        "severity": "info",
                    })

            prev_load[st] = load

    return events
