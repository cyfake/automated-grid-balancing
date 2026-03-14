# Autonomous Grid Balancing Agent

**Using AgentField Primitives to replace complex microservices with guided autonomy.**

This project demonstrates a minimalist, autonomous backend for grid balancing. Instead of 6 microservices with REST APIs, Kafka, and complex orchestration, we use 6 AgentField agents communicating via `app.discover` and `app.call` with shared Pydantic schemas.

## The Architecture
**Consolidation -> Decision -> Audit**

1.  **Orchestrator Agent**: The "brain" that drives the loop.
2.  **Telemetry Agent**: "Ingest." Standardizes multi-stream data (PJM/EIA) into a canonical `GridState`.
3.  **Forecast Agent**: "Predict." Generates future load/renewable profiles.
4.  **Policy Agent**: "Govern." Serves safe operating limits and cost weights.
5.  **Planner Agent**: "Decide." Heuristic waterfall logic (Battery -> DR -> Peaker).
6.  **Verifier Agent**: "Audit." Simulates physics and checks constraints.

## Replaced Complexity
| Traditional Approach | Autonomous Agent Approach |
| :--- | :--- |
| **Service Mesh**: 6 containers, HTTP/gRPC overhead, mismatched JSON schemas. | **AgentField**: 6 classes, in-memory `app.call`, strict Pydantic `GridState`. |
| **Orchestration**: Airflow DAGs or hardcoded cron scripts. | **Reasoner**: A single python function `plan_run` that discovers skills dynamically. |
| **Observability**: Scattered logs across services. | **Audit Logs**: Unified `Linkable Audit Trail` with "reasoning" for every action. |

## Quick Start
1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run Demo**:
   ```bash
   jupyter notebook notebooks/demo.ipynb
   ```
   Or run the orchestrator directly in python:
   ```python
   from agents.orchestrator_agent import OrchestratorAgent, RunRequest, DatasetConfig
   
   agent = OrchestratorAgent()
   agent.plan_run(RunRequest(dataset=DatasetConfig(pjm_dir="../data")))
   ```
