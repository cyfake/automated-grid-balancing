"""
EIA Open Data API client.

Fetches hourly generation-by-fuel-type and demand data from the U.S. Energy
Information Administration (EIA) for three regions: CAL (CA), ERCO (TX),
NYIS (NY).  Transforms the response into the canonical CSV format consumed
by the ingestion agent.

API documentation: https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data
Data source: Form EIA-930, Hourly Electric Grid Monitor
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE = "https://api.eia.gov/v2/electricity/rto"
_FUEL_TYPE_DATA = f"{_BASE}/fuel-type-data/data"
_REGION_DATA = f"{_BASE}/region-data/data"

# EIA respondent → short state code used throughout the pipeline.
# NOTE: The fuel-type-data endpoint uses "CAL" for California (the full
# region), not "CISO" (which only covers CAISO on the demand endpoint).
# We use the respondent codes that are consistent across BOTH endpoints.
RESPONDENT_TO_STATE = {
    "CAL":  "CA",   # California (full region)
    "ERCO": "TX",   # Electric Reliability Council of Texas
    "NYIS": "NY",   # New York Independent System Operator
}

RESPONDENTS = list(RESPONDENT_TO_STATE.keys())

# Fuels we categorise as "renewable" (used directly in the planner)
RENEWABLE_FUELS = {"SUN", "WND"}

# Fuels that count toward dispatchable / fuel capacity
DISPATCHABLE_FUELS = {"NG", "COL", "NUC", "OIL", "GEO", "WAT"}

# Battery assumptions per state.
# EIA does not publish hourly battery capacity data for each ISO.  The
# values below are order-of-magnitude estimates informed by DOE and CAISO
# published interconnection queues (2024).  They are held constant across
# all hours.
#
#   power_mw        – max charge / discharge rate (MW)
#   energy_mwh      – total usable stored energy (MWh)
#   efficiency      – round-trip AC efficiency (0-1)
#   initial_soc_mwh – assumed starting state-of-charge (MWh)
BATTERY_ASSUMPTIONS: Dict[str, Dict[str, float]] = {
    "CA": {"power_mw": 4000, "energy_mwh": 16000, "efficiency": 0.88, "initial_soc_mwh": 8000},
    "TX": {"power_mw": 3000, "energy_mwh": 12000, "efficiency": 0.90, "initial_soc_mwh": 6000},
    "NY": {"power_mw": 2000, "energy_mwh": 8000,  "efficiency": 0.85, "initial_soc_mwh": 4000},
}

# When computing fuel_capacity_mw we take the peak observed dispatchable
# generation for a state across the entire window and add this fraction as
# headroom, so that the planner's fuel ceiling is slightly above the
# empirical maximum.
FUEL_CAPACITY_HEADROOM = 0.15

CSV_COLUMNS = [
    "state", "hour", "hour_of_day", "load_mw", "solar_mw", "wind_mw",
    "fuel_capacity_mw", "battery_power_mw", "battery_energy_mwh",
    "battery_efficiency", "battery_initial_soc_mwh",
]


# ---------------------------------------------------------------------------
# Low-level API helpers
# ---------------------------------------------------------------------------

def _api_key() -> str:
    """Return the EIA API key from the environment or fall back to DEMO_KEY."""
    return os.environ.get("EIA_API_KEY", "DEMO_KEY")


def _fetch_json(base_url: str, params: dict, max_retries: int = 5) -> dict:
    """Build a GET request with properly encoded params and return JSON.
    Retries on HTTP 429 (rate-limit) with exponential back-off."""
    import time as _time
    from urllib.error import HTTPError

    parts = []
    for k, v in params.items():
        if isinstance(v, list):
            for item in v:
                parts.append(f"{k}={item}")
        else:
            parts.append(f"{k}={v}")
    url = base_url + "?" + "&".join(parts)

    for attempt in range(max_retries):
        try:
            req = Request(url, headers={"User-Agent": "grid-balance-agent/1.0"})
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = 30 * (attempt + 1)
                print(f"  [rate-limited] Waiting {wait}s before retry ({attempt + 1}/{max_retries}) …")
                _time.sleep(wait)
            else:
                raise


def _eia_params(
    api_key: str,
    respondents: List[str],
    start: str,
    end: str,
    extra: Optional[Dict] = None,
) -> dict:
    """Build the common params dict for an EIA v2 query."""
    p = {
        "api_key": api_key,
        "frequency": "hourly",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": "5000",
        "start": start,
        "end": end,
    }
    for i, r in enumerate(respondents):
        p[f"facets[respondent][{i}]"] = r
    if extra:
        p.update(extra)
    return p


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_fuel_type_data(
    respondents: List[str],
    start: str,
    end: str,
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Fetch hourly generation-by-fuel-type from EIA.

    Returns a list of dicts with keys:
        period, respondent, fueltype, type-name, value
    """
    key = api_key or _api_key()
    params = _eia_params(key, respondents, start, end)
    result = _fetch_json(_FUEL_TYPE_DATA, params)
    data = result.get("response", {}).get("data", [])
    if not data:
        raise RuntimeError(
            f"EIA fuel-type-data returned no records for {respondents} "
            f"({start} – {end}).  Check your API key and date range."
        )
    return data


