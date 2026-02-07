"""
Core data models for the grid load-balancing MVP.
All schemas use dataclasses for zero external dependencies.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json


# ---------------------------------------------------------------------------
# Per state-hour snapshot
# ---------------------------------------------------------------------------
@dataclass
class GridState:
    """Single hour observation for one state."""
    state: str
    hour: int  # 0-23
    load_mw: float
    solar_mw: float
    wind_mw: float
    fuel_capacity_mw: float  # max available fuel generation
    battery_power_mw: float  # max charge/discharge rate
    battery_energy_mwh: float  # total battery capacity
    battery_efficiency: float  # round-trip efficiency (0-1)
    battery_soc_mwh: float  # current state of charge


# ---------------------------------------------------------------------------
# 24-hour forecast bundle for one state
# ---------------------------------------------------------------------------
@dataclass
class StateForecast:
    """24h forecast arrays for a single state."""
    state: str
    load: List[float]  # len 24
    solar: List[float]
    wind: List[float]
    fuel_capacity: List[float]


@dataclass
class ForecastPack:
    """Forecasts for all states."""
    states: Dict[str, StateForecast] = field(default_factory=dict)
    hours: int = 24


# ---------------------------------------------------------------------------
# Transfer link
# ---------------------------------------------------------------------------
@dataclass
class TransferLink:
    from_state: str
    to_state: str
    capacity_mw: float


@dataclass
class TransferTopology:
    links: List[TransferLink] = field(default_factory=list)

    def get_capacity(self, from_state: str, to_state: str) -> float:
        for link in self.links:
            if link.from_state == from_state and link.to_state == to_state:
                return link.capacity_mw
        return 0.0


# ---------------------------------------------------------------------------
# Hourly action (decision)
# ---------------------------------------------------------------------------
@dataclass
class HourlyAction:
    """Dispatch decision for one hour across all states."""
    hour: int
    # Per-state values (keyed by state name)
    battery_charge_mw: Dict[str, float] = field(default_factory=dict)
    battery_discharge_mw: Dict[str, float] = field(default_factory=dict)
    fuel_dispatch_mw: Dict[str, float] = field(default_factory=dict)
    curtailment_mw: Dict[str, float] = field(default_factory=dict)
    unserved_mw: Dict[str, float] = field(default_factory=dict)
    # Transfer matrix: {(from, to): MW}
    transfers_mw: Dict[str, float] = field(default_factory=dict)
    # SoC after this hour
    soc_after_mwh: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "hour": self.hour,
            "battery_charge_mw": self.battery_charge_mw,
            "battery_discharge_mw": self.battery_discharge_mw,
            "fuel_dispatch_mw": self.fuel_dispatch_mw,
            "curtailment_mw": self.curtailment_mw,
            "unserved_mw": self.unserved_mw,
            "transfers_mw": self.transfers_mw,
            "soc_after_mwh": self.soc_after_mwh,
        }


# ---------------------------------------------------------------------------
# Full 24-hour plan
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    actions: List[HourlyAction] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "actions": [a.to_dict() for a in self.actions],
        }


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
@dataclass
class KPIs:
    total_unserved_mwh: float = 0.0
    total_curtailment_mwh: float = 0.0
    total_fuel_mwh: float = 0.0
    total_renewable_mwh: float = 0.0
    total_load_mwh: float = 0.0
    renewable_utilization: float = 0.0  # fraction of available renewables used
    transfer_utilization: float = 0.0  # fraction of transfer capacity used
    battery_cycles_proxy: float = 0.0  # total discharge MWh / total capacity

    def to_dict(self) -> dict:
        return {
            "total_unserved_mwh": round(self.total_unserved_mwh, 2),
            "total_curtailment_mwh": round(self.total_curtailment_mwh, 2),
            "total_fuel_mwh": round(self.total_fuel_mwh, 2),
            "total_renewable_mwh": round(self.total_renewable_mwh, 2),
            "total_load_mwh": round(self.total_load_mwh, 2),
            "renewable_utilization": round(self.renewable_utilization, 4),
            "transfer_utilization": round(self.transfer_utilization, 4),
            "battery_cycles_proxy": round(self.battery_cycles_proxy, 4),
        }


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
@dataclass
class Recommendation:
    rank: int
    rec_type: str  # "add_storage", "add_transfer", "add_battery_power"
    description: str
    change: Dict = field(default_factory=dict)
    kpi_deltas: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "type": self.rec_type,
            "description": self.description,
            "change": self.change,
            "kpi_deltas": self.kpi_deltas,
        }


# ---------------------------------------------------------------------------
# Battery config (per state)
# ---------------------------------------------------------------------------
@dataclass
class BatteryConfig:
    power_mw: float
    energy_mwh: float
    efficiency: float  # round-trip, 0-1
    initial_soc_mwh: float


# ---------------------------------------------------------------------------
# Policy weights / constraints
# ---------------------------------------------------------------------------
@dataclass
class PolicyConfig:
    unserved_penalty: float = 1000.0
    curtailment_penalty: float = 1.0
    fuel_penalty: float = 10.0
    min_soc_fraction: float = 0.1  # keep at least 10% SoC
    soc_reserve_evening_fraction: float = 0.4  # target 40% for evening peak
    evening_peak_start: int = 17  # hour
    evening_peak_end: int = 21  # hour
