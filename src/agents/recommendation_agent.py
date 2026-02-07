"""
Recommendation agent: runs counterfactual what-if simulations
and ranks infrastructure recommendations.
"""
from typing import Dict, List
import copy

from ..schemas.models import (
    ForecastPack,
    TransferTopology,
    TransferLink,
    BatteryConfig,
    PolicyConfig,
    KPIs,
    Recommendation,
)
from ..planning.planner_agent import plan as run_planner
from ..sim.simulation_agent import simulate


def _kpi_score(kpis: KPIs, policy: PolicyConfig) -> float:
    """Weighted penalty score (lower is better)."""
    return (
        kpis.total_unserved_mwh * policy.unserved_penalty
        + kpis.total_curtailment_mwh * policy.curtailment_penalty
        + kpis.total_fuel_mwh * policy.fuel_penalty
    )


def _kpi_deltas(baseline: KPIs, modified: KPIs, policy: PolicyConfig) -> Dict[str, float]:
    return {
        "unserved_mwh_delta": round(modified.total_unserved_mwh - baseline.total_unserved_mwh, 2),
        "curtailment_mwh_delta": round(modified.total_curtailment_mwh - baseline.total_curtailment_mwh, 2),
        "fuel_mwh_delta": round(modified.total_fuel_mwh - baseline.total_fuel_mwh, 2),
        "renewable_util_delta": round(modified.renewable_utilization - baseline.renewable_utilization, 4),
        "score_delta": round(
            _kpi_score(modified, policy) - _kpi_score(baseline, policy), 2
        ),
    }


def generate_recommendations(
    forecast: ForecastPack,
    topology: TransferTopology,
    battery_configs: Dict[str, BatteryConfig],
    policy: PolicyConfig,
    baseline_kpis: KPIs,
) -> List[Recommendation]:
    """
    Run counterfactual scenarios and rank by improvement.

    Scenarios:
    1. +50% battery energy per state (with proportional initial SoC)
    2. +50% battery power per state
    3. +50% transfer capacity on all links
    4. +100% transfer capacity on all links (bigger upgrade)
    """
    scenarios = []

    # Scenario 1: more battery energy (+50%, scale initial SoC proportionally)
    for st in sorted(battery_configs.keys()):
        modified_batt = {k: copy.deepcopy(v) for k, v in battery_configs.items()}
        added = modified_batt[st].energy_mwh * 0.5
        # Scale initial SoC proportionally to maintain same fraction
        soc_fraction = modified_batt[st].initial_soc_mwh / modified_batt[st].energy_mwh
        modified_batt[st].energy_mwh *= 1.5
        modified_batt[st].initial_soc_mwh = modified_batt[st].energy_mwh * soc_fraction
        p = run_planner(forecast, topology, modified_batt, policy)
        kpis = simulate(p, forecast, topology, modified_batt)
        scenarios.append((
            "add_storage",
            f"Add {added:.0f} MWh battery storage to {st}",
            {"state": st, "added_mwh": added},
            kpis,
        ))

    # Scenario 2: more battery power (+50%)
    for st in sorted(battery_configs.keys()):
        modified_batt = {k: copy.deepcopy(v) for k, v in battery_configs.items()}
        added = modified_batt[st].power_mw * 0.5
        modified_batt[st].power_mw *= 1.5
        p = run_planner(forecast, topology, modified_batt, policy)
        kpis = simulate(p, forecast, topology, modified_batt)
        scenarios.append((
            "add_battery_power",
            f"Add {added:.0f} MW battery power to {st}",
            {"state": st, "added_mw": added},
            kpis,
        ))

    # Scenario 3: more transfer capacity (+50%)
    modified_topo = TransferTopology(
        links=[
            TransferLink(l.from_state, l.to_state, l.capacity_mw * 1.5)
            for l in topology.links
        ]
    )
    p = run_planner(forecast, modified_topo, battery_configs, policy)
    kpis = simulate(p, forecast, modified_topo, battery_configs)
    scenarios.append((
        "add_transfer",
        "Increase all transfer capacities by 50%",
        {"increase_pct": 50},
        kpis,
    ))

    # Scenario 4: double transfer capacity
    modified_topo2 = TransferTopology(
        links=[
            TransferLink(l.from_state, l.to_state, l.capacity_mw * 2.0)
            for l in topology.links
        ]
    )
    p = run_planner(forecast, modified_topo2, battery_configs, policy)
    kpis = simulate(p, forecast, modified_topo2, battery_configs)
    scenarios.append((
        "add_transfer",
        "Double all transfer capacities",
        {"increase_pct": 100},
        kpis,
    ))

    # Score and rank
    baseline_score = _kpi_score(baseline_kpis, policy)
    ranked = []
    for rec_type, desc, change, kpis in scenarios:
        score = _kpi_score(kpis, policy)
        improvement = baseline_score - score  # positive = better
        ranked.append((improvement, rec_type, desc, change, kpis))

    ranked.sort(key=lambda x: -x[0])  # best improvement first

    recommendations = []
    for i, (improvement, rec_type, desc, change, kpis) in enumerate(ranked):
        recommendations.append(Recommendation(
            rank=i + 1,
            rec_type=rec_type,
            description=desc,
            change=change,
            kpi_deltas=_kpi_deltas(baseline_kpis, kpis, policy),
        ))

    return recommendations
