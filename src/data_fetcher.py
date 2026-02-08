import os
import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class NRELFetcher:
    """
    Fetcher for NREL NSRDB (National Solar Radiation Database) data.
    """
    BASE_URL = "https://developer.nrel.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    
    def __init__(self):
        self.api_key = os.getenv("NREL_API_KEY", "DEMO_KEY")
        self.email = os.getenv("NREL_EMAIL", "rakeshkrai@gmail.com") # Using a real-looking email
        self.cache_dir = Path("data/nsrdb_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_solar_data(self, lat: float, lon: float, year: int = 2020) -> pd.DataFrame:
        """
        Fetches solar data for a specific point and year.
        Caches the result to avoid redundant API calls.
        """
        cache_file = self.cache_dir / f"nsrdb_{lat}_{lon}_{year}.csv"
        
        if cache_file.exists():
            print(f"Loading cached NREL data from {cache_file}")
            return pd.read_csv(cache_file, skiprows=2)

        print(f"Fetching NREL data for {lat}, {lon} for year {year}...")
        
        params = {
            'api_key': self.api_key,
            'wkt': f'POINT({lon} {lat})',
            'attributes': 'ghi,dni,dhi,wind_speed',
            'names': str(year),
            'utc': 'true',
            'leap_day': 'true',
            'interval': '60',
            'email': self.email
        }
        
        response = requests.get(self.BASE_URL, params=params)
        
        if response.status_code != 200:
            print(f"Error fetching NREL data: {response.status_code}")
            print(response.text)
            return pd.DataFrame()

        # Save to cache
        cache_file.write_text(response.text)
        
        # NREL CSVs typically have 2 rows of metadata before headers
        return pd.read_csv(StringIO(response.text), skiprows=2)

if __name__ == "__main__":
    # Test with DEMO_KEY
    fetcher = NRELFetcher()
    # PJM area approx coordinates (Philadelphia)
    test_lat, test_lon = 39.9526, -75.1652
    df = fetcher.fetch_solar_data(test_lat, test_lon, 2020)
    
    if not df.empty:
        print("Successfully fetched NREL data:")
        print(df.head())
    else:
        print("Failed to fetch data. Check API key or limits.")
