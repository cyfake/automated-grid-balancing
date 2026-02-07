"""
Ingestion agent: loads hourly grid data from the canonical processed CSV.

Data flow:
  1. If data/processed/eia_hourly.csv exists → read it (primary path)
  2. Otherwise → call the EIA client to fetch and cache it, then read

All downstream agents receive the same List[GridState] regardless of which
path was taken.
"""
import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from ..schemas.models import GridState
from ..utils.helpers import DATA_PROCESSED


# Default processed file written by the EIA client
_DEFAULT_CSV = DATA_PROCESSED / "eia_hourly.csv"
_PROVENANCE_JSON = DATA_PROCESSED / "eia_hourly.provenance.json"


def _load_csv(filepath: str | Path) -> List[Dict]:
    """Load a CSV into a list of dicts."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _ensure_processed_csv(csv_path: Path) -> Path:
    """If no processed CSV exists, fetch from EIA and write one."""
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path

    print("  No processed data found — fetching from EIA API …")
    from ..utils.eia_client import build_processed_csv
    build_processed_csv(csv_path, hours=48)
    return csv_path


def ingest(data_dir: str = None) -> List[GridState]:
    """
    Load the canonical processed CSV and return unified GridState records.

    Parameters
    ----------
    data_dir : str, optional
        Directory containing the processed CSV.  Defaults to data/processed/.
        The file must be named ``eia_hourly.csv`` (or be the only CSV present).

    Returns
    -------
    List[GridState]
    """
    if data_dir is None:
        csv_path = _DEFAULT_CSV
    else:
        d = Path(data_dir)
        csv_path = d / "eia_hourly.csv"
        if not csv_path.exists():
            # Fall back to any CSV in the directory
            csvs = sorted(d.glob("*.csv"))
            csv_path = csvs[0] if csvs else d / "eia_hourly.csv"

    csv_path = _ensure_processed_csv(csv_path)

    rows = _load_csv(csv_path)
    if not rows:
        raise FileNotFoundError(f"Processed CSV is empty: {csv_path}")

    all_records: List[GridState] = []
    for row in rows:
        gs = GridState(
            state=row["state"],
            hour=int(row["hour"]),
            load_mw=float(row["load_mw"]),
            solar_mw=float(row["solar_mw"]),
            wind_mw=float(row["wind_mw"]),
            fuel_capacity_mw=float(row["fuel_capacity_mw"]),
            battery_power_mw=float(row["battery_power_mw"]),
            battery_energy_mwh=float(row["battery_energy_mwh"]),
            battery_efficiency=float(row["battery_efficiency"]),
            battery_soc_mwh=float(row["battery_initial_soc_mwh"]),
        )
        all_records.append(gs)

    return all_records


def data_provenance() -> Optional[Dict]:
    """
    Return the provenance metadata written alongside the processed CSV,
    or None if the sidecar file doesn't exist.
    """
    if _PROVENANCE_JSON.exists():
        with open(_PROVENANCE_JSON) as f:
            return json.load(f)
    return None
