import uuid
from datetime import datetime
from schemas import StepResult, AuditLog

class VerifierAgent:
    """
    Verifier Agent responsible for auditing results and logging performance.
    """
    def __init__(self, name: str = "VerifierAgent"):
        self.name = name

    def verify_step(self, result: StepResult) -> AuditLog:
        """
        Audits the transition and creates a log entry.
        Checks for constraint violations (e.g., battery over-discharge).
        """
        # Simple verification: check if battery SoC matches expected bounds
        warnings = []
        if result.next_state.battery_soc_mwh < 0:
            warnings.append("Critical Error: Battery SoC below 0!")
        
        return AuditLog(
            timestamp=result.next_state.timestamp,
            agent_name=self.name,
            input_snapshot=result.action.model_dump(),
            output_snapshot=result.next_state.model_dump(),
            decision_id=str(uuid.uuid4()),
            metadata={"warnings": warnings, "cost": result.total_cost}
        )
