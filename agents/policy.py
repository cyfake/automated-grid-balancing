from schemas import PolicyPack

class PolicyAgent:
    """
    Policy Agent responsible for setting operating constraints and objectives.
    In a real system, this might adapt dynamically to regulatory or market changes.
    """
    def __init__(self, name: str = "PolicyAgent"):
        self.name = name

    def get_policy(self) -> PolicyPack:
        """Returns the current policy configuration."""
        # Static policy for the demo, but could be dynamic
        return PolicyPack(
            max_battery_discharge_mw=5000.0,  # Scaled for PJM levels
            max_battery_charge_mw=5000.0,
            min_soc_pct=0.1,
            target_soc_pct=0.4,
            peaker_threshold_price=120.0  # Spike threshold
        )
