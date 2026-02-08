from datetime import datetime, timedelta
from typing import Dict
from schemas import ForecastBundle, GridState

class ForecastAgent:
    """
    Forecast Agent responsible for predicting demand, solar, and price.
    For this demo, it uses a 'look-ahead' into the environment's data series.
    """
    def __init__(self, name: str = "ForecastAgent"):
        self.name = name

    def generate_forecast(self, env, horizon_hours: int = 24) -> ForecastBundle:
        """
        Generates a ForecastBundle by looking at the upcoming values in the environment.
        This represents a 'very good' forecaster.
        """
        current_idx = env.current_index
        demand_series = env.demand_series
        
        demand_fc = {}
        solar_fc = {}
        price_fc = {}
        
        start_ts = demand_series.index[current_idx]
        
        for h in range(1, horizon_hours + 1):
            idx = (current_idx + h) % len(demand_series)
            ts = demand_series.index[idx]
            ts_str = ts.isoformat()
            
            # Predict demand (exact from series)
            demand_fc[ts_str] = float(demand_series.iloc[idx])
            
            # Predict solar (use environment logic but without random ramps for 'clean' forecast)
            solar_fc[ts_str] = float(env._get_synthetic_solar(ts))
            
            # Predict price
            net_demand = demand_fc[ts_str] - solar_fc[ts_str]
            price_fc[ts_str] = float(env._get_synthetic_price(net_demand))
            
        return ForecastBundle(
            timestamp=start_ts,
            horizon_hours=horizon_hours,
            demand_forecast=demand_fc,
            solar_forecast=solar_fc,
            price_forecast=price_fc
        )
