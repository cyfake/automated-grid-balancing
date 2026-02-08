from env import GridEnv
import pandas as pd

env = GridEnv()

print("Checking Solar Data...")
print(f"Fetcher Email: {env.fetcher.email}")
print(f"Data Source Empty? {env.real_solar_data.empty}")

if not env.real_solar_data.empty:
    print("\n--- Real Solar Data Head ---")
    print(env.real_solar_data.head())
    print("\n--- Real Solar Data Tail ---")
    print(env.real_solar_data.tail())
    
    # Check for non-zero values at night (should be 0)
    night_mask = (env.real_solar_data.index.hour < 5) | (env.real_solar_data.index.hour > 20)
    night_solar = env.real_solar_data[night_mask]
    print(f"\nNon-zero solar at night count: {(night_solar > 0).sum()}")
    print(f"Max night solar: {night_solar.max()}")
else:
    print("Real solar data is EMPTY. Falling back to synthetic.")

# Check correlation with demand for the first 100 steps
print("\n--- Correlation Check (First 100h) ---")
dates = env.demand_series.index[:100]
demands = env.demand_series.iloc[:100]
solars = []

for ts in dates:
    # Logic from env.py to get solar
    if not env.real_solar_data.empty:
        if ts in env.real_solar_data.index:
             val = env.real_solar_data.loc[ts]
        else:
             mask = (env.real_solar_data.index.month == ts.month) & \
                    (env.real_solar_data.index.day == ts.day) & \
                    (env.real_solar_data.index.hour == ts.hour)
             if mask.any():
                 val = env.real_solar_data[mask].iloc[0]
             else:
                 val = 0.0
        solars.append(val)
    else:
        solars.append(env._get_synthetic_solar(ts))

df_corr = pd.DataFrame({'demand': demands.values, 'solar': solars})
print(df_corr.head(24))
print(f"\nCorrelation: {df_corr['demand'].corr(df_corr['solar'])}")
