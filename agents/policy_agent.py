import yaml
from typing import Tuple
from agentfield import Agent, app
from automated_grid_balancing.common.schemas import PolicyPack
from automated_grid_balancing.common.utils import setup_logging

logger = setup_logging("policy_agent")

@app.agent
class PolicyAgent(Agent):
    name = "policy_agent"
    description = "Serves governance rules and cost weights"
    tags = ["policy", "guardrails"]

    @app.skill
    def load_policy(self, policy_path: str, cost_path: str) -> Tuple[PolicyPack, dict]:
        """Loads policy and cost configurations."""
        logger.info(f"Loading policy from {policy_path}")
        with open(policy_path, 'r') as f:
            p_data = yaml.safe_load(f)
            
        with open(cost_path, 'r') as f:
            c_data = yaml.safe_load(f)
            
        policy = PolicyPack(**p_data)
        return policy, c_data
