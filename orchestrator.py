from env import GridEnv
from agents.telemetry import TelemetryAgent
from agents.forecast import ForecastAgent
from agents.policy import PolicyAgent
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.verifier import VerifierAgent
from schemas import AuditLog
from typing import List

class GridOrchestrator:
    """
    Main Orchestrator that runs the Agentic Loop.
    """
    def __init__(self):
        self.env = GridEnv()
        self.telemetry = TelemetryAgent()
        self.forecast = ForecastAgent()
        self.policy = PolicyAgent()
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.verifier = VerifierAgent()
        
        self.history: List[AuditLog] = []

    def run_step(self):
        """Executes one full loop of the agentic grid management."""
        # 1. Sense
        state = self.telemetry.fetch_state(self.env)
        
        # 2. Predict
        forecast = self.forecast.generate_forecast(self.env)
        
        # 3. Govern
        policy = self.policy.get_policy()
        
        # 4. Plan
        plan = self.planner.create_plan(state, forecast, policy)
        
        # 5. Act (Agent)
        result = self.executor.execute_plan(self.env, plan)
        
        # 5b. Baseline (No Battery, Gas = Net Demand)
        # Calculate what would happen if we just used gas for everything
        baseline_net_demand = state.demand_mw - (state.solar_mw + state.wind_mw)
        baseline_cost = baseline_net_demand * state.current_price
        # Tie-break: if prices are negative, cost is negative (generators pay to produce) 
        # but typically baseline cost is just meeting demand at current price
        
        # 6. Verify
        # Store baseline in the result object
        result.baseline_cost = baseline_cost
        
        log = self.verifier.verify_step(result)
        self.history.append(log)
        
        return result, log

if __name__ == "__main__":
    orchestrator = GridOrchestrator()
    print("Starting Grid Management Loop (10 steps)...")
    for i in range(10):
        res, log = orchestrator.run_step()
        print(f"Step {i+1}: {res.prev_state.timestamp} | Action: {res.action.reasoning[:50]}... | Cost: ${res.total_cost:,.2f}")
