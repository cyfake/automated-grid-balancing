"""
State builder agent: cleans ingested records and builds canonical
per-state, per-hour series.
"""
from typing import Dict, List, Tuple

from ..schemas.models import GridState, BatteryConfig


def build_state_series(
    records: List[GridState],
    start_hour: int = 0,
    num_hours: int = 48,
) -> Tuple[Dict[str, List[GridState]], Dict[str, BatteryConfig]]:
    """
    Organize records into {state: [GridState for each hour]} and extract
    battery configs (from initial hour).

    Returns:
        state_series: {state_name: [GridState, ...]} ordered by hour
        battery_configs: {state_name: BatteryConfig}
    """
    by_state: Dict[str, Dict[int, GridState]] = {}
    for gs in records:
        if gs.hour < start_hour or gs.hour >= start_hour + num_hours:
            continue
        by_state.setdefault(gs.state, {})[gs.hour] = gs

    state_series: Dict[str, List[GridState]] = {}
    battery_configs: Dict[str, BatteryConfig] = {}

    for state, hour_map in sorted(by_state.items()):
        hours_sorted = sorted(hour_map.keys())
        state_series[state] = [hour_map[h] for h in hours_sorted]

        # Battery config from first hour
        first = hour_map[hours_sorted[0]]
        battery_configs[state] = BatteryConfig(
            power_mw=first.battery_power_mw,
            energy_mwh=first.battery_energy_mwh,
            efficiency=first.battery_efficiency,
            initial_soc_mwh=first.battery_soc_mwh,
        )

    return state_series, battery_configs
