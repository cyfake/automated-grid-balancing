from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator

class GridState(BaseModel):
    """Snapshot of the physical grid state."""
    timestamp: datetime
    demand_mw: float = Field(..., ge=0, description="Current power demand in MW")
    solar_mw: float = Field(..., ge=0, description="Current solar generation in MW")
    wind_mw: float = Field(0.0, ge=0, description="Current wind generation in MW")
    battery_soc_mwh: float = Field(..., ge=0, description="Battery State of Charge in MWh")
    battery_max_mwh: float = Field(default=100.0, ge=0)
    current_price: float = Field(..., description="Electricity price ($/MWh)")
    net_demand_mw: float = 0.0

    def __init__(self, **data):
        super().__init__(**data)
        self.net_demand_mw = self.demand_mw - (self.solar_mw + self.wind_mw)

class ForecastBundle(BaseModel):
    """Predictions for future periods."""
    timestamp: datetime
    horizon_hours: int = 24
    demand_forecast: Dict[str, float]
    solar_forecast: Dict[str, float]
    price_forecast: Dict[str, float]

class PolicyPack(BaseModel):
    """Current operating constraints and objectives."""
    max_battery_discharge_mw: float = 20.0
    max_battery_charge_mw: float = 20.0
    min_soc_pct: float = Field(0.1, ge=0, le=1)
    target_soc_pct: float = Field(0.5, ge=0, le=1)
    peaker_threshold_price: float = 150.0

class DispatchPlan(BaseModel):
    """Instructions for the next step."""
    timestamp: datetime
    battery_charge_mw: float = 0.0  # Positive for charging, negative for discharging
    peaker_mw: float = 0.0
    reasoning: str = ""

class StepResult(BaseModel):
    """Outcome of an environment transition."""
    prev_state: GridState
    next_state: GridState
    action: DispatchPlan
    total_cost: float
    baseline_cost: float = 0.0
    carbon_score: float

class AuditLog(BaseModel):
    """Traceability for agent actions."""
    timestamp: datetime
    agent_name: str
    input_snapshot: Dict
    output_snapshot: Dict
    decision_id: str
    metadata: Optional[Dict] = None

if __name__ == "__main__":
    # Self-test validation
    try:
        test_state = GridState(
            timestamp=datetime.now(),
            demand_mw=50.5,
            solar_mw=10.0,
            battery_soc_mwh=45.0,
            current_price=65.0
        )
        print("Schema Validation Success: GridState initialized correctly.")
        print(f"Net Demand Calculated: {test_state.net_demand_mw} MW")
    except Exception as e:
        print(f"Validation Error: {e}")
