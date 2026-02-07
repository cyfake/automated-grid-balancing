"""
Simulation agent: applies a plan hour-by-hour and computes realized KPIs.
"""
from typing import Dict

from ..schemas.models import (
    Plan,
    ForecastPack,
    TransferTopology,
    BatteryConfig,
    KPIs,
)


def simulate(
    plan: Plan,
    forecast: ForecastPack,
    topology: TransferTopology,
    battery_configs: Dict[str, BatteryConfig],
) -> KPIs:
    """
    Verify the plan against forecast data and compute KPIs.
    This is a pure auditing pass — it doesn't re-optimize.
    """
    states = sorted(forecast.states.keys())
    hours = forecast.hours

    total_unserved = 0.0
    total_curtailment = 0.0
    total_fuel = 0.0
    total_renewable_used = 0.0
    total_renewable_available = 0.0
    total_load = 0.0
    total_transfer_used = 0.0
    total_transfer_capacity = 0.0
    total_discharge = 0.0
    total_battery_capacity = sum(b.energy_mwh for b in battery_configs.values())

    for h in range(min(hours, len(plan.actions))):
        action = plan.actions[h]

        for st in states:
            sf = forecast.states[st]
            load = sf.load[h]
            solar = sf.solar[h]
            wind = sf.wind[h]
            renewable_avail = solar + wind

            total_load += load
            total_renewable_available += renewable_avail

            # Renewable actually used = available - curtailed
            curtailed = action.curtailment_mw.get(st, 0)
            renewable_used = renewable_avail - curtailed
            total_renewable_used += renewable_used

            total_curtailment += curtailed
            total_fuel += action.fuel_dispatch_mw.get(st, 0)
            total_unserved += action.unserved_mw.get(st, 0)
            total_discharge += action.battery_discharge_mw.get(st, 0)

        # Transfer utilization
        for link in topology.links:
            key = f"{link.from_state}->{link.to_state}"
            used = action.transfers_mw.get(key, 0)
            total_transfer_used += used
            total_transfer_capacity += link.capacity_mw

    re_util = (total_renewable_used / total_renewable_available) if total_renewable_available > 0 else 1.0
    tr_util = (total_transfer_used / total_transfer_capacity) if total_transfer_capacity > 0 else 0.0
    batt_cycles = (total_discharge / total_battery_capacity) if total_battery_capacity > 0 else 0.0

    return KPIs(
        total_unserved_mwh=total_unserved,
        total_curtailment_mwh=total_curtailment,
        total_fuel_mwh=total_fuel,
        total_renewable_mwh=total_renewable_used,
        total_load_mwh=total_load,
        renewable_utilization=re_util,
        transfer_utilization=tr_util,
        battery_cycles_proxy=batt_cycles,
    )
