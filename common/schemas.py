from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

# --- Configuration Schemas ---

class DatasetConfig(BaseModel):
    pjm_dir: str = Field(..., description="Directory containing PJM hourly load CSVs")
    pjm_pattern: str = Field("*_hourly.csv", description="Glob pattern for PJM files")
    region: Optional[str] = Field(None, description="Specific region to filter for (e.g., 'PJM')")

class ExogenousConfig(BaseModel):
    eia_fuelmix_csv: Optional[str] = Field(None, description="Path to EIA fuel mix CSV")
    noaa_isdlite_dir: Optional[str] = Field(None, description="Directory containing NOAA ISD-Lite data")
    stations: Optional[List[str]] = Field(None, description="List of NOAA station IDs to use")

# --- Runtime Data Structures ---

class GridState(BaseModel):
    t: int = Field(..., description="Simulation step index")
    timestamp: datetime = Field(..., description="Wall clock time")
    region: str = Field(..., description="Region identifier")
    demand_mw: float = Field(..., description="Total load in MW")
    renewable_mw: float = Field(..., description="Combined Solar+Wind generation in MW")
    solar_mw: float = Field(0.0, description="Solar generation in MW")
    wind_mw: float = Field(0.0, description="Wind generation in MW")
    wind_ms: Optional[float] = Field(None, description="Wind speed in m/s")
    temp_c: Optional[float] = Field(None, description="Temperature in Celsius")
    reserve_proxy: float = Field(0.0, description="Available reserve margin proxy (MW)")
    freq_proxy: float = Field(60.0, description="Grid frequency proxy (Hz)")
    
    # New fields from Electricity Maps API
    carbon_intensity: Optional[float] = Field(None, description="Carbon intensity (gCO2eq/kWh)")
    renewable_percentage: Optional[float] = Field(None, description="Renewable energy percentage")
    fossil_free_percentage: Optional[float] = Field(None, description="Fossil-free energy percentage")

class ForecastBundle(BaseModel):
    demand_path: List[float] = Field(..., description="Forecasted demand for horizon")
    renewable_path: List[float] = Field(..., description="Forecasted renewables for horizon")
    sigma_demand: float = Field(..., description="Uncertainty in demand forecast")
    sigma_renew: float = Field(..., description="Uncertainty in renewable forecast")

class PolicyPack(BaseModel):
    reserve_min_mw: float = Field(..., description="Minimum reserve requirement (MW)")
    freq_min_hz: float = Field(59.9, description="Minimum frequency threshold (Hz)")
    ramp_limit_mw: float = Field(..., description="Max ramp rate per step (MW)")
    max_action_mw: float = Field(..., description="Max power adjustment per step (MW)")

class Action(BaseModel):
    battery_mw: float = Field(0.0, description="Battery charge (+) / discharge (-) MW")
    curtail_mw: float = Field(0.0, description="Renewable curtailment MW (always >= 0)")
    dr_mw: float = Field(0.0, description="Demand Response load reduction MW (always >= 0)")
    peaker_mw: float = Field(0.0, description="Peaker plant generation MW (always >= 0)")
    reasoning: str = Field("", description="Explanation for the action")

class AuditLog(BaseModel):
    step: int
    timestamp: datetime
    action: Action
    violations: List[str] = Field(default_factory=list)
    cost: float
    explanation: str

# --- Orchestrator I/O ---

class RunRequest(BaseModel):
    dataset: DatasetConfig
    exogenous: ExogenousConfig = Field(default_factory=ExogenousConfig)
    horizon_steps: int = Field(6, description="Planning horizon")
    n_steps: int = Field(48, description="Number of simulation steps")

class RunResult(BaseModel):
    artifacts: Dict[str, str] = Field(..., description="Paths to generated artifacts")
    summary: Dict[str, float] = Field(..., description="Summary metrics")
    violations_count: int = Field(..., description="Total constraint violations")
