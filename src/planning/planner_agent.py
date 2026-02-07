"""
Planner agent: deterministic greedy dispatch with 24h lookahead.

Strategy:
1. Compute per-hour "scarcity scores" across the horizon.
2. Build a target SoC curve that reserves battery for high-scarcity hours.
3. Greedy per-hour dispatch:
   - Use renewables up to load
   - If deficit: discharge batteries (respecting reserve), imports, fuel
   - If surplus: charge batteries, exports, curtail
"""
from typing import Dict, List

from ..schemas.models import (
    ForecastPack,
    TransferTopology,
    BatteryConfig,
    PolicyConfig,
    HourlyAction,
    Plan,
)


def _compute_scarcity_scores(
    forecast: ForecastPack, states: List[str]
) -> Dict[str, List[float]]:
    """
    Scarcity = max(0, load - solar - wind) for each state-hour.
    Higher = more need for batteries/fuel.
    """
    scores: Dict[str, List[float]] = {}
    for st in states:
        sf = forecast.states[st]
        scores[st] = []
        for h in range(forecast.hours):
            deficit = sf.load[h] - sf.solar[h] - sf.wind[h]
            scores[st].append(max(0, deficit))
    return scores


def _build_soc_target_curve(
    scarcity: Dict[str, List[float]],
    battery_configs: Dict[str, BatteryConfig],
    policy: PolicyConfig,
    hours: int = 24,
) -> Dict[str, List[float]]:
    """
    Build target minimum SoC for each hour.
    Logic: look ahead from each hour; if future hours have high scarcity,
    keep more SoC. During evening peak, enforce higher reserve.
    """
    targets: Dict[str, List[float]] = {}

    for st, batt in battery_configs.items():
        t = []
        total_future_scarcity = sum(scarcity[st])
        for h in range(hours):
            # Base minimum
            base_min = batt.energy_mwh * policy.min_soc_fraction

            # Future scarcity ratio: how much scarcity remains after this hour
            remaining = sum(scarcity[st][h:])
            if total_future_scarcity > 0:
                future_ratio = remaining / total_future_scarcity
            else:
                future_ratio = 0

            # Evening peak boost
            hod = h % 24
            if policy.evening_peak_start <= hod <= policy.evening_peak_end:
                evening_target = batt.energy_mwh * policy.soc_reserve_evening_fraction
            else:
                evening_target = base_min

            # Blend: reserve proportional to future scarcity
            scarcity_target = base_min + (batt.energy_mwh * 0.5 - base_min) * future_ratio

            target = max(base_min, evening_target, scarcity_target)
            t.append(min(target, batt.energy_mwh))  # cap at max
        targets[st] = t

    return targets


