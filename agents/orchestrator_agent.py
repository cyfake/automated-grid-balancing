import pandas as pd
import json
from datetime import datetime
from pathlib import Path
from agentfield import Agent, app
from automated_grid_balancing.common.schemas import RunRequest, RunResult, GridState
from automated_grid_balancing.common.utils import setup_logging, ensure_dir

logger = setup_logging("orchestrator")

@app.agent
class OrchestratorAgent(Agent):
    name = "orchestrator_agent"
    description = "Coordinates the autonomous grid balancing loop"
    tags = ["orchestrator"]
    
    @app.skill
    def ping(self) -> dict:
        return {"ok": True}

    @app.reasoner
    def prepare_run(self, req: RunRequest) -> dict:
        """Initializes data and policy for a run."""
        logger.info(f"Preparing run for {req.dataset.pjm_dir}")
        
        # 1. Initialize Telemetry
        grid_path = app.call("telemetry_agent", "build_gridstate_stream", 
                             pjm_path=app.call("telemetry_agent", "load_pjm", dataset=req.dataset),
                             eia_path=app.call("telemetry_agent", "load_eia_fuelmix", exogenous=req.exogenous),
                             noaa_path=app.call("telemetry_agent", "load_noaa_isdlite", exogenous=req.exogenous))
        
        # Load Stream
        df_stream = pd.read_csv(grid_path)
        df_stream['timestamp'] = pd.to_datetime(df_stream['timestamp'])
        
        # 2. Load Policy
        agent_dir = Path(__file__).parent
        pkg_root = agent_dir.parent
        policy_path = pkg_root / "configs" / "policy.yaml"
        cost_path = pkg_root / "configs" / "cost.yaml"
        
        policy, cost_weights = app.call("policy_agent", "load_policy", 
                                       policy_path=str(policy_path),
                                       cost_path=str(cost_path))
        
        # Initial State
        current_row = df_stream.iloc[0]
        state = GridState(
            t=0,
            timestamp=current_row['timestamp'],
            region=req.dataset.region or "Unknown",
            demand_mw=current_row['load_mw'],
            renewable_mw=current_row['renewable_mw'],
            solar_mw=current_row.get('solar_mw', 0.0),
            wind_mw=current_row.get('wind_mw', 0.0),
            wind_ms=current_row.get('wind_ms'),
            temp_c=current_row.get('temp_c'),
            reserve_proxy=current_row.get('reserve_proxy', 0.0),
            freq_proxy=60.0 
        )
        
        return {
            "grid_path": grid_path,
            "df_stream": df_stream,
            "policy": policy,
            "cost_weights": cost_weights,
            "state": state,
            "logs": [],
            "total_violations": 0,
            "total_cost": 0.0,
            "horizon_steps": req.horizon_steps
        }

    @app.reasoner
    def run_step(self, context: dict, step_idx: int) -> dict:
        """Executes a single step of the loop."""
        state = context['state']
        grid_path = context['grid_path']
        horizon_steps = context['horizon_steps']
        policy = context['policy']
        cost_weights = context['cost_weights']
        
        logger.info(f"Step {step_idx}: Processing...")
        
        # Forecast
        forecast = app.call("forecast_agent", "forecast", 
                            state=state, horizon_steps=horizon_steps)
        
        # Plan
        action = app.call("planner_agent", "plan", state=state, forecast=forecast, policy=policy)
        
        # Verify & Audit
        next_state_sim, log = app.call("verifier_agent", "verify_and_audit", 
                                       step=step_idx, prev_state=state, action=action, 
                                       policy=policy, cost_weights=cost_weights)
        
        # Update State for next loop
        # Instead of moving to next row in stream, we poll live data
        try:
            next_state_live = app.call("telemetry_agent", "fetch_live_gridstate", step_idx=step_idx+1, zone=state.region)
            # We preserve the reserve/freq physical sim outputs onto the fetched state
            next_state_live.reserve_proxy = next_state_sim.reserve_proxy
            next_state_live.freq_proxy = next_state_sim.freq_proxy
            next_state = next_state_live
        except Exception as e:
            logger.error(f"Failed to fetch next state, repeating simulation state: {e}")
            next_state = next_state_sim
            
        context['state'] = next_state
        context['logs'].append(log)
        context['total_violations'] += len(log.violations)
        context['total_cost'] += log.cost
        
        return {
            "state": next_state,
            "log": log,
            "action": action
        }

    @app.reasoner
    def plan_run(self, req: RunRequest) -> RunResult:
        context = self.prepare_run(req)
        # For programmatic planned runs, we just execute n_steps
        steps_to_run = req.n_steps
        
        for t in range(steps_to_run):
            self.run_step(context, t)
            
        # 5. Save Artifacts
        run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        out_dir = ensure_dir(f"automated_grid_balancing/artifacts/{run_id}")
        
        # Audits
        audit_path = f"{out_dir}/audits.json"
        with open(audit_path, 'w') as f:
            f.write(json.dumps([l.model_dump(mode='json') for l in context['logs']], indent=2))
            
        summary = {
            "steps": steps_to_run,
            "total_cost": context['total_cost'],
            "violations": context['total_violations']
        }
        
        return RunResult(
            artifacts={"audits": audit_path, "gridstate": context['grid_path']},
            summary=summary,
            violations_count=context['total_violations']
        )
