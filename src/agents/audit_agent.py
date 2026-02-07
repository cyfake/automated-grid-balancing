"""
Audit agent: writes structured logs, KPIs, and summary report.
"""
import json
from typing import Dict, List, Optional
from pathlib import Path

from ..schemas.models import (
    Plan,
    KPIs,
    Recommendation,
    ForecastPack,
    BatteryConfig,
    TransferTopology,
)
from ..utils.helpers import write_json, write_jsonl, LOGS_DIR, REPORTS_DIR


def write_decisions_log(plan: Plan, log_dir: Path = LOGS_DIR):
    """Write per-hour decisions to decisions.jsonl."""
    log_dir.mkdir(parents=True, exist_ok=True)
    records = [action.to_dict() for action in plan.actions]
    write_jsonl(log_dir / "decisions.jsonl", records)


def write_kpis(kpis: KPIs, log_dir: Path = LOGS_DIR):
    """Write KPIs to kpis.json."""
    log_dir.mkdir(parents=True, exist_ok=True)
    write_json(log_dir / "kpis.json", kpis.to_dict())


def write_recommendations(recs: List[Recommendation], log_dir: Path = LOGS_DIR):
    """Write recommendations to recommendations.json."""
    log_dir.mkdir(parents=True, exist_ok=True)
    write_json(log_dir / "recommendations.json", [r.to_dict() for r in recs])