def plan(
    forecast: ForecastPack,
    topology: TransferTopology,
    battery_configs: Dict[str, BatteryConfig],
    policy: PolicyConfig,
) -> Plan:
    """Run the greedy 24h planner."""
    states = sorted(forecast.states.keys())
    hours = forecast.hours
    scarcity = _compute_scarcity_scores(forecast, states)
    soc_targets = _build_soc_target_curve(scarcity, battery_configs, policy, hours)

    # Initialize SoC
    soc: Dict[str, float] = {st: battery_configs[st].initial_soc_mwh for st in states}
    actions: List[HourlyAction] = []

    for h in range(hours):
        action = HourlyAction(hour=h)

        # Step 1: compute net position per state (renewable - load)
        net: Dict[str, float] = {}
        for st in states:
            sf = forecast.states[st]
            renewable = sf.solar[h] + sf.wind[h]
            net[st] = renewable - sf.load[h]
            action.curtailment_mw[st] = 0.0
            action.battery_charge_mw[st] = 0.0
            action.battery_discharge_mw[st] = 0.0
            action.fuel_dispatch_mw[st] = 0.0
            action.unserved_mw[st] = 0.0

        # Step 2: battery dispatch per state
        for st in states:
            batt = battery_configs[st]
            eff = batt.efficiency
            sqrt_eff = eff ** 0.5  # one-way efficiency

            if net[st] < 0:
                # Deficit — try to discharge
                deficit = -net[st]
                # How much can we discharge while staying above target SoC?
                available_soc = max(0, soc[st] - soc_targets[st][h])
                max_discharge_energy = available_soc  # MWh in battery
                max_discharge_power = batt.power_mw
                # Actual output limited by power and energy
                discharge_output = min(deficit, max_discharge_power, max_discharge_energy * sqrt_eff)
                discharge_from_soc = discharge_output / sqrt_eff if sqrt_eff > 0 else 0

                action.battery_discharge_mw[st] = round(discharge_output, 2)
                soc[st] -= discharge_from_soc
                net[st] += discharge_output

            elif net[st] > 0:
                # Surplus — try to charge
                surplus = net[st]
                headroom = batt.energy_mwh - soc[st]
                max_charge_power = batt.power_mw
                charge_input = min(surplus, max_charge_power, headroom / sqrt_eff if sqrt_eff > 0 else 0)
                charge_to_soc = charge_input * sqrt_eff

                action.battery_charge_mw[st] = round(charge_input, 2)
                soc[st] += charge_to_soc
                net[st] -= charge_input

        # Step 3a: transfers (surplus states export to deficit states)
        deficit_states = [(st, -net[st]) for st in states if net[st] < 0]
        surplus_states = [(st, net[st]) for st in states if net[st] > 0]

        deficit_states.sort(key=lambda x: -x[1])
        surplus_states.sort(key=lambda x: -x[1])

        for dst, d_need in deficit_states:
            remaining_need = d_need
            for i, (src, s_avail) in enumerate(surplus_states):
                if remaining_need <= 0 or s_avail <= 0:
                    continue
                cap = topology.get_capacity(src, dst)
                transfer = min(remaining_need, s_avail, cap)
                if transfer > 0:
                    key = f"{src}->{dst}"
                    action.transfers_mw[key] = round(
                        action.transfers_mw.get(key, 0) + transfer, 2
                    )
                    remaining_need -= transfer
                    surplus_states[i] = (src, s_avail - transfer)
                    net[dst] += transfer
                    net[src] -= transfer

        # Step 4: fuel for remaining deficits
        fuel_used_this_hour: Dict[str, float] = {}
        for st in states:
            if net[st] < 0:
                deficit = -net[st]
                fuel_cap = forecast.states[st].fuel_capacity[h]
                fuel = min(deficit, fuel_cap)
                action.fuel_dispatch_mw[st] = round(fuel, 2)
                fuel_used_this_hour[st] = fuel
                net[st] += fuel
            else:
                fuel_used_this_hour[st] = 0.0

        # Step 5: fuel-backed transfers — states with spare fuel capacity
        # export to states still in deficit
        deficit_after_fuel = [(st, -net[st]) for st in states if net[st] < -0.01]
        deficit_after_fuel.sort(key=lambda x: -x[1])

        for dst, d_need in deficit_after_fuel:
            remaining_need = d_need
            for src in states:
                if src == dst or remaining_need <= 0:
                    continue
                spare_fuel = forecast.states[src].fuel_capacity[h] - fuel_used_this_hour[src]
                if spare_fuel <= 0:
                    continue
                cap = topology.get_capacity(src, dst)
                # Subtract any existing transfers on this link
                key = f"{src}->{dst}"
                already = action.transfers_mw.get(key, 0)
                avail_cap = cap - already
                if avail_cap <= 0:
                    continue
                transfer = min(remaining_need, spare_fuel, avail_cap)
                if transfer > 0:
                    action.transfers_mw[key] = round(already + transfer, 2)
                    action.fuel_dispatch_mw[src] = round(
                        action.fuel_dispatch_mw.get(src, 0) + transfer, 2
                    )
                    fuel_used_this_hour[src] += transfer
                    remaining_need -= transfer
                    net[dst] += transfer
                    # net[src] unchanged: fuel generation offsets export

        # Step 6: unserved energy for any remaining deficit
        for st in states:
            if net[st] < -0.01:
                action.unserved_mw[st] = round(-net[st], 2)
                net[st] = 0

        # Step 7: curtailment for remaining surplus
        for st in states:
            if net[st] > 0.01:
                action.curtailment_mw[st] = round(net[st], 2)

        # Record SoC
        for st in states:
            action.soc_after_mwh[st] = round(soc[st], 2)

        actions.append(action)

    return Plan(
        actions=actions,
        metadata={
            "planner": "greedy_lookahead_v1",
            "hours": hours,
            "states": states,
        },
    )
