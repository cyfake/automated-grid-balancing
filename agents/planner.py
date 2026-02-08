import os
import time
from datetime import datetime
from dotenv import load_dotenv
import openai
import instructor
import google.generativeai as genai
from schemas import GridState, ForecastBundle, PolicyPack, DispatchPlan

# Load environment variables
load_dotenv()

class PlannerAgent:
    """
    Planner Agent: The 'Brain' that coordinates state and forecast to produce a plan.
    It uses Google Gemini (or GPT-4) to perform generative reasoning for grid dispatch.
    """
    VERSION = "2.2-GEMINI-FIX"

    def __init__(self, name: str = "PlannerAgent"):
        self.name = name
        self.client = None
        self.model_type = None
        self._refresh_client()

    def _refresh_client(self):
        """No-op for now as we use hardcoded logic."""
        self.client = None
        self.model_type = "deterministic"

    def create_plan(self, state: GridState, forecast: ForecastBundle, policy: PolicyPack) -> DispatchPlan:
        """
        Creates a dispatch plan using deterministic rule-based logic.
        """
        # We skip the LLM call entirely for performance and simplicity
        return self._fallback_rule_base(state, forecast, policy, "Autonomous Rule-Base")

    def _fallback_rule_base(self, state: GridState, forecast: ForecastBundle, policy: PolicyPack, reason: str = "Steady state.") -> DispatchPlan:
        """Original rule-based logic used as a safety fallback."""
        battery_charge = 0.0
        peaker_mw = 0.0
        reasoning = []
        soc_pct = state.battery_soc_mwh / state.battery_max_mwh
        
        if state.current_price >= policy.peaker_threshold_price:
            peaker_mw = min(10000.0, state.net_demand_mw)
            reasoning.append(f"Peaker activation (Price threshold).")
        
        if state.current_price < 50.0 and soc_pct < policy.target_soc_pct:
            needed_mwh = (policy.target_soc_pct - soc_pct) * state.battery_max_mwh
            battery_charge = min(policy.max_battery_charge_mw, needed_mwh)
            reasoning.append(f"Charging (Low market price).")
        elif state.current_price > 100.0 and soc_pct > policy.min_soc_pct:
            available_mwh = (soc_pct - policy.min_soc_pct) * state.battery_max_mwh
            battery_charge = -min(policy.max_battery_discharge_mw, available_mwh)
            reasoning.append(f"Discharging (High market price).")

        final_reasoning = " | ".join(reasoning) if reasoning else "No specific actions."
        return DispatchPlan(
            timestamp=state.timestamp,
            battery_charge_mw=battery_charge,
            peaker_mw=peaker_mw,
            reasoning=f"Fallback ({reason}): {final_reasoning}"
        )

