import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agentfield import app
from automated_grid_balancing.agents.orchestrator_agent import OrchestratorAgent
from automated_grid_balancing.agents.telemetry_agent import TelemetryAgent
from automated_grid_balancing.agents.forecast_agent import ForecastAgent
from automated_grid_balancing.agents.policy_agent import PolicyAgent
from automated_grid_balancing.agents.planner_agent import PlannerAgent
from automated_grid_balancing.agents.verifier_agent import VerifierAgent
from automated_grid_balancing.common.schemas import DatasetConfig, RunRequest, ExogenousConfig

def debug_run():
    print("Starting debug run...")
    
    # 1. Setup Orchestrator
    orchestrator = OrchestratorAgent()
    
    # 2. Prepare Run
    data_dir = os.path.abspath("data")
    dataset = DatasetConfig(pjm_dir=data_dir, pjm_pattern="eia_hourly.csv", region="Texas")
    req = RunRequest(dataset=dataset, horizon_steps=6, n_steps=24)
    
    print(f"Preparing run for {req.dataset.pjm_dir}...")
    try:
        context = orchestrator.prepare_run(req)
        print("Prepare run successful.")
        print(f"Data length in context: {len(context['df_stream'])}")
        print(f"Grid path in context: {context['grid_path']}")
    except Exception as e:
        print(f"Error in prepare_run: {e}")
        return

    # 3. Step Loop
    steps = min(req.n_steps, len(context['df_stream']))
    print(f"Will run {steps} steps.")
    
    for t in range(steps):
        print(f"--- Step {t} ---")
        try:
            result = orchestrator.run_step(context, t)
            print(f"Step {t} success. Cost: {result['log'].cost:.2f}")
        except Exception as e:
            print(f"ERROR at Step {t}: {e}")
            import traceback
            traceback.print_exc()
            break
            
    print("Debug run complete.")

if __name__ == "__main__":
    debug_run()
