import pandas as pd
from agentfield import Agent, app
from automated_grid_balancing.common.schemas import ForecastBundle
from automated_grid_balancing.common.utils import setup_logging

logger = setup_logging("forecast_agent")

@app.agent
class ForecastAgent(Agent):
    name = "forecast_agent"
    description = "Generates short-term load and renewable forecasts"
    tags = ["forecast"]

    @app.skill
    def forecast(self, state, horizon_steps: int) -> ForecastBundle:
        """Persistence forecast: assumes next H steps = current step + 0 noise."""
        
        last_load = state.demand_mw
        last_renew = state.renewable_mw
        
        # Create persistent horizon based purely on the real-time API values 
        # (This can be improved later to use real weather forecasting APIs)
        future_load = [last_load for _ in range(horizon_steps)]
        future_renew = [last_renew for _ in range(horizon_steps)]

        # If perfectly 0, add minimal noise base to avoid math issues downstream
        base_demand_sigma = max(last_load * 0.02, 10.0)
        base_renew_sigma = max(last_renew * 0.10, 5.0)

        return ForecastBundle(
            demand_path=future_load,
            renewable_path=future_renew,
            sigma_demand=base_demand_sigma,
            sigma_renew=base_renew_sigma
        )
