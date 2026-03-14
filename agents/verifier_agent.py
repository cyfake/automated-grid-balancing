from datetime import timedelta
from agentfield import Agent, app
from automated_grid_balancing.common.schemas import GridState, Action, PolicyPack, AuditLog
from automated_grid_balancing.common.utils import setup_logging

logger = setup_logging("verifier_agent")

@app.agent
class VerifierAgent(Agent):
    name = "verifier_agent"
    description = " audits actions and simulates physics"
    tags = ["verify", "audit"]
    
    @app.skill
    def verify_and_audit(
        self, 
        step: int, 
        prev_state: GridState, 
        action: Action, 
        policy: PolicyPack, 
        cost_weights: dict
    ) -> tuple[GridState, AuditLog]:
        
        # 1. Apply Physics (Transition)
        # Net Imbalance = Demand - Renewable - (Battery + Peaker + DR - Curtail)
        # Ideally should be 0.
        
        supply = prev_state.renewable_mw - action.curtail_mw + action.peaker_mw + action.dr_mw
        # Battery: + means charging (Load), - means discharging (Supply)
        # So Net Supply from battery = -battery_mw
        supply -= action.battery_mw
        
        imbalance = prev_state.demand_mw - supply
        
        # 2. Compute Proxies
        # Freq: 60 - k * imbalance
        # We need a stronger K factor to show deviation when Planner fails to cover load
        k_freq = 0.05 
        
        # Inertia: Use previous frequency as baseline, don't just snap to new one
        # This makes it feel more like a physical system
        prev_dev = prev_state.freq_proxy - 60.0
        target_dev = -(imbalance * k_freq)
        
        # Simple low-pass filter for inertia
        alpha = 0.3
        new_dev = prev_dev * (1 - alpha) + target_dev * alpha
        
        next_freq = 60.0 + new_dev
        
        # Clip to realistic bounds
        next_freq = max(59.0, min(61.0, next_freq))
        
        # Reserve: Simple capacity check
        # Assume max capacity is fixed at 1.2 * max load seen so far or passed in
        # For proxy, let's say reserve decreased by how much we used peaker/battery
        # This is a stateless simplifcation
        next_reserve = prev_state.reserve_proxy - action.peaker_mw + action.curtail_mw
        
        # Next Timestamp
        next_ts = prev_state.timestamp + timedelta(hours=1)
        
        next_state = GridState(
            t=step+1,
            timestamp=next_ts,
            region=prev_state.region,
            demand_mw=prev_state.demand_mw, # Placeholder, will be updated by telemetry next step usually
            renewable_mw=prev_state.renewable_mw, # Placeholder
            solar_mw=prev_state.solar_mw, # Placeholder
            wind_mw=prev_state.wind_mw, # Placeholder
            reserve_proxy=next_reserve,
            freq_proxy=next_freq
        )
        
        # 3. Violations
        violations = []
        if next_freq < policy.freq_min_hz:
            violations.append(f"Frequency dip: {next_freq:.4f} Hz < {policy.freq_min_hz}")
        
        if next_reserve < policy.reserve_min_mw:
            violations.append(f"Reserve margins low: {next_reserve:.1f} MW")

        # 4. Cost
        step_cost = 0.0
        step_cost += abs(action.battery_mw) * cost_weights['battery_cycle_cost']
        step_cost += action.curtail_mw * cost_weights['curtailment_penalty']
        step_cost += action.dr_mw * cost_weights['dr_cost']
        step_cost += action.peaker_mw * cost_weights['peaker_cost']
        step_cost += len(violations) * cost_weights['violation_penalty']
        
        log = AuditLog(
            step=step,
            timestamp=prev_state.timestamp,
            action=action,
            violations=violations,
            cost=step_cost,
            explanation=f"Action taken: {action.reasoning}. Result freq: {next_freq:.2f}Hz."
        )
        
        return next_state, log
