"""
Forecast agent: builds 24h forecast from historical data.
MVP approach: use the next 24h of actual data as the base forecast,
add optional uncertainty bands (±10%).
"""
from typing import Dict, List

from ..schemas.models import GridState, StateForecast, ForecastPack


def build_forecast(
    state_series: Dict[str, List[GridState]],
    start_hour: int = 0,
    horizon: int = 24,
) -> ForecastPack:
    """
    Build 24h forecast for each state starting from start_hour index.
    Uses actual data as "perfect forecast" for the MVP.
    """
    pack = ForecastPack(hours=horizon)

    for state, series in state_series.items():
        window = series[start_hour : start_hour + horizon]
        if len(window) < horizon:
            # pad with last known values
            while len(window) < horizon:
                window.append(window[-1])

        sf = StateForecast(
            state=state,
            load=[gs.load_mw for gs in window],
            solar=[gs.solar_mw for gs in window],
            wind=[gs.wind_mw for gs in window],
            fuel_capacity=[gs.fuel_capacity_mw for gs in window],
        )
        pack.states[state] = sf

    return pack


def add_uncertainty_bands(
    forecast: ForecastPack, pct: float = 0.10
) -> Dict[str, Dict[str, Dict[str, List[float]]]]:
    """
    Returns {state: {variable: {"low": [...], "high": [...]}}}
    """
    bands = {}
    for state, sf in forecast.states.items():
        bands[state] = {}
        for var_name in ["load", "solar", "wind", "fuel_capacity"]:
            vals = getattr(sf, var_name)
            bands[state][var_name] = {
                "low": [v * (1 - pct) for v in vals],
                "high": [v * (1 + pct) for v in vals],
            }
    return bands
