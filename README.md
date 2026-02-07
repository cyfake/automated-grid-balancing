# Grid Load-Balancing Agent — MVP

Autonomous 24-hour grid dispatch optimizer for 3 US states (CA, TX, NY) with battery storage, inter-state transfers, and fuel fallback. Built on Agentfield. Uses real hourly data from the U.S. Energy Information Administration (EIA).

## What it does

Given hourly state-level data (load, solar, wind, fuel capacity, battery specs), the system:

1. **Balances** supply and demand each hour using a greedy heuristic with 24h lookahead
2. **Minimizes** unserved energy (huge penalty), fuel usage, and curtailment
3. **Optimizes** battery dispatch with SoC target curves that reserve capacity for evening peaks
4. **Transfers** power between states via fuel-backed inter-state links
5. **Recommends** infrastructure upgrades via counterfactual what-if simulations
6. **Reports** structured logs, KPIs, and a markdown summary with data provenance

## Data source

All generation and demand data comes from the **EIA Open Data API** (Form EIA-930, Hourly Electric Grid Monitor):

- **Fuel-type generation**: `/v2/electricity/rto/fuel-type-data/data` — hourly MW by fuel for each ISO
- **Demand**: `/v2/electricity/rto/region-data/data` — hourly demand (type "D") per ISO
- **ISOs**: CISO (California), ERCO (Texas), NYIS (New York)

The pipeline fetches the most recent 48-hour window (with a 6-hour reporting lag) and writes a canonical CSV to `data/processed/eia_hourly.csv`. On subsequent runs, the local CSV is reused unless deleted.

**Fields not available from EIA** (documented assumptions):
- **Battery specs**: Static per-state estimates (CA: 4 GW / 16 GWh, TX: 3 GW / 12 GWh, NY: 2 GW / 8 GWh) based on DOE and CAISO interconnection queue data (2024)
- **Fuel capacity**: Derived as peak observed dispatchable generation + 15% headroom

A provenance sidecar (`eia_hourly.provenance.json`) is written alongside the CSV with full metadata.

## Setup

```bash
cd grid-balance-agent
cp .env.example .env
pip install -r requirements.txt
```

Optional: set your EIA API key in `.env` for higher rate limits:
```bash
EIA_API_KEY=your-key-here
```
Register for a free key at https://www.eia.gov/opendata/register.php. Without it, the pipeline uses `DEMO_KEY` (30 requests/hour limit).

## Run the MVP (standalone)

```bash
python runs/run_mvp.py
```

On first run (or when `data/processed/eia_hourly.csv` is absent), the pipeline fetches fresh data from EIA. Subsequent runs reuse the cached CSV.

Options:
```bash
python runs/run_mvp.py --start-hour 0 --horizon 24
python runs/run_mvp.py --data-dir path/to/processed/  # custom data directory
python runs/run_mvp.py --enable-llm                    # requires GEMINI_API_KEY in .env
```

To force a refresh of EIA data:
```bash
rm data/processed/eia_hourly.csv
python runs/run_mvp.py
```

## Run via Agentfield

Start the Agentfield server, then start the node:

```bash
# Terminal 1: Agentfield server (if not already running)
# (follow Agentfield docs)

# Terminal 2: Start the grid balance agent node
python main.py
```

### Trigger the pipeline

```bash
curl -X POST http://localhost:8080/api/v1/execute/grid-balance-agent.grid_run_grid_mvp \
  -H "Content-Type: application/json" \
  -d '{"input": {"start_hour": 0, "horizon": 24, "enable_llm": false}}'
```

### Get an explanation (optional, LLM-powered)

```bash
# First set ENABLE_LLM_SUMMARY=true in .env and restart the node
curl -X POST http://localhost:8080/api/v1/execute/grid-balance-agent.grid_explain_run \
  -H "Content-Type: application/json" \
  -d '{"input": {}}'
```

## Output artifacts

After running, these files are produced:

| File | Description |
|------|-------------|
| `data/processed/eia_hourly.csv` | Canonical processed data (cached from EIA) |
| `data/processed/eia_hourly.provenance.json` | Data provenance metadata (source, period, assumptions) |
| `logs/decisions.jsonl` | Per-hour dispatch decisions (battery, transfers, fuel, curtailment) |
| `logs/kpis.json` | Aggregate KPIs (unserved energy, fuel, renewable utilization, etc.) |
| `logs/recommendations.json` | Ranked infrastructure upgrade recommendations with KPI deltas |
| `reports/summary.md` | Human-readable markdown report with data source and provenance |

## Architecture

```
run_mvp.py / Agentfield reasoner
  └─ orchestrator
       ├─ ingestion_agent      → loads EIA data (cached CSV or API fetch)
       ├─ state_builder_agent  → builds per-state hourly series
       ├─ transfer_agent       → defines 3-state topology + capacities
       ├─ forecast_agent       → 24h forecast (perfect foresight for MVP)
       ├─ policy_agent         → penalty weights + constraints
       ├─ planner_agent        → greedy dispatch with SoC target curves
       ├─ simulation_agent     → KPI computation
       ├─ stress_agent         → identifies critical hours
       ├─ recommendation_agent → counterfactual what-if analysis
       └─ audit_agent          → writes all output files + provenance
```

## Planner design

The planner is fully deterministic (no LLM). Per hour it:

1. Computes net position (renewable - load) per state
2. Dispatches batteries using SoC-aware lookahead targets
3. Transfers power from surplus to deficit states
4. Dispatches fuel for remaining deficits
5. Runs fuel-backed transfers (states with spare fuel capacity export to states that hit their cap)
6. Records any unserved energy or curtailment

The SoC target curve reserves battery capacity for:
- Future high-scarcity hours (proportional to remaining deficit)
- Evening peak hours (17:00-21:00) with a 40% SoC floor

## Demo script (for judges)

1. **Show data source**: `cat data/processed/eia_hourly.provenance.json` — real EIA data with provenance
2. **Run**: `python runs/run_mvp.py` — completes in <1s (with cached data)
3. **Show KPIs**: `cat logs/kpis.json` — renewable utilization, unserved energy, fuel
4. **Show recommendations**: `cat logs/recommendations.json` — infrastructure upgrades with KPI deltas
5. **Show report**: `cat reports/summary.md` — full narrative with data source, trade-offs, causal chains
6. **Agentfield**: trigger via curl, show the node in Agentfield UI
7. **Why Agentfield**: the node exposes the pipeline as composable reasoners that other agents can call, enabling multi-agent grid coordination
