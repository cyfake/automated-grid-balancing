import json
from pathlib import Path

def update_notebook(notebook_path):
    with open(notebook_path, 'r') as f:
        full_nb = json.load(f)

    # 1. Remove wind-related cells
    # We look for keywords: 'Wind Toolkit', 'wtk_site_metadata', 'all_wind_df'
    wind_keywords = ['Wind Toolkit', 'wtk_site_metadata', 'all_wind_df']
    filtered_cells = []
    for cell in full_nb.get('cells', []):
        source_text = ''.join(cell.get('source', []))
        if any(kw in source_text for kw in wind_keywords):
            continue
        filtered_cells.append(cell)
    
    full_nb['cells'] = filtered_cells

    # 2. Define the new preprocessing cells with fixed imputation
    new_cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Preprocessing: canonical hourly PJM load dataset\n",
                "\n",
                "This section implements a robust preprocessing pipeline to create a canonical dataset for modeling. \n",
                "\n",
                "**Pipeline Stages:**\n",
                "1. **Sorting**: Ensure strict temporal ordering.\n",
                "2. **Duplicate Resolution**: Handle DST fall-back duplicates via aggregation.\n",
                "3. **Reindexing**: Complete the hourly timeline and detect gaps.\n",
                "4. **Imputation**: Fill missing hours (e.g., DST spring-forward) using time-based interpolation and catch-all fill logic.\n",
                "5. **Feature Engineering**: Add time-based features and convert units.\n",
                "6. **Scaling**: Region-wise MinMax scaling."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import numpy as np\n",
                "from sklearn.preprocessing import MinMaxScaler\n",
                "from pathlib import Path\n",
                "\n",
                "# Constants\n",
                "OUT_DIR = Path('output')\n",
                "OUT_DIR.mkdir(exist_ok=True)\n",
                "FREQ = 'h'\n",
                "\n",
                "def fit_minmax(train_series):\n",
                "    \"\"\"Fits a MinMaxScaler to the series and returns parameters.\"\"\"\n",
                "    scaler = MinMaxScaler()\n",
                "    scaler.fit(train_series.values.reshape(-1, 1))\n",
                "    return scaler\n",
                "\n",
                "def transform_minmax(series, scaler):\n",
                "    \"\"\"Applies a fitted scaler to a series.\"\"\"\n",
                "    return scaler.transform(series.values.reshape(-1, 1)).flatten()\n",
                "\n",
                "print(\"Preprocessing utilities initialized.\")"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 2) Sort correctly and validate ordering"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# MELT the dataframe into long format for easier per-region processing\n",
                "df_long = df.reset_index().melt(id_vars='Datetime', var_name='region', value_name='load_mw')\n",
                "df_long = df_long.rename(columns={'Datetime': 'datetime'})\n",
                "\n",
                "# Sort and reset index\n",
                "df_long = df_long.sort_values(['region', 'datetime']).reset_index(drop=True)\n",
                "print(f\"Long-format dataset created. Shape: {df_long.shape}\")\n",
                "display(df_long.head())"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 3) Fix duplicates (especially DST fall-back duplicates)"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "dup_report = []\n",
                "\n",
                "def resolve_duplicates(group):\n",
                "    region = group.name\n",
                "    dup_mask = group.duplicated('datetime', keep=False)\n",
                "    if dup_mask.any():\n",
                "        dups = group[dup_mask]\n",
                "        for dt, sub_group in dups.groupby('datetime'):\n",
                "            dup_report.append({\n",
                "                'region': region, \n",
                "                'duplicate_datetime': dt, \n",
                "                'count': len(sub_group), \n",
                "                'mean_value': sub_group['load_mw'].mean()\n",
                "            })\n",
                "        agg_group = group.groupby('datetime', as_index=False).agg({'load_mw': 'mean'})\n",
                "        agg_group['region'] = region\n",
                "        return agg_group\n",
                "    return group\n",
                "\n",
                "df_dedup = df_long.groupby('region', group_keys=False).apply(resolve_duplicates)\n",
                "df_dedup_report = pd.DataFrame(dup_report)\n",
                "\n",
                "print(f'Resolved {len(df_dedup_report)} unique duplicate timestamps.')"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 4) Reindex to complete hourly timeline"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "reindexed_list = []\n",
                "missing_report = []\n",
                "\n",
                "for region, group in df_dedup.groupby('region'):\n",
                "    group = group.set_index('datetime')\n",
                "    full_index = pd.date_range(start=group.index.min(), end=group.index.max(), freq=FREQ)\n",
                "    reindexed = group.reindex(full_index)\n",
                "    \n",
                "    missing_mask = reindexed['load_mw'].isna()\n",
                "    if missing_mask.any():\n",
                "        missing_pts = reindexed[missing_mask].index\n",
                "        for dt in missing_pts:\n",
                "            missing_report.append({'region': region, 'missing_datetime': dt})\n",
                "            \n",
                "    reindexed = reindexed.reset_index().rename(columns={'index': 'datetime'})\n",
                "    reindexed['region'] = region\n",
                "    reindexed_list.append(reindexed)\n",
                "\n",
                "df_reindexed = pd.concat(reindexed_list, ignore_index=True)\n",
                "print(f'Detected {len(missing_report)} missing hourly timestamps.')"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 5) Impute missing timestamps safely\n",
                "\n",
                "We fill gaps using `time` interpolation with `limit_direction='both'` and a final `.ffill().bfill()` to ensure zero NaNs."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "fill_report = []\n",
                "IMPUTE_METHOD = 'time'\n",
                "\n",
                "def impute_gaps(group):\n",
                "    region = group.name\n",
                "    group = group.set_index('datetime')\n",
                "    missing_mask = group['load_mw'].isna()\n",
                "    \n",
                "    if missing_mask.any():\n",
                "        if IMPUTE_METHOD == 'time':\n",
                "            group['load_mw'] = group['load_mw'].interpolate(method='time', limit_direction='both')\n",
                "        else:\n",
                "            group['load_mw'] = (group['load_mw'].shift(1) + group['load_mw'].shift(-1)) / 2.0\n",
                "        \n",
                "        # Safety catch-all for remaining NaNs (e.g. at the start or end of the series)\n",
                "        group['load_mw'] = group['load_mw'].ffill().bfill()\n",
                "    return group.reset_index()\n",
                "\n",
                "df_canonical = df_reindexed.groupby('region', group_keys=False).apply(impute_gaps)\n",
                "print(f'Imputation completed. NaNs remaining: {df_canonical[\"load_mw\"].isna().sum()}')\n",
                "assert df_canonical['load_mw'].isna().sum() == 0, 'There are still NaNs in the load_mw column!'"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 6) Add derived time features & Clarify units"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "df_canonical['hour'] = df_canonical['datetime'].dt.hour\n",
                "df_canonical['dayofweek'] = df_canonical['datetime'].dt.dayofweek\n",
                "df_canonical['month'] = df_canonical['datetime'].dt.month\n",
                "df_canonical['year'] = df_canonical['datetime'].dt.year\n",
                "df_canonical['is_weekend'] = df_canonical['dayofweek'].isin([5, 6]).astype(int)\n",
                "df_canonical['energy_mwh'] = df_canonical['load_mw'] * 1.0\n",
                "print('Features added and units clarified.')\n",
                "display(df_canonical.head())"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 8) Scaling for model training"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "scaled_dfs = []\n",
                "for region, group in df_canonical.groupby('region'):\n",
                "    scaler = fit_minmax(group['load_mw'])\n",
                "    group['load_mw_scaled'] = transform_minmax(group['load_mw'], scaler)\n",
                "    scaled_dfs.append(group)\n",
                "\n",
                "df_canonical = pd.concat(scaled_dfs, ignore_index=True)\n",
                "print('MinMax scaling applied per region.')"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 9) Output canonical dataset(s)"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "df_canonical_wide = df_canonical.pivot(index='datetime', columns='region', values='load_mw')\n",
                "df_canonical.to_csv(OUT_DIR / 'pjm_canonical_long.csv', index=False)\n",
                "df_canonical_wide.to_csv(OUT_DIR / 'pjm_canonical_wide.csv')\n",
                "print(f'Datasets saved to {OUT_DIR}/')"
            ]
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "### 10) Quick plots for verification"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "sample_region = sorted(df_canonical['region'].unique())[0]\n",
                "subset = df_canonical[df_canonical['region'] == sample_region]\n",
                "plt.figure(figsize=(15, 6))\n",
                "plt.plot(subset['datetime'], subset['load_mw'], label=f'{sample_region} Canonical')\n",
                "plt.title(f'Canonical Load Series: {sample_region}')\n",
                "plt.xlabel('Datetime')\n",
                "plt.ylabel('MW')\n",
                "plt.legend()\n",
                "plt.show()"
            ]
        }
    ]

    # Find where to append/re-inject: 
    # We remove any previous attempt at "Preprocessing: ..." first
    final_cells = []
    in_target_section = False
    for cell in full_nb['cells']:
        src = ''.join(cell.get('source', []))
        if '# Preprocessing: canonical hourly PJM load dataset' in src:
            in_target_section = True
            continue
        # If we encounter the NEXT main section header (e.g. ## alignment), we stop skipping.
        # But we've already deleted wind code, so let's just append the new section after the last surviving cell 
        # before any potential wind-related cells were there.
        # Simplest: find the cell containing 'Detected load columns' and place after it.
        final_cells.append(cell)

    # Actually, let's just find the cell and replace the WHOLE section if it was already there
    # or append if not.
    
    # Re-filtering logic:
    cleaned_cells = []
    in_prep_block = False
    for cell in full_nb['cells']:
        src = ''.join(cell.get('source', []))
        if '# Preprocessing: canonical hourly PJM load dataset' in src:
            in_prep_block = True
            continue
        if in_prep_block:
            # Skip cells until we find something that ISN'T usually in our prep block
            # (our prep block usually ends with plots)
            if '### 10)' in src or 'Quick plots for verification' in src:
                # This is the last cell of the block, still skip it, then end block
                continue
            # If we see common next headers, we exit block
            if '## 7. Visualization' in src:
                in_prep_block = False
        
        if not in_prep_block:
            cleaned_cells.append(cell)
    
    # Now find the place to insert (usually after Data Quality Report or Initial Visualization)
    # Let's insert after 'Duplicate rows:' cell (Data Quality Report)
    insert_idx = len(cleaned_cells)
    for i, cell in enumerate(cleaned_cells):
        src = ''.join(cell.get('source', []))
        if 'print(f"Missing values' in src:
            insert_idx = i + 1
            break
            
    final_nb_cells = cleaned_cells[:insert_idx] + new_cells + cleaned_cells[insert_idx:]
    full_nb['cells'] = final_nb_cells

    with open(notebook_path, 'w') as f:
        json.dump(full_nb, f, indent=1)

if __name__ == '__main__':
    update_notebook('PJM_Load_Analysis.ipynb')
