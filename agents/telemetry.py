from schemas import GridState

class TelemetryAgent:
    """
    Telemetry Agent responsible for reading physical grid state.
    In this demo, it acts as a high-fidelity sensor interface to the environment.
    """
    def __init__(self, name: str = "TelemetryAgent"):
        self.name = name

    def fetch_state(self, env) -> GridState:
        """Fetch the current state from the environment."""
        state = env.get_state()
        # In a real system, we might add sensor noise here
        return state
