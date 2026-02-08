import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, Dict
from pathlib import Path
from schemas import GridState, DispatchPlan, StepResult
from src.data_fetcher import NRELFetcher

class GridEnv:
    """
    Grid Simulation Environment.
    Manages the physical state of the grid, battery, and peaker plants.
    """
    def __init__(self, data_path: str = 'data/PJM hourly load data/pjm_hourly_est.csv'):
        self.data_path = Path(data_path)
        self.demand_series = self._load_pjm_data()
        self.current_index = 0
        
        # EIA Data Integration (Texas)
        self.eia_path = Path("data/eia_hourly.csv")
        self.eia_data = self._load_eia_data()
        
        # Real Solar/Wind Data Placeholders
        self.real_solar_data = pd.Series()
        self.real_wind_data = pd.Series()
        
        if not self.eia_data.empty:
             print("Using EIA Texas Data (Load + Solar + Wind)")
             self.demand_series = self.eia_data['load_mw']
             self.real_solar_data = self.eia_data['solar_mw']
             self.real_wind_data = self.eia_data['wind_mw']
        else:
             print("Fallback to PJM Data")
             self.demand_series = self._load_pjm_data()
             self.fetcher = NRELFetcher()
             self.real_solar_data = self._load_nrel_solar()

        # Battery Parameters (Example settings)
        self.battery_max_mwh = 100.0
        self.battery_soc_mwh = 50.0  # Start at 50%
        self.charge_efficiency = 0.95
        self.discharge_efficiency = 0.95
        
        # Peaker Parameters
        self.peaker_marginal_cost = 150.0  # $/MWh
        
    def _load_pjm_data(self) -> pd.Series:
        """Loads and cleans PJM demand data."""
        if not self.data_path.exists():
            raise FileNotFoundError(f"PJM data not found at {self.data_path}")
        
        df = pd.read_csv(self.data_path)
        # Assuming 'Datetime' is the column name as detected earlier
        df['Datetime'] = pd.to_datetime(df['Datetime'])
        df = df.sort_values('Datetime').reset_index(drop=True)
        # Use PJM_Load as the primary demand signal
        series = df.set_index('Datetime')['PJM_Load'].interpolate()
        return series

    def _get_synthetic_solar(self, ts: datetime) -> float:
        """Generates a synthetic solar-shaped curve (MW)."""
        hour = ts.hour + ts.minute / 60.0
        # Simple bell curve centered at 13:00 (1 PM)
        # Peak generation of 40,000 MW (scaled to PJM-like levels)
        peak_mw = 40000.0
        if 6 <= hour <= 18:
            # Sine curve from 0 to 1 back to 0
            val = np.sin(np.pi * (hour - 6) / 12)
            # Add occasional random "cloud ramps" (dips up to 40%)
            if np.random.random() < 0.1:  # 10% chance of sudden dip
                 val *= (0.6 + 0.4 * np.random.random())
            return val * peak_mw
        return 0.0

    def _get_synthetic_price(self, net_demand: float) -> float:
        """
        Calculates synthetic price based on net demand ($/MWh).
        Price increases exponentially as net demand nears grid limits.
        """
        base_price = 30.0
        price_scalar = 0.005 # Sensitivity
        # Price spikes when net demand is very high
        return base_price + np.exp(net_demand * price_scalar / 100)

    def _load_eia_data(self) -> pd.DataFrame:
        """Loads processed EIA data for TX if available."""
        if not self.eia_path.exists():
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(self.eia_path)
            # Filter for Texas
            df = df[df['state'] == 'TX'].copy()
            
            # Create a localized datetime index (assuming 2026 for demo continuity or use row year)
            # define a start date matching PJM or just use 2024
            start_date = datetime(2024, 1, 1, 0, 0)
            df['timestamp'] = [start_date + timedelta(hours=i) for i in range(len(df))]
            
            df = df.set_index('timestamp')
            return df[['load_mw', 'solar_mw', 'wind_mw']]
        except Exception as e:
            print(f"Error loading EIA data: {e}")
            return pd.DataFrame()

    def _load_nrel_solar(self) -> pd.Series:
        """Loads real solar data for the grid location (Legacy PJM/NREL path)."""
        # Only used if EIA data is missing
        if hasattr(self, 'fetcher'):
            # Philadelphia coordinates roughly
            lat, lon = 39.9526, -75.1652
            try:
                df = self.fetcher.fetch_solar_data(lat, lon, 2020)
                if df.empty: return pd.Series()
                df['dt'] = pd.to_datetime(df[['Year', 'Month', 'Day', 'Hour']])
                peaks = df['GHI'].max()
                scale = 20000.0 / peaks if peaks > 0 else 1.0
                return df.set_index('dt')['GHI'] * scale
            except:
                return pd.Series()
        return pd.Series()

    def get_state(self) -> GridState:
        """Returns the current GridState."""
        ts = self.demand_series.index[self.current_index]
        demand = self.demand_series.iloc[self.current_index]
        
        # Solar Handling
        solar = 0.0
        if not self.real_solar_data.empty:
            if ts in self.real_solar_data.index:
                solar = self.real_solar_data.loc[ts]
            else:
                 # Fallback logic for mismatched timestamps (cyclic)
                 # Map current simulation timestamp to data index using hour of year
                 idx = self.current_index % len(self.real_solar_data)
                 solar = self.real_solar_data.iloc[idx]
        else:
            solar = self._get_synthetic_solar(ts)

        # Wind Handling
        wind = 0.0
        if not self.real_wind_data.empty:
            if ts in self.real_wind_data.index:
                wind = self.real_wind_data.loc[ts]
            else:
                 idx = self.current_index % len(self.real_wind_data)
                 wind = self.real_wind_data.iloc[idx]

        # Calculate net demand: Load - (Solar + Wind)
        net_demand = demand - (solar + wind)
        price = self._get_synthetic_price(net_demand)
        
        return GridState(
            timestamp=ts,
            demand_mw=demand,
            solar_mw=solar,
            wind_mw=wind,
            battery_soc_mwh=self.battery_soc_mwh,
            battery_max_mwh=self.battery_max_mwh,
            current_price=price
        )

    def step(self, action: DispatchPlan) -> StepResult:
        """
        Transitions the environment based on the dispatch action.
        """
        prev_state = self.get_state()
        
        # 1. Update Battery SoC
        if action.battery_charge_mw > 0:
            # Charging
            actual_charge = min(action.battery_charge_mw, self.battery_max_mwh - self.battery_soc_mwh)
            self.battery_soc_mwh += actual_charge * self.charge_efficiency
        else:
            # Discharging (action is negative)
            actual_discharge = max(action.battery_charge_mw, -self.battery_soc_mwh)
            self.battery_soc_mwh += actual_discharge / self.discharge_efficiency # action is negative

        # Bounds check
        self.battery_soc_mwh = max(0.0, min(self.battery_soc_mwh, self.battery_max_mwh))

        # 2. Advance Time
        self.current_index = (self.current_index + 1) % len(self.demand_series)
        next_state = self.get_state()
        
        # 3. Calculate Cost (Simplistic)
        # Cost = (Peaker generation * marginal cost) + (Market price * Net Demand)
        # In a real grid, this is more complex, but for demo:
        market_cost = prev_state.net_demand_mw * prev_state.current_price
        peaker_cost = action.peaker_mw * self.peaker_marginal_cost
        total_cost = market_cost + peaker_cost
        
        # 4. Carbon Impact (Peaker = dirty, Solar = clean)
        carbon_score = (prev_state.net_demand_mw * 0.5) + (action.peaker_mw * 1.0)

        return StepResult(
            prev_state=prev_state,
            next_state=next_state,
            action=action,
            total_cost=total_cost,
            carbon_score=carbon_score
        )

if __name__ == "__main__":
    # Test Environment
    try:
        env = GridEnv()
        # Advance to noon (13 steps from 1 AM)
        for _ in range(12):
            env.current_index += 1
            
        initial_state = env.get_state()
        print(f"Noon State: {initial_state.timestamp}, Demand: {initial_state.demand_mw:.1f} MW, Solar: {initial_state.solar_mw:.1f} MW, Price: ${initial_state.current_price:.2f}")
        
        # Mock a dispatch action (charge battery slightly if solar exists)
        action = DispatchPlan(
            timestamp=initial_state.timestamp,
            battery_charge_mw=10.0 if initial_state.solar_mw > 0 else 0.0,
            peaker_mw=0.0,
            reasoning="Test solar step"
        )
        
        res = env.step(action)
        print(f"Step Result Cost: ${res.total_cost:,.2f}")
        print(f"Next State SoC: {res.next_state.battery_soc_mwh:.1f} MWh")
        
    except Exception as e:
        print(f"Env Test Error: {e}")
        import traceback
        traceback.print_exc()