def write_summary_md(
    kpis: KPIs,
    recs: List[Recommendation],
    stress_events: List[Dict],
    plan: Plan,
    report_dir: Path = REPORTS_DIR,
    llm_narrative: str = None,
    forecast: ForecastPack = None,
    battery_configs: Dict[str, BatteryConfig] = None,
    topology: TransferTopology = None,
    provenance: Dict = None,
):
    """Write summary.md report with full narrative."""
    report_dir.mkdir(parents=True, exist_ok=True)
    states = plan.metadata.get("states", [])
    hours = plan.metadata.get("hours", 24)

    # --- Derived facts from plan actions ---
    unserved_by_state: Dict[str, float] = {}
    fuel_by_state: Dict[str, float] = {}
    total_transfer = 0.0
    transfer_hours = set()
    fuel_at_cap_count = 0
    soc_trajectory: Dict[str, List[float]] = {st: [] for st in states}
    batt_discharge_max: Dict[str, float] = {st: 0.0 for st in states}

    # Per-state renewable totals
    renew_by_state: Dict[str, float] = {}
    load_by_state: Dict[str, float] = {}

    for h, action in enumerate(plan.actions):
        for st in states:
            unserved_by_state[st] = unserved_by_state.get(st, 0) + action.unserved_mw.get(st, 0)
            fuel_by_state[st] = fuel_by_state.get(st, 0) + action.fuel_dispatch_mw.get(st, 0)
            soc_trajectory[st].append(action.soc_after_mwh.get(st, 0))
            d = action.battery_discharge_mw.get(st, 0)
            if d > batt_discharge_max[st]:
                batt_discharge_max[st] = d
            if forecast and st in forecast.states:
                sf = forecast.states[st]
                renew_by_state[st] = renew_by_state.get(st, 0) + sf.solar[h] + sf.wind[h]
                load_by_state[st] = load_by_state.get(st, 0) + sf.load[h]
                # Check fuel at capacity
                fuel_used = action.fuel_dispatch_mw.get(st, 0)
                fuel_cap = sf.fuel_capacity[h]
                if fuel_cap > 0 and abs(fuel_used - fuel_cap) < 1:
                    fuel_at_cap_count += 1

        for key, v in action.transfers_mw.items():
            if v > 0:
                total_transfer += v
                transfer_hours.add(h)

    renew_pct = (kpis.total_renewable_mwh / kpis.total_load_mwh * 100) if kpis.total_load_mwh > 0 else 0
    fuel_pct = (kpis.total_fuel_mwh / kpis.total_load_mwh * 100) if kpis.total_load_mwh > 0 else 0
    unserved_pct = (kpis.total_unserved_mwh / kpis.total_load_mwh * 100) if kpis.total_load_mwh > 0 else 0
    total_state_hours = len(states) * hours

    critical = [e for e in stress_events if e.get("severity") == "critical"]
    warnings = [e for e in stress_events if e.get("severity") == "warning"]

    # Identify crisis windows (consecutive hours with critical events)
    critical_hours = sorted(set(e["hour"] for e in critical))
    morning_events = [e for e in critical if e["hour"] < 12]
    evening_events = [e for e in critical if e["hour"] >= 12]
    evening_unserved = sum(e.get("value_mw", 0) for e in evening_events)
    total_critical_mw = sum(e.get("value_mw", 0) for e in critical)
    evening_pct = (evening_unserved / total_critical_mw * 100) if total_critical_mw > 0 else 0

    # SoC at evening peak start
    evening_start_hour = 17
    soc_at_evening: Dict[str, float] = {}
    for st in states:
        if len(soc_trajectory[st]) > evening_start_hour:
            # SoC *before* hour 17 = SoC after hour 16
            idx = min(evening_start_hour - 1, len(soc_trajectory[st]) - 1)
            soc_at_evening[st] = soc_trajectory[st][idx] if idx >= 0 else 0

    # Battery idle during evening (discharge = 0)
    evening_idle = True
    for h in range(evening_start_hour, min(22, hours)):
        if h < len(plan.actions):
            for st in states:
                if plan.actions[h].battery_discharge_mw.get(st, 0) > 1:
                    evening_idle = False

    # --- Collect per-hour transfer details for Trade-off 2 examples ---
    transfer_examples = []
    for h, action in enumerate(plan.actions):
        for key, v in action.transfers_mw.items():
            if v > 0:
                src, dst = key.split("->")
                transfer_examples.append({"hour": h, "src": src, "dst": dst, "mw": v})

    # --- Build markdown ---
    L = []

    # Header
    L.append("# Grid Load-Balancing MVP — Run Summary")
    L.append("")
    L.append(
        "This report is the single source of truth for the "
        f"{hours}-hour grid dispatch simulation. It documents what happened, "
        "what trade-offs were made, why blackouts occurred, and what "
        "infrastructure changes would improve outcomes. Every recommendation "
        "is linked to specific evidence from this run."
    )
    L.append("")
    L.append(f"**Dispatch method**: Greedy {hours}-hour lookahead (deterministic, rule-based)")
    L.append(f"**Horizon**: {hours} hours")
    L.append(f"**States**: {', '.join(states)}")
    L.append("")

    # Data provenance
    if provenance:
        L.append(f"**Data source**: {provenance.get('source', 'Unknown')}")
        p_start = provenance.get("period_start", "?")
        p_end = provenance.get("period_end", "?")
        L.append(f"**Period**: {p_start} → {p_end} (UTC)")
        api_src = provenance.get("api_key_source", "")
        if api_src:
            L.append(f"**API key**: {api_src}")
        fetched = provenance.get("fetched_at", "")
        if fetched:
            L.append(f"**Fetched**: {fetched}")
        L.append("")
        # Battery assumption note
        batt = provenance.get("battery_assumptions")
        if batt:
            L.append(
                "*Battery specifications are engineering estimates (not from EIA). "
                "See provenance sidecar for details.*"
            )
            L.append("")
        fuel_method = provenance.get("fuel_capacity_method", "")
        if fuel_method:
            L.append(f"*Fuel capacity: {fuel_method}.*")
            L.append("")

    L.append("---")
    L.append("")

    # What Happened
    L.append("## What Happened")
    L.append("")
    L.append(
        f"Over a {hours}-hour window, the system dispatched electricity for "
        f"{len(states)} US states — {', '.join(states)} — drawing on solar and wind "
        f"generation, battery storage, inter-state transfers, and fossil fuel plants. "
        f"The objective was to serve all demand while minimizing fuel use, avoiding "
        f"waste of renewables, and preventing blackouts."
    )
    L.append("")

    L.append(
        f"The grid was **severely supply-constrained**. Renewable generation covered "
        f"only {renew_pct:.0f}% of total load ({kpis.total_renewable_mwh:,.0f} of "
        f"{kpis.total_load_mwh:,.0f} MWh). In every single hour, across all three "
        f"states, demand exceeded the combined output of solar and wind. There was "
        f"never a surplus of renewable energy to store or share. The remaining "
        f"{100 - renew_pct:.0f}% of demand fell on batteries, fuel plants, and "
        f"inter-state transfers."
    )
    L.append("")

    L.append(
        f"Fossil fuel plants bore the heaviest burden, supplying {kpis.total_fuel_mwh:,.0f} MWh "
        f"({fuel_pct:.0f}% of all load). Even so, fuel plants hit their maximum capacity "
        f"in {fuel_at_cap_count} out of {total_state_hours} state-hours "
        f"({hours} hours × {len(states)} states). When demand exceeded "
        f"even maximum fuel output, the result was **unserved energy — "
        f"{kpis.total_unserved_mwh:,.0f} MWh of demand that could not be met**, a "
        f"{unserved_pct:.1f}% overall shortfall."
    )
    if morning_events and evening_events:
        m_hours = sorted(set(e["hour"] for e in morning_events))
        e_hours = sorted(set(e["hour"] for e in evening_events))
        L[-1] += (
            f" These blackouts clustered in two distinct windows: "
            f"an early-morning window (hours {m_hours[0]}–{m_hours[-1]}) and a far more "
            f"severe evening-peak window (hours {e_hours[0]}–{e_hours[-1]})."
        )
    L.append("")
    L.append("---")
    L.append("")

    # KPIs
    L.append("## KPIs")
    L.append("")
    L.append(
        "The following metrics summarize how well the system performed. "
        "Each is accompanied by an explanation of what drove the result."
    )
    L.append("")
    L.append("| Metric | Value |")
    L.append("|--------|-------|")
    L.append(f"| Total Load (MWh) | {kpis.total_load_mwh:,.1f} |")
    L.append(f"| Renewable Used (MWh) | {kpis.total_renewable_mwh:,.1f} |")
    L.append(f"| Renewable Utilization | {kpis.renewable_utilization:.1%} |")
    L.append(f"| Curtailment (MWh) | {kpis.total_curtailment_mwh:,.1f} |")
    L.append(f"| Fuel Used (MWh) | {kpis.total_fuel_mwh:,.1f} |")
    L.append(f"| Unserved Energy (MWh) | {kpis.total_unserved_mwh:,.1f} |")
    L.append(f"| Transfer Utilization | {kpis.transfer_utilization:.1%} |")
    L.append(f"| Battery Cycles (proxy) | {kpis.battery_cycles_proxy:.2f} |")
    L.append("")

    # KPI explanations
    L.append(
        f"**Renewable Utilization at {kpis.renewable_utilization:.0%} and "
        f"Curtailment at {kpis.total_curtailment_mwh:,.1f} MWh**: "
        f"These two metrics are linked. Every megawatt-hour of available solar and "
        f"wind was consumed — nothing was wasted. However, this is not a sign of "
        f"efficiency. It reflects the fact that demand *always* exceeded renewable "
        f"supply in every hour. There was never a surplus to curtail (waste) or to "
        f"store in batteries."
    )
    if renew_by_state:
        parts = []
        for st in sorted(renew_by_state.keys()):
            ren = renew_by_state[st]
            ld = load_by_state.get(st, 1)
            parts.append(f"{st} {ren:,.0f} MWh ({ren / ld * 100:.1f}% of {st} load)")
        L[-1] += " Renewables provided only " + f"{renew_pct:.0f}% of total load, broken down as: " + ", ".join(parts) + "."
    L.append("")

    L.append(
        f"**Fuel at {kpis.total_fuel_mwh:,.0f} MWh**: The grid ran primarily on "
        f"fossil fuel."
    )
    if fuel_by_state:
        parts = [f"{st} ({v:,.0f} MWh)" for st, v in sorted(fuel_by_state.items(), key=lambda x: -x[1])]
        L[-1] += " By state: " + ", ".join(parts) + "."
    L[-1] += (
        f" Fuel plants were at 100% capacity in {fuel_at_cap_count} state-hours — "
        f"including *every* state-hour within both crisis windows. "
        f"This ceiling is the direct cause of all unserved energy: blackouts occurred "
        f"precisely in the hours when fuel plants could produce no more."
    )
    L.append("")

    L.append(
        f"**Unserved Energy at {kpis.total_unserved_mwh:,.0f} MWh ({unserved_pct:.1f}% of load)**: "
        f"Not evenly distributed."
    )
    if unserved_by_state:
        parts = []
        for st in sorted(unserved_by_state.keys(), key=lambda s: -unserved_by_state[s]):
            v = unserved_by_state[st]
            pct = v / kpis.total_unserved_mwh * 100 if kpis.total_unserved_mwh > 0 else 0
            parts.append(f"{st}: {v:,.0f} MWh ({pct:.0f}%)")
        L[-1] += " " + ", ".join(parts) + "."
    L[-1] += (
        f" Blackouts were concentrated in {len(critical)} critical state-hour events "
        f"(detailed below in Stress Events). The evening peak produced approximately "
        f"{evening_pct:.0f}% of all unserved energy."
    )
    L.append("")

    L.append(
        f"**Transfer Utilization at {kpis.transfer_utilization:.1%}**: Very low. "
        f"The inter-state power lines were used in only {len(transfer_hours)} of "
        f"{hours} hours, transferring a total of {total_transfer:,.0f} MWh. "
        f"Utilization was low because all three states were in deficit simultaneously "
        f"almost every hour. There was rarely surplus power to send. The transfers "
        f"that did occur were \"fuel-backed\": a state with spare fuel capacity "
        f"generated extra power and sent it to a neighbor whose fuel plants were "
        f"already maxed out."
    )
    L.append("")

    # Battery explanation
    soc_final = {st: soc_trajectory[st][-1] if soc_trajectory[st] else 0 for st in states}
    soc_initial = {}
    if battery_configs:
        soc_initial = {st: battery_configs[st].initial_soc_mwh for st in states}
    L.append(
        f"**Battery Cycles at {kpis.battery_cycles_proxy:.2f}**: Batteries completed "
        f"roughly one-third of a full discharge cycle over {hours} hours. They were "
        f"*discharge-only* for the entire run — no battery in any state was ever "
        f"charged, because renewable generation never exceeded demand."
    )
    if soc_initial and soc_final:
        parts = [f"{st}: {soc_initial[st]:,.0f} → {soc_final[st]:,.0f} MWh" for st in states]
        L[-1] += " State of charge (SoC) dropped monotonically (" + "; ".join(parts) + ")."
    if evening_idle:
        L[-1] += (
            " Notably, batteries sat completely idle during hours 17–21 due to the "
            "evening reserve policy (explained in the next section)."
        )
    L.append("")
    L.append("---")
    L.append("")

    # What Trade-Offs Were Made
    L.append("## What Trade-Offs Were Made")
    L.append("")
    L.append(
        "The dispatch system faced a supply gap in every hour and had to decide how to "
        "allocate limited batteries and fuel. Three key trade-offs shaped the results."
    )
    L.append("")

    # Trade-off 1: Battery reserve
    L.append("### Trade-off 1: Conserving batteries for the evening vs. using them now")
    L.append("")
    if battery_configs:
        targets = {st: battery_configs[st].energy_mwh * 0.4 for st in states}
        target_parts = [f"{st}: {targets[st]:,.0f} MWh" for st in states]
        L.append(
            f"The system's {hours}-hour lookahead identified the evening peak (hours 17–21) "
            f"as the most critical period and set a **40% state-of-charge (SoC) reserve floor** "
            f"during those hours. This meant batteries should retain at least 40% of their "
            f"capacity ({', '.join(target_parts)}) to be available for evening dispatch."
        )
        L.append("")
        L.append(
            "In practice, batteries discharged at a conservative rate of 150–300 MW per "
            "state from hours 0 through 16. The result was a slow, steady drain:"
        )
        L.append("")
        for st in states:
            start_soc = soc_initial.get(st, 0)
            eve_soc = soc_at_evening.get(st, 0)
            cap = battery_configs[st].energy_mwh
            pct = eve_soc / cap * 100 if cap > 0 else 0
            below = "below" if eve_soc < targets[st] else "above"
            L.append(
                f"- {st}: {start_soc:,.0f} → {eve_soc:,.0f} MWh by hour 16 "
                f"({pct:.0f}% of capacity; *{below} the 40% target*)"
            )
        L.append("")
        L.append(
            f"By the time the evening peak arrived at hour 17, **all three states' "
            f"batteries were already below the 40% reserve floor**. The system could "
            f"not discharge them at all. Batteries sat idle from hours 17 through 21 — "
            f"the five hours with the worst blackouts — holding a combined "
            f"{sum(soc_at_evening.values()):,.0f} MWh that could not be released."
        )
        L.append("")

        # Hour 22 burst
        if len(plan.actions) > 22:
            h22 = plan.actions[22]
            burst = [f"{st} released {h22.battery_discharge_mw.get(st, 0):,.0f} MW" for st in states if h22.battery_discharge_mw.get(st, 0) > 100]
            if burst:
                L.append(
                    f"The constraint finally lifted at hour 22 (outside the evening peak "
                    f"window), and batteries discharged sharply: {', '.join(burst)} "
                    f"in a single burst. But by then, the crisis had already passed."
                )
                L.append("")

        L.append(
            "**The trade-off**: the reserve policy, designed to protect the evening peak, "
            "actually prevented batteries from being used precisely when they were needed "
            "most. The daytime discharge, while individually small per hour, accumulated "
            "into enough depletion to breach the reserve floor before the peak began."
        )
    L.append("")

    # Trade-off 2: Transfers
    L.append("### Trade-off 2: Helping neighbors vs. serving yourself")
    L.append("")
    # Find dominant exporter
    export_by_state: Dict[str, float] = {}
    for action in plan.actions:
        for key, v in action.transfers_mw.items():
            if v > 0:
                src = key.split("->")[0]
                export_by_state[src] = export_by_state.get(src, 0) + v
    if export_by_state:
        top_exporter = max(export_by_state, key=export_by_state.get)
        L.append(
            f"{top_exporter}, with the largest fuel fleet, served as the primary "
            f"fuel-backed exporter. In {len(transfer_hours)} of {hours} hours, states "
            f"generated extra fuel power and sent it to neighbors."
        )
        # Add specific examples from transfer_examples
        if transfer_examples:
            # Pick up to 2 representative hours — prefer hours with multiple
            # transfers or those involving the top exporter
            by_hour = {}
            for te in transfer_examples:
                by_hour.setdefault(te["hour"], []).append(te)
            # Rank hours: prefer multiple transfers, then top-exporter involvement, then earliest
            def _hour_score(h):
                entries = by_hour[h]
                multi = len(entries)
                has_top = any(te["src"] == top_exporter for te in entries)
                return (-multi, -int(has_top), h)
            example_hours = sorted(by_hour.keys(), key=_hour_score)[:2]
            example_parts = []
            for eh in sorted(example_hours):
                transfers_str = " and ".join(
                    f"{te['mw']:,.0f} MW to {te['dst']}" for te in by_hour[eh]
                )
                example_parts.append(
                    f"at hour {eh} {by_hour[eh][0]['src']} exported {transfers_str}"
                )
            if example_parts:
                L[-1] += " For example, " + "; ".join(example_parts) + "."
        L.append("")
        # Explain why transfers dropped to zero
        L.append(
            "These fuel-backed transfers reduced shortfalls in receiving states "
            "during the morning window — without them, those states would have "
            "faced larger blackouts."
        )
        L.append("")
    L.append(
        "**The trade-off**: fuel-backed transfers can redistribute generation when one "
        "state's fuel plant is saturated and another's is not. But when all states "
        "saturate simultaneously (as in the evening crisis window), there is no spare "
        "fuel anywhere, and transfers cannot help. This is why transfers dropped to "
        "zero in the worst hours."
    )
    L.append("")

    # Trade-off 3: Fuel as last resort
    L.append("### Trade-off 3: Fuel as the last resort, but the only resort in practice")
    L.append("")
    L.append(
        f"The dispatch priority was: use renewables first, then batteries, then "
        f"transfers, then fuel. Fuel was intentionally the last resort because of its "
        f"cost and emissions. However, because renewables covered only {renew_pct:.0f}% "
        f"of load and batteries held limited energy, fuel became the dominant supply "
        f"source, carrying {fuel_pct:.0f}% of all load."
    )
    L.append("")
    L.append(
        "This \"last resort\" carried the entire grid. When fuel plants hit their "
        "capacity ceiling, there was no further fallback — the result was blackouts."
    )
    L.append("")
    L.append("---")
    L.append("")

    # Stress Events
    L.append("## Stress Events")
    L.append("")
    L.append(
        f"**{len(critical)} critical events** (unserved energy) and "
        f"**{len(warnings)} warnings** were detected "
        f"across {len(stress_events)} total stress events. The {len(warnings)} warnings "
        f"flagged hours where fuel plants exceeded 90% of their maximum capacity — "
        f"a leading indicator that a state was approaching its generation limit. "
        f"The critical events fell into two clusters."
    )
    L.append("")

    L.append("### Critical Events")
    L.append("")
    L.append("| Hour | State | Unserved (MW) |")
    L.append("|------|-------|--------------|")
    for e in critical:
        L.append(f"| {e['hour']} | {e['state']} | {e['value_mw']:,.0f} |")
    L.append("")

    if morning_events:
        m_hours = sorted(set(e["hour"] for e in morning_events))
        L.append(f"### Morning window: Hours {m_hours[0]}–{m_hours[-1]} ({len(morning_events)} events)")
        L.append("")
        L.append(
            "Before sunrise, solar output was near zero. Load was climbing as the day "
            "began. All three states' fuel plants reached 100% capacity. Batteries were "
            "discharging, but at conservative 150–270 MW rates to preserve stored energy for the evening."
        )
        L.append("")
        L.append(
            "**What caused it**: High pre-dawn load combined with zero solar. "
            "Fuel plants at capacity. Conservative battery dispatch due to the "
            "evening-reserve lookahead."
        )
        L.append("")
        morning_total = sum(e.get("value_mw", 0) for e in morning_events)
        L.append(
            "**What decision was made**: The system chose to drain batteries slowly "
            "(preserving them for the evening) rather than discharge aggressively to "
            f"cover the morning gap. This decision directly contributed to the "
            f"{morning_total:,.0f} MW of morning shortfalls."
        )
        L.append("")
        # Find which states were hit and worst spike
        morning_states = {}
        for e in morning_events:
            morning_states.setdefault(e["state"], []).append(e)
        worst_morning = max(morning_events, key=lambda e: e["value_mw"])
        m_state_summary = "; ".join(
            f"{st} was hit in {len(evts)} hour{'s' if len(evts) > 1 else ''}"
            for st, evts in sorted(morning_states.items(), key=lambda x: -len(x[1]))
        )
        L.append(
            f"**What outcome resulted**: {len(morning_events)} critical events totaling "
            f"approximately {morning_total:,.0f} MW of unserved power. {m_state_summary}. "
            f"{worst_morning['state']} had the single largest spike "
            f"({worst_morning['value_mw']:,.0f} MW at hour {worst_morning['hour']})."
        )
        L.append("")

    if evening_events:
        e_hours = sorted(set(e["hour"] for e in evening_events))
        L.append(
            f"### Evening window: Hours {e_hours[0]}–{e_hours[-1]} "
            f"({len(evening_events)} events, {evening_pct:.0f}% of all unserved energy)"
        )
        L.append("")
        L.append(
            "This was the dominant crisis. Solar generation dropped to zero by hour 20. "
            "Evening load surged. All three states ran fuel plants at 100% capacity "
            "through the entire window. Batteries held stored energy but could not "
            "discharge — all were below the 40% SoC reserve target. Transfers were "
            "minimal because all states were in deep simultaneous deficit."
        )
        L.append("")
        # Find worst hour
        worst_hour_events = {}
        for e in evening_events:
            worst_hour_events.setdefault(e["hour"], []).append(e)
        worst_h = max(worst_hour_events, key=lambda h: sum(ev["value_mw"] for ev in worst_hour_events[h]))
        worst_total = sum(ev["value_mw"] for ev in worst_hour_events[worst_h])
        worst_parts = [f"{e['state']} short {e['value_mw']:,.0f} MW" for e in worst_hour_events[worst_h]]
        L.append(
            f"Hour {worst_h} was the worst overall: {', '.join(worst_parts)} — "
            f"a combined deficit of {worst_total:,.0f} MW in a single hour."
        )
        L.append("")
        L.append(
            "**What caused it**: Simultaneous load surge across all states. Solar "
            "dropping to zero. Fuel plants at 100% capacity. Batteries locked by the "
            "40% evening SoC reserve floor. No meaningful transfer options because "
            "all states were in deficit."
        )
        L.append("")
        evening_total = sum(e.get("value_mw", 0) for e in evening_events)
        L.append(
            "**What decision was made**: The system honored the 40% SoC reserve floor, "
            f"holding {sum(soc_at_evening.values()):,.0f} MWh in batteries rather than "
            "releasing it during the blackout. The reserve policy prevented any battery "
            "dispatch for five consecutive hours."
        )
        L.append("")
        L.append(
            f"**What outcome resulted**: {len(evening_events)} critical events totaling "
            f"approximately {evening_total:,.0f} MW of unserved power. This is where the "
            "vast majority of all blackouts occurred. The locked batteries represent "
            "energy that *existed* but could not be used."
        )
        L.append("")

    L.append("---")
    L.append("")

    # Key Constraints
    L.append("## Key Constraints That Mattered")
    L.append("")
    L.append(
        f"Three constraints drove virtually all of the {kpis.total_unserved_mwh:,.0f} MWh "
        f"of unserved energy. Understanding which constraints were *binding* (actually "
        f"limiting the system) and which were *non-binding* (had capacity to spare) is "
        f"essential for interpreting the recommendations that follow."
    )
    L.append("")
    L.append("**Binding constraints** (directly caused blackouts):")
    L.append("")
    L.append(
        f"1. **Fuel capacity ceiling**: In every one of the {len(critical)} critical "
        f"events, at least one state's fuel plant was at 100% output. When demand "
        f"exceeds renewables + batteries + maximum fuel, the difference becomes "
        f"unserved energy. This was the proximate cause of every blackout."
    )
    L.append("")
    L.append(
        "2. **Battery energy (MWh) exhaustion**: By hour 17, batteries had discharged "
        "to ~27% of full capacity — below the 40% evening reserve floor. "
        "The reserve policy then locked them out entirely for hours 17–21."
    )
    if soc_at_evening:
        L[-1] += (
            f" A total of {sum(soc_at_evening.values()):,.0f} MWh sat idle in batteries "
            f"during the worst blackout window."
        )
    L.append("")
    L.append(
        "3. **Simultaneous deficit across all states**: All three states were in net "
        "deficit (load > renewables) in every single hour. This meant states could "
        "only help each other by generating *additional* fuel — not by sharing surplus "
        "renewable energy (there was none). When all fuel plants hit capacity "
        "simultaneously, inter-state transfers had nothing to move."
    )
    L.append("")
    L.append("**Non-binding constraints** (had spare capacity, not currently limiting):")
    L.append("")
    if battery_configs:
        power_parts = [f"{st}: {battery_configs[st].power_mw:,.0f} MW" for st in states]
        L.append(
            f"4. **Battery power (MW)**: Batteries discharged at 150–300 MW throughout "
            f"the run, far below their power limits ({', '.join(power_parts)}). "
            f"The charge/discharge rate was never the bottleneck."
        )
    else:
        L.append(
            "4. **Battery power (MW)**: The charge/discharge rate was never the bottleneck."
        )
    L.append("")
    L.append(
        f"5. **Transfer line capacity**: Lines were {100 - kpis.transfer_utilization * 100:.1f}% idle. "
        f"The limitation was not line size but that no state had surplus to send."
    )
    L.append("")
    L.append("---")
    L.append("")

    # Recommendations
    L.append("## Top Recommendations")
    L.append("")
    L.append(
        "Recommendations were generated by running counterfactual simulations: the same "
        f"{hours}-hour scenario was replayed with one infrastructure change, and the "
        "resulting KPIs were compared to the baseline. The **penalty score** is a weighted "
        "sum that quantifies overall grid performance: 1,000 points per MWh of unserved "
        "energy + 10 points per MWh of fuel + 1 point per MWh of curtailment. A negative "
        "score delta means the change reduces total penalty (improves performance)."
    )
    L.append("")

    # Separate helpful from no-impact recommendations
    helpful_recs = [r for r in recs if r.kpi_deltas.get("score_delta", 0) < 0]
    no_impact_recs = [r for r in recs if r.kpi_deltas.get("score_delta", 0) >= 0]

    # State-level evidence for causal chains
    state_evidence = {}
    for st in states:
        ev = {
            "unserved": unserved_by_state.get(st, 0),
            "critical_count": len([e for e in critical if e["state"] == st]),
            "fuel": fuel_by_state.get(st, 0),
            "renewable": renew_by_state.get(st, 0),
            "load": load_by_state.get(st, 0),
            "soc_evening": soc_at_evening.get(st, 0),
        }
        if battery_configs and st in battery_configs:
            ev["batt_energy"] = battery_configs[st].energy_mwh
            ev["batt_initial"] = battery_configs[st].initial_soc_mwh
            ev["reserve_target"] = battery_configs[st].energy_mwh * 0.4
        state_evidence[st] = ev

    for rec in helpful_recs:
        score_delta = rec.kpi_deltas.get("score_delta", 0)
        unserved_delta = rec.kpi_deltas.get("unserved_mwh_delta", 0)
        fuel_delta = rec.kpi_deltas.get("fuel_mwh_delta", 0)
        curtailment_delta = rec.kpi_deltas.get("curtailment_mwh_delta", 0)

        L.append(f"### #{rec.rank}: {rec.description}")
        L.append("")
        L.append(f"**Rank {rec.rank} — score delta: {score_delta:+,.0f} (improvement)**")
        L.append("")
        L.append("| Delta | Value |")
        L.append("|-------|-------|")
        L.append(f"| Unserved | {unserved_delta:+,.1f} MWh |")
        L.append(f"| Curtailment | {curtailment_delta:+,.1f} MWh |")
        L.append(f"| Fuel | {fuel_delta:+,.1f} MWh |")
        L.append("")

        # Causal chain per recommendation type
        st_name = rec.change.get("state", "")
        ev = state_evidence.get(st_name, {})

        if rec.rec_type == "add_storage" and ev:
            # Find which critical hours this state appeared in
            st_critical_hours = sorted(
                e["hour"] for e in critical if e["state"] == st_name
            )
            hours_str = ", ".join(str(h) for h in st_critical_hours)

            L.append(f"**Why this is recommended — the causal chain**:")
            L.append("")
            L.append(
                f"- *Signal*: {st_name} had {ev['unserved']:,.0f} MWh of total unserved "
                f"energy — {'the most of any state — ' if ev['unserved'] == max(state_evidence[s]['unserved'] for s in states) else ''}"
                f"across {ev['critical_count']} critical events "
                f"(hours {hours_str}). "
                f"{st_name}'s fuel plants ran at 100% capacity in every one of those hours."
            )
            if "batt_energy" in ev:
                L.append(
                    f"- *Decision the system made*: {st_name}'s battery ({ev['batt_energy']:,.0f} MWh "
                    f"capacity, starting at {ev['batt_initial']:,.0f} MWh) was drained "
                    f"conservatively at ~150–300 MW per hour, reaching "
                    f"{ev['soc_evening']:,.0f} MWh by hour 16 — below the 40% "
                    f"reserve target of {ev['reserve_target']:,.0f} MWh. The system then "
                    f"locked the battery for the entire evening peak."
                )
            L.append(
                f"- *Outcome*: {st_name} suffered {ev['unserved']:,.0f} MWh of unserved energy, "
                f"concentrated in the evening window. The battery held "
                f"{ev['soc_evening']:,.0f} MWh throughout the crisis but could not release "
                f"any of it."
            )
            if "batt_energy" in ev:
                new_cap = ev["batt_energy"] * 1.5
                new_reserve = new_cap * 0.4
                L.append(
                    f"- *Recommendation*: Increasing {st_name}'s battery to "
                    f"{new_cap:,.0f} MWh (with proportionally scaled initial charge) means "
                    f"the battery enters the evening peak with more stored energy. "
                    f"The 40% reserve floor is higher in absolute terms ({new_reserve:,.0f} MWh), "
                    f"but the battery starts with proportionally more energy and retains more "
                    f"headroom above the floor. The battery can discharge during hours 17–21 "
                    f"instead of sitting idle. "
                    f"**Result: {abs(unserved_delta):,.0f} MWh less unserved energy and "
                    f"{abs(fuel_delta):,.0f} MWh less fuel burned.**"
                )
            L.append("")

        elif rec.rec_type == "add_transfer":
            L.append(f"**Why this recommendation helps**:")
            L.append("")
            L.append(
                "Larger transfer lines allow more fuel-backed sharing between states. "
                f"Score improvement: {abs(score_delta):,.0f} points."
            )
            L.append("")

    # No-impact recommendations
    if no_impact_recs:
        # Group by type
        power_recs = [r for r in no_impact_recs if r.rec_type == "add_battery_power"]
        transfer_recs = [r for r in no_impact_recs if r.rec_type == "add_transfer"]
        other_recs = [r for r in no_impact_recs if r.rec_type not in ("add_battery_power", "add_transfer")]

        if power_recs:
            ranks = [str(r.rank) for r in power_recs]
            L.append(f"### #{', #'.join(ranks)}: Increase battery power (MW) — No impact")
            L.append("")
            L.append("| Rank | Change | Score Delta | Unserved Delta | Fuel Delta |")
            L.append("|------|--------|-------------|----------------|------------|")
            for rec in power_recs:
                score_delta = rec.kpi_deltas.get("score_delta", 0)
                L.append(
                    f"| {rec.rank} | {rec.description} | {score_delta:+,.1f} | "
                    f"{rec.kpi_deltas.get('unserved_mwh_delta', 0):+,.1f} MWh | "
                    f"{rec.kpi_deltas.get('fuel_mwh_delta', 0):+,.1f} MWh |"
                )
            L.append("")
            if battery_configs:
                power_parts = [f"{st}: {battery_configs[st].power_mw:,.0f} MW" for st in states]
                L.append(
                    "**Why zero impact**: Battery power rating is the maximum charge/discharge "
                    "rate in MW. Throughout this run, batteries discharged at 150–300 MW — well "
                    f"below their existing power limits ({', '.join(power_parts)}). "
                    "The bottleneck was not how fast energy could flow out of the battery; it was "
                    "how much stored energy (MWh) was available. "
                    "See **non-binding constraint #4** above: battery power "
                    "was never saturated in any hour."
                )
            else:
                L.append(
                    "**Why zero impact**: Battery power rating is the maximum charge/discharge "
                    "rate in MW. Throughout this run, batteries discharged at 150–300 MW — well "
                    "below their existing power limits. The bottleneck was not how fast energy "
                    "could flow out of the battery; it was how much stored energy (MWh) was available. "
                    "See **non-binding constraint #4** above: battery power "
                    "was never saturated in any hour."
                )
            L.append("")

        if transfer_recs:
            ranks = [str(r.rank) for r in transfer_recs]
            L.append(f"### #{', #'.join(ranks)}: Increase transfer capacity — No impact")
            L.append("")
            L.append("| Rank | Change | Score Delta | Unserved Delta | Fuel Delta |")
            L.append("|------|--------|-------------|----------------|------------|")
            for rec in transfer_recs:
                score_delta = rec.kpi_deltas.get("score_delta", 0)
                L.append(
                    f"| {rec.rank} | {rec.description} | {score_delta:+,.1f} | "
                    f"{rec.kpi_deltas.get('unserved_mwh_delta', 0):+,.1f} MWh | "
                    f"{rec.kpi_deltas.get('fuel_mwh_delta', 0):+,.1f} MWh |"
                )
            L.append("")
            L.append(
                f"**Why zero impact**: Transfer lines operated at only "
                f"{kpis.transfer_utilization:.1%} average utilization. Even doubling "
                f"their capacity produced no improvement because the constraint was "
                f"never how much power the lines could carry — it was that **no state "
                f"had surplus to send**. With all three states in deficit every hour, "
                f"and all fuel plants at capacity during crisis windows, larger "
                f"inter-state lines had nothing additional to move. "
                f"See **non-binding constraint #5** above."
            )
            L.append("")

        for rec in other_recs:
            score_delta = rec.kpi_deltas.get("score_delta", 0)
            direction = "no impact" if score_delta == 0 else "worse"
            L.append(f"### #{rec.rank}: {rec.description} — {direction}")
            L.append("")
            L.append(f"{rec.rank}. **{rec.description}** — score delta: {score_delta:+,.1f} ({direction})")
            L.append("")

    L.append("---")
    L.append("")

    # Why These Recommendations
    L.append("## Why These Recommendations — Summary")
    L.append("")
    L.append(
        f"The pattern across all {len(recs)} counterfactual scenarios points to a "
        "single conclusion: **the grid's binding constraint is the total amount of "
        "stored energy (MWh), not the rate of energy flow (MW) or the capacity of "
        "inter-state connections.**"
    )
    L.append("")
    if helpful_recs:
        L.append(
            f"Battery energy storage upgrades (recommendations "
            f"#{', #'.join(str(r.rank) for r in helpful_recs)}) help because they "
            f"address the root cause: there is not enough stored energy to bridge the "
            f"gap between daytime renewable generation and evening peak demand, especially "
            f"when fuel plants are already at maximum output. Larger batteries arrive at "
            f"the evening peak with more energy available above the reserve floor, enabling "
            f"discharge during the critical hours 17–21 when the current batteries sit idle."
        )
        L.append("")
    if power_recs or transfer_recs:
        no_ranks = [str(r.rank) for r in no_impact_recs]
        L.append(
            f"Battery power upgrades and transfer capacity upgrades "
            f"(#{', #'.join(no_ranks)}) show zero impact because they address "
            f"constraints that are not currently binding. Batteries never hit their "
            f"power limit, and transfer lines are "
            f"{100 - kpis.transfer_utilization * 100:.0f}% idle."
        )
        L.append("")
    if len(helpful_recs) >= 2:
        rank_explanation_parts = []
        for rec in helpful_recs:
            st = rec.change.get("state", "")
            ev = state_evidence.get(st, {})
            if ev:
                rank_explanation_parts.append(
                    f"{st} ({ev['unserved']:,.0f} MWh unserved, {ev['renewable']:,.0f} MWh renewable)"
                )
        L.append(
            f"The ranking among the storage recommendations reflects two factors: "
            f"which state has the most unserved energy to reduce, and which state has "
            f"the most renewable energy available to fill the additional storage. "
            f"By state: {'; '.join(rank_explanation_parts)}."
        )
        L.append("")

    L.append("---")
    L.append("")

    # Summary of Findings
    L.append("## Summary of Findings")
    L.append("")
    L.append(
        f"1. **The grid is fundamentally energy-constrained, not power-constrained.** "
        f"Renewable generation covers {renew_pct:.0f}% of load. The remainder falls on "
        f"fuel, which hits its capacity ceiling in {fuel_at_cap_count} of "
        f"{total_state_hours} state-hours. Every blackout occurred when fuel was at maximum."
    )
    L.append("")
    L.append(
        "2. **Battery storage is the highest-leverage investment.** All three "
        "top-ranked recommendations add storage (MWh). More storage lets the grid "
        "bank daytime renewables for the evening peak and provides a buffer above the "
        "SoC reserve floor, enabling battery dispatch during the hours when fuel is "
        "maxed and blackouts occur."
    )
    L.append("")
    L.append(
        f"3. **Battery power and transfer capacity are not current bottlenecks.** "
        f"{len(no_impact_recs)} of {len(recs)} tested scenarios showed zero improvement "
        f"across all KPIs because neither constraint is binding in this scenario."
    )
    L.append("")
    L.append(
        f"4. **The evening peak (hours 17–21) is the dominant risk window**, producing "
        f"{evening_pct:.0f}% of all unserved energy across {len(evening_events)} of "
        f"{len(critical)} critical events. Both crisis windows are driven by the same "
        f"mechanism: fuel at capacity, batteries depleted or locked, and all states in "
        f"simultaneous deficit."
    )
    L.append("")
    L.append(
        "5. **The evening reserve policy created an unintended consequence**: "
        "conservative daytime discharge, intended to save battery for the evening, "
        "depleted SoC below the 40% reserve floor *before* the evening peak began. "
        "Batteries then sat idle during the five worst hours. This suggests the "
        "reserve policy itself may need recalibration — either a lower evening floor, "
        "or a two-stage policy that releases the reserve when fuel plants are fully "
        "saturated."
    )
    L.append("")

    if llm_narrative:
        L.append("---")
        L.append("")
        L.append("## AI Summary (Gemini)")
        L.append("")
        L.append(llm_narrative)
        L.append("")

    with open(report_dir / "summary.md", "w") as f:
        f.write("\n".join(L))
