import requests
from datetime import datetime
import os

# We will need to return the expected schema
from automated_grid_balancing.common.schemas import GridState

API_KEY = "Xx829MX7w87J0KKpWcO7"  # Hardcoded for now based on the screenshot/user test script
BASE_URL = "https://api.electricitymaps.com/v3"

def fetch_electricitymaps(zone="DE") -> dict:
    """
    Fetches the latest power breakdown, carbon intensity, and renewable percentage.
    """
    headers = {"auth-token": API_KEY}
    
    # We will fetch power breakdown, carbon intensity, and renewable percentage
    endpoints = {
        "power_breakdown": f"/power-breakdown/latest?zone={zone}",
        "carbon_intensity": f"/carbon-intensity/latest?zone={zone}",
        "renewable_energy": f"/renewable-energy/latest?zone={zone}"
    }
    
    results = {}
    for key, endpoint in endpoints.items():
        try:
            url = BASE_URL + endpoint
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                results[key] = resp.json()
            else:
                print(f"Failed to fetch {key}: {resp.status_code} - {resp.text}")
                results[key] = {}
        except Exception as e:
            print(f"Error fetching {key}: {e}")
            results[key] = {}
            
    return results

def convert_to_gridstate(api_data: dict, step_idx: int, zone: str = "DE") -> GridState:
    """
    Converts the API responses into the GridState schema.
    """
    # 1. Parse Power Breakdown
    power_data = api_data.get("power_breakdown", {})
    power_breakdown = power_data.get("powerProductionBreakdown", {})
    
    # Power Consumption (Total Demand)
    demand_mw = power_data.get("powerConsumptionTotal", 0)
    
    # Extract Production
    wind_mw = power_breakdown.get("wind", 0) or 0
    solar_mw = power_breakdown.get("solar", 0) or 0
    renewable_mw = wind_mw + solar_mw
    
    # Extract Carbon & Renewable info
    carbon_data = api_data.get("carbon_intensity", {})
    carbon_intensity = carbon_data.get("carbonIntensity", 0)
    
    renew_data = api_data.get("renewable_energy", {})
    renewable_percentage = renew_data.get("renewablePercentage", 0)
    
    # 2. Get Timestamp
    timestamp_str = power_data.get("datetime")
    if timestamp_str:
        # e.g., "2026-03-08T19:00:00.000Z"
        # We handle parsing roughly
        try:
            # Drop the Z and milliseconds if present for basic parsing
            ts_clean = timestamp_str.replace("Z", "").split(".")[0]
            timestamp = datetime.fromisoformat(ts_clean)
        except:
            timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcnow()
        
    # 3. Create GridState
    # Provide defaults for missing physical proxies if needed
    state = GridState(
        t=step_idx,
        timestamp=timestamp,
        region=zone,
        demand_mw=float(demand_mw),
        renewable_mw=float(renewable_mw),
        solar_mw=float(solar_mw),
        wind_mw=float(wind_mw),
        reserve_proxy=0.0,  # Will be calculated dynamically if needed
        freq_proxy=60.0,
        carbon_intensity=float(carbon_intensity) if carbon_intensity else None,
        renewable_percentage=float(renewable_percentage) if renewable_percentage else None
    )
    
    # Add simple Reserve and Freq Proxies
    capacity = state.demand_mw * 1.2
    net_load = state.demand_mw - state.renewable_mw
    state.reserve_proxy = max(0.0, capacity - net_load)
    
    return state

if __name__ == "__main__":
    # Test
    print("Fetching live data...")
    raw = fetch_electricitymaps()
    state = convert_to_gridstate(raw, 0)
    print(state.model_dump_json(indent=2))
