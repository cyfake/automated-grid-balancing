import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional
from agentfield import Agent, app
from automated_grid_balancing.common.schemas import DatasetConfig, ExogenousConfig, GridState
from automated_grid_balancing.common.utils import setup_logging
from automated_grid_balancing.src.utils.electricitymaps_adapter import fetch_electricitymaps, convert_to_gridstate

logger = setup_logging("telemetry_agent")

@app.agent
class TelemetryAgent(Agent):
    name = "telemetry_agent"
    description = "Ingests multi-stream grid data and produces canonical GridState"
    tags = ["telemetry", "gridstate", "ingestion"]

    @app.skill
    def load_pjm(self, dataset: DatasetConfig) -> str:
        """Parses raw PJM CSVs into a standardized parquet."""
        logger.info(f"Loading PJM data from {dataset.pjm_dir}")
        path = Path(dataset.pjm_dir)
        files = list(path.glob(dataset.pjm_pattern))
        if not files:
            raise FileNotFoundError(f"No files found matching {dataset.pjm_pattern} in {dataset.pjm_dir}")
        print(f"DEBUG: Found files: {files}")
        
        dfs = []
        for f in files:
            try:
                # Assuming standard PJM hourly format: datetime_beginning_utc, load_mw, etc.
                # Adjust column names as needed based on actual file inspection
                df = pd.read_csv(f)
                # Normalize columns
                df.columns = [c.lower() for c in df.columns]
                print(f"DEBUG: Columns for {f}: {df.columns}")
                
                # Check for pjm_hourly_est.csv format: 'Datetime', 'PJM_Load' (or region columns)
                if 'datetime' in df.columns:
                     dt_col = 'datetime'
                     # Logic to pick a load column. If 'pjm_load' exists use it, else try AEP, COMED etc
                     # For now, default to 'pjm_load' if present, else 'aep'
                     if 'pjm_load' in df.columns:
                         load_col = 'pjm_load'
                     elif 'aep' in df.columns:
                         load_col = 'aep'
                     elif 'load_mw' in df.columns:
                         load_col = 'load_mw'
                     else:
                         # Fallback: take the second column if it looks numeric?
                         # Let's just stick to known columns for safety
                         load_col = None

                # Fallback for eia_hourly.csv which has 'hour' but no datetime
                if not dt_col and 'hour' in df.columns:
                    # Synthetic start date
                    start_date = pd.Timestamp("2024-01-01")
                    df['datetime'] = start_date + pd.to_timedelta(df['hour'], unit='H')
                    dt_col = 'datetime'
                    load_col = 'load_mw' # eia_hourly has this

                if dt_col and load_col:
                    df['datetime'] = pd.to_datetime(df[dt_col])
                    df = df.set_index('datetime')
                    df = df.rename(columns={load_col: 'load_mw'})
                    
                    # Capture Solar/Wind if present (e.g. from eia_hourly)
                    # Capture Solar/Wind if present (e.g. from eia_hourly)
                    if 'solar_mw' in df.columns and 'wind_mw' in df.columns:
                        df['renewable_mw'] = df['solar_mw'] + df['wind_mw']
                    
                    cols_to_keep = ['load_mw']
                    if 'renewable_mw' in df.columns:
                        cols_to_keep.append('renewable_mw')
                    if 'solar_mw' in df.columns:
                        cols_to_keep.append('solar_mw')
                    if 'wind_mw' in df.columns:
                        cols_to_keep.append('wind_mw')
                    dfs.append(df[cols_to_keep])
            except Exception as e:
                logger.warning(f"Failed to parse {f}: {e}")
        
        if not dfs:
             raise ValueError("No valid data parsed from PJM files")
             
        full_df = pd.concat(dfs).sort_index()
        # Handle duplicates (DST)
        full_df = full_df.groupby(level=0).mean()
        # Resample hourly to ensure continuity
        full_df = full_df.resample('H').mean().interpolate()
        
        out_path = path / "pjm_standardized.parquet"
        full_df.to_parquet(out_path)
        return str(out_path)

    @app.skill
    def load_eia_fuelmix(self, exogenous: ExogenousConfig) -> Optional[str]:
        """Optional: Loads EIA fuel mix data."""
        if not exogenous.eia_fuelmix_csv:
            return None
        # Placeholder for actual logic
        return exogenous.eia_fuelmix_csv

    @app.skill
    def load_noaa_isdlite(self, exogenous: ExogenousConfig) -> Optional[str]:
        """Optional: Loads NOAA weather data."""
        if not exogenous.noaa_isdlite_dir:
            return None
        # Placeholder
        return exogenous.noaa_isdlite_dir

    @app.skill
    def build_gridstate_stream(self, pjm_path: str, eia_path: Optional[str], noaa_path: Optional[str]) -> str:
        """Merges streams into canonical GridState CSV."""
        logger.info("Building canonical GridState stream...")
        df_pjm = pd.read_parquet(pjm_path)
        
        # Merge Logic (Simplified for minimal viable agent)
        # In a real system, we'd join eia/noaa on index
        
        if 'renewable_mw' not in df_pjm.columns:
            logger.info("Generating synthetic renewable profile...")
            hours = df_pjm.index.hour
            # Solar peak at noon, zero at night
            solar_profile = np.maximum(0, -np.cos((hours / 24) * 2 * np.pi) * 1000)
            # Random wind
            wind_profile = np.random.normal(500, 100, len(df_pjm))
            
            df_pjm['solar_mw'] = solar_profile
            df_pjm['wind_mw'] = np.abs(wind_profile)
            df_pjm['renewable_mw'] = df_pjm['solar_mw'] + df_pjm['wind_mw']
        else:
             logger.info("Using existing renewable data from source.")
             # Ensure solar/wind columns exist if we used existing data
             if 'solar_mw' not in df_pjm.columns:
                 df_pjm['solar_mw'] = df_pjm['renewable_mw'] * 0.4 # Rough split guess
             if 'wind_mw' not in df_pjm.columns:
                 df_pjm['wind_mw'] = df_pjm['renewable_mw'] * 0.6
            
        # Add Proxy Columns
        df_pjm['wind_ms'] = 5.0 # default
        df_pjm['temp_c'] = 20.0 # default
        df_pjm['reserve_proxy'] = 0.0 # placeholder, calculated dynamically? Or static?
        # Actually GridState schema has reserve_proxy. We can calc a static margin here
        # Net Load = Load - Renewables. 
        # Capacity (Simulated) = Load * 1.2
        # Reserve = Capacity - Net Load
        capacity = df_pjm['load_mw'].max() * 1.2
        df_pjm['reserve_proxy'] = capacity - (df_pjm['load_mw'] - df_pjm['renewable_mw'])
        
        # Freq Proxy: 60 - k * (Load - Supply). But Supply matches Load ideal.
        # Let's say Freq deviates based on rate of change of Net Load (Ramp stress)
        net_load = df_pjm['load_mw'] - df_pjm['renewable_mw']
        ramp = net_load.diff().fillna(0)
        df_pjm['freq_proxy'] = 60.0 - (ramp * 0.0001)

        # Output
        # Ensure index is named timestamp for Orchestrator
        df_pjm.index.name = 'timestamp'
        
        out_path = Path(pjm_path).parent / "gridstate_stream.csv"
        df_pjm.to_csv(out_path)
        return str(out_path)

    @app.skill
    def fetch_live_gridstate(self, step_idx: int, zone: str = "DE") -> GridState:
        """Fetches live real-time data from Electricity Maps API and returns a canonical GridState."""
        logger.info(f"Fetching live grid state for zone: {zone} (Step {step_idx})")
        try:
            raw_data = fetch_electricitymaps(zone=zone)
            state = convert_to_gridstate(raw_data, step_idx=step_idx, zone=zone)
            return state
        except Exception as e:
            logger.error(f"Failed to fetch live grid state: {e}")
            # Fallback to an empty/fake state if API completely fails to ensure loop continues
            return GridState(
                t=step_idx,
                timestamp=pd.Timestamp.utcnow(),
                region=zone,
                demand_mw=1000.0,
                renewable_mw=0.0,
                solar_mw=0.0,
                wind_mw=0.0,
                reserve_proxy=0.0,
                freq_proxy=60.0
            )