def fetch_demand_data(
    respondents: List[str],
    start: str,
    end: str,
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Fetch hourly demand (type "D") from EIA region-data.

    Returns a list of dicts with keys:
        period, respondent, type, type-name, value
    """
    key = api_key or _api_key()
    params = _eia_params(key, respondents, start, end)
    params["facets[type][0]"] = "D"
    result = _fetch_json(_REGION_DATA, params)
    data = result.get("response", {}).get("data", [])
    if not data:
        raise RuntimeError(
            f"EIA region-data returned no records for {respondents} "
            f"({start} – {end}).  Check your API key and date range."
        )
    return data


# ---------------------------------------------------------------------------
# Transform EIA data → canonical CSV
# ---------------------------------------------------------------------------

def _default_time_range(hours: int = 48):
    """Return (start, end) strings for the most recent complete `hours`-hour
    window, leaving a 6-hour reporting lag."""
    now_utc = datetime.now(timezone.utc)
    end_dt = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=6)
    start_dt = end_dt - timedelta(hours=hours)
    fmt = "%Y-%m-%dT%H"
    return start_dt.strftime(fmt), end_dt.strftime(fmt)


def build_processed_csv(
    output_path: str | Path,
    hours: int = 48,
    start: Optional[str] = None,
    end: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Path:
    """
    Fetch EIA data and write a canonical CSV to *output_path*.

    The CSV has one row per (state, hour) with the columns expected by
    the ingestion agent.

    Returns the Path to the written file and prints provenance info.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if start is None or end is None:
        start, end = _default_time_range(hours)

    print(f"  Fetching EIA fuel-type data ({start} → {end}) …")
    fuel_rows = fetch_fuel_type_data(RESPONDENTS, start, end, api_key)

    print(f"  Fetching EIA demand data ({start} → {end}) …")
    demand_rows = fetch_demand_data(RESPONDENTS, start, end, api_key)

    # --- Organise raw records by (respondent, period) ---
    # fuel_map[respondent][period] = {fueltype: value_mw, ...}
    fuel_map: Dict[str, Dict[str, Dict[str, float]]] = {}
    for row in fuel_rows:
        r = row["respondent"]
        p = row["period"]
        ft = row["fueltype"]
        val = float(row["value"])
        fuel_map.setdefault(r, {}).setdefault(p, {})[ft] = val

    # demand_map[respondent][period] = demand_mw
    demand_map: Dict[str, Dict[str, float]] = {}
    for row in demand_rows:
        r = row["respondent"]
        p = row["period"]
        demand_map.setdefault(r, {})[p] = float(row["value"])

    # --- Determine the common set of periods across all respondents ---
    all_periods = set()
    for r in RESPONDENTS:
        if r in fuel_map:
            all_periods |= fuel_map[r].keys()
    periods = sorted(all_periods)[:hours]
    if len(periods) < hours:
        print(f"  [warn] Only {len(periods)} common hours available (requested {hours})")

    # --- Compute per-state peak dispatchable generation for fuel_capacity ---
    peak_dispatchable: Dict[str, float] = {RESPONDENT_TO_STATE[r]: 0.0 for r in RESPONDENTS}
    for r in RESPONDENTS:
        st = RESPONDENT_TO_STATE[r]
        for period in periods:
            fuels = fuel_map.get(r, {}).get(period, {})
            disp = sum(max(0, fuels.get(ft, 0)) for ft in DISPATCHABLE_FUELS)
            if disp > peak_dispatchable[st]:
                peak_dispatchable[st] = disp

    fuel_capacity: Dict[str, float] = {
        st: round(peak * (1 + FUEL_CAPACITY_HEADROOM), 2)
        for st, peak in peak_dispatchable.items()
    }

    print(f"  Derived fuel capacity (peak dispatchable × {1 + FUEL_CAPACITY_HEADROOM:.2f}):")
    for st in sorted(fuel_capacity):
        print(f"    {st}: {fuel_capacity[st]:,.0f} MW  (peak observed: {peak_dispatchable[st]:,.0f} MW)")

    # --- Build CSV rows ---
    csv_rows = []
    for h_idx, period in enumerate(periods):
        for r in RESPONDENTS:
            st = RESPONDENT_TO_STATE[r]
            fuels = fuel_map.get(r, {}).get(period, {})
            demand = demand_map.get(r, {}).get(period, 0)

            solar = max(0, fuels.get("SUN", 0))
            wind = max(0, fuels.get("WND", 0))

            batt = BATTERY_ASSUMPTIONS[st]

            csv_rows.append({
                "state": st,
                "hour": h_idx,
                "hour_of_day": h_idx % 24,
                "load_mw": round(demand, 2),
                "solar_mw": round(solar, 2),
                "wind_mw": round(wind, 2),
                "fuel_capacity_mw": fuel_capacity[st],
                "battery_power_mw": batt["power_mw"],
                "battery_energy_mwh": batt["energy_mwh"],
                "battery_efficiency": batt["efficiency"],
                "battery_initial_soc_mwh": batt["initial_soc_mwh"],
            })

    # --- Write ---
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"  Wrote {len(csv_rows)} rows to {output_path}")
    print(f"  Period: {periods[0]} → {periods[-1]} (UTC)")

    # Also write a small provenance sidecar
    provenance = {
        "source": "EIA Open Data API (Form EIA-930)",
        "endpoints": [_FUEL_TYPE_DATA, _REGION_DATA],
        "respondents": {r: RESPONDENT_TO_STATE[r] for r in RESPONDENTS},
        "period_start": periods[0],
        "period_end": periods[-1],
        "hours": len(periods),
        "fuel_capacity_method": f"peak observed dispatchable + {FUEL_CAPACITY_HEADROOM:.0%} headroom",
        "battery_assumptions": BATTERY_ASSUMPTIONS,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_key_source": "EIA_API_KEY env var" if os.environ.get("EIA_API_KEY") else "DEMO_KEY (default)",
    }
    prov_path = output_path.with_suffix(".provenance.json")
    with open(prov_path, "w") as f:
        json.dump(provenance, f, indent=2)
    print(f"  Provenance: {prov_path}")

    return output_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from ..utils.helpers import DATA_PROCESSED
    build_processed_csv(DATA_PROCESSED / "eia_hourly.csv")
