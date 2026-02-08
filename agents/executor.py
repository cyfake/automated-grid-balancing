from schemas import DispatchPlan, StepResult

class ExecutorAgent:
    """
    Executor Agent responsible for implementing the plan in the environment.
    """
    def __init__(self, name: str = "ExecutorAgent"):
        self.name = name

    def execute_plan(self, env, plan: DispatchPlan) -> StepResult:
        """Applies the dispatch plan to the grid environment."""
        result = env.step(plan)
        return result
