from agentfield import Agent, app
from automated_grid_balancing.common.schemas import GridState, ForecastBundle, PolicyPack, Action
from automated_grid_balancing.common.utils import setup_logging

logger = setup_logging("planner_agent")

@app.agent
class PlannerAgent(Agent):
    name = "planner_agent"
    description = "Decides optimal grid control actions"
    tags = ["planner"]

    @app.skill
    def plan(self, state: GridState, forecast: ForecastBundle, policy: PolicyPack) -> Action:
        """Determines best action to balance supply/demand."""
        # Simple heuristic waterfall
        net_load = state.demand_mw - state.renewable_mw
        
        # Current flexibility (simplified state tracking would be needed for true SoC)
        # But here we output a generic Action request
        
        action = Action()
        reasoning = []

        if net_load > 0:
            # Deficit: Need supply
            needed = net_load
            reasoning.append(f"Deficit of {needed:.1f} MW.")
            
            # 1. Battery Discharge
            discharge = min(needed, policy.max_action_mw) # Simplified max
            action.battery_mw = -discharge # Negative for discharge
            needed -= discharge
            reasoning.append(f"Discharging {discharge:.1f} MW.")
            
            # 2. Peaker if still needed (Uncapped for this demo)
            if needed > 0:
                # peaker = min(needed, policy.max_action_mw) 
                peaker = needed # Allow gas to fill the entire remaining gap
                action.peaker_mw = peaker
                needed -= peaker
                reasoning.append(f"Peaker dispatch {peaker:.1f} MW.")
                
            # 3. DR if critical (Manual only, or if gas fails physically - not simulated here)
            # if needed > 0:
            #     action.dr_mw = needed
            #     reasoning.append(f"Emergency DR {needed:.1f} MW.")
                
        else:
            # Surplus: Need to absorb
            surplus = abs(net_load)
            reasoning.append(f"Surplus of {surplus:.1f} MW.")
            
            # 1. Charge Battery
            charge = min(surplus, policy.max_action_mw)
            action.battery_mw = charge
            surplus -= charge
            reasoning.append(f"Charging {charge:.1f} MW.")
            
            # 2. Curtail
            if surplus > 0:
                action.curtail_mw = surplus
                reasoning.append(f"Curtailing {surplus:.1f} MW.")

        action.reasoning = " | ".join(reasoning)
        return action
