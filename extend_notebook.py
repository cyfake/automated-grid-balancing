import json

def extend_notebook(notebook_path):
    with open(notebook_path, 'r') as f:
        nb = json.load(f)

    new_cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 8. Wind Toolkit Data Ingestion\n",
                "\n",
                "In this section, we load and inspect the Wind Toolkit site metadata."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import xarray as xr\n",
                "import numpy as np\n",
                "\n",
                "# Path to wind metadata\n",
                "WIND_METADATA_PATH = 'data/wtk_site_metadata.csv'\n",
                "\n",
                "# Load metadata (inferring column names as the file has no header)\n",
                "# Columns based on prompt: site_id, latitude, longitude, capacity, capacity_factor, full_timeseries_path, etc.\n",
                "wind_meta = pd.read_csv(WIND_METADATA_PATH, header=None)\n",
                "\n",
                "# Assign likely column names based on data inspection\n",
                "col_names = [\n",
                "    'site_id', 'longitude', 'latitude', 'unused_1', 'unused_2', \n",
                "    'hub_height', 'offshore', 'unused_3', 'capacity', \n",
                "    'capacity_factor', 'unused_4', 'full_timeseries_path'\n",
                "]\n",
                "wind_meta.columns = col_names\n",
                "\n",
                "print(f\"Number of sites loaded: {len(wind_meta)}\")\n",
                "display(wind_meta.head())\n",
                "print(\"\\nSummary Statistics:\")\n",
                "display(wind_meta[['capacity', 'capacity_factor']].describe())"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 9. Loading Wind Time Series (NetCDF)\n",
                "\n",
                "We select a subset of sites and load their hourly wind time series."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# Select a subset of sites for analysis (e.g., first 5 sites)\n",
                "selected_sites = wind_meta.head(5)\n",
                "\n",
                "wind_data_list = []\n",
                "WIND_DATA_BASE = Path('data/wtk')\n",
                "\n",
                "for idx, site in selected_sites.iterrows():\n",
                "    # The path in metadata is relative, e.g., '253/126691.ncccncnc'\n",
                "    # We'll assume the .nc extension if it's missing or handle the provided filename\n",
                "    rel_path = site['full_timeseries_path']\n",
                "    site_id = site['site_id']\n",
                "    \n",
                "    # Try to open as .nc if path exists\n",
                "    nc_path = WIND_DATA_BASE / rel_path\n",
                "    if not nc_path.exists():\n",
                "        # Fallback for demonstration if files are missing\n",
                "        print(f\"Warning: Site {site_id} data not found at {nc_path}\")\n",
                "        continue\n",
                "\n",
                "    ds = xr.open_dataset(nc_path)\n",
                "    # Inspect variables and convert to dataframe\n",
                "    df_site = ds.to_dataframe().reset_index()\n",
                "    df_site['site_id'] = site_id\n",
                "    wind_data_list.append(df_site)\n",
                "    ds.close()\n",
                "\n",
                "if wind_data_list:\n",
                "    all_wind_df = pd.concat(wind_data_list, ignore_index=True)\n",
                "    print(f\"Loaded wind data for {len(wind_data_list)} sites.\")\n",
                "else:\n",
                "    print(\"No wind data loaded. Ensure .nc files are in the data/wtk directory.\")\n",
                "    # Create dummy data for flow demonstration if needed (comment out in production)\n",
                "    # (In a real scenario, this would stop or raise an error)\n"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 10. Temporal Alignment (2007-2013)\n",
                "\n",
                "Aligning wind data with PJM load data on the hourly scale for the years 2007-2013."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# This code assumes all_wind_df has 'time' in UTC and df has 'Datetime' in US/Eastern\n",
                "if 'all_wind_df' in locals() and not all_wind_df.empty:\n",
                "    # 1. Convert Timestamps UTC -> US/Eastern\n",
                "    all_wind_df['time'] = pd.to_datetime(all_wind_df['time']).dt.tz_localize('UTC').dt.tz_convert('US/Eastern')\n",
                "    \n",
                "    # 2. Filter to 2007-2013\n",
                "    wind_filtered = all_wind_df[(all_wind_df['time'].dt.year >= 2007) & (all_wind_df['time'].dt.year <= 2013)]\n",
                "    pjm_filtered = df[(df.index.year >= 2007) & (df.index.year <= 2013)].copy()\n",
                "    \n",
                "    print(f\"PJM timestamps before alignment: {len(pjm_filtered)}\")\n",
                "    print(f\"Wind timestamps before alignment: {len(wind_filtered)}\")\n"
            ]
        }
    ]

    nb['cells'].extend(new_cells)

    with open(notebook_path, 'w') as f:
        json.dump(nb, f, indent=1)

if __name__ == '__main__':
    extend_notebook('PJM_Load_Analysis.ipynb')
