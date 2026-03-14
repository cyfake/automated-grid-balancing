# Autonomous Grid Balancing Agent

An autonomous agent-based simulation of power grid balancing built with the **AgentField framework**.  
The project demonstrates how AI agents can coordinate to maintain supply–demand balance in a simulated electricity grid while replacing traditional distributed microservice architectures with a lightweight agent-based system.

Instead of multiple microservices communicating through REST APIs, Kafka queues, and orchestration frameworks, this system uses **AgentField agents communicating directly through `app.discover` and `app.call` with shared Pydantic schemas**.

---

# Overview

This project simulates a **grid-balancing control system inspired by the Texas (ERCOT) power grid**.

It demonstrates how autonomous agents can:

- ingest real-world load and generation data  
- forecast demand  
- plan dispatch decisions  
- simulate grid physics  
- audit and verify safe system operation  

The system is designed to illustrate **real-time grid balancing with AI-driven decision-making**.

---

# Features

- **Real-World Data**  
  Uses 20-year historical load data (PJM dataset used as a proxy for ERCOT demand patterns).

- **Agentic Control**  
  Six specialized agents collaborate to maintain supply-demand balance.

- **Physical Simulation**  
  Frequency deviation is calculated based on supply/demand imbalance to simulate real grid dynamics.

- **Visual Dashboard**  
  A Streamlit dashboard displays:
  - live supply vs demand balance
  - grid frequency stability
  - energy mix (solar, wind, gas, battery)
  - detailed audit logs of agent decisions

---

# System Architecture

The architecture follows a **Consolidation → Decision → Audit pipeline**.

Six agents coordinate the grid balancing loop:

1. **Orchestrator Agent**  
   Drives the simulation loop and coordinates agent interactions.

2. **Telemetry Agent**  
   Ingests and standardizes load and renewable data streams into a canonical `GridState`.

3. **Forecast Agent**  
   Generates short-term demand and renewable forecasts.

4. **Policy Agent**  
   Defines operational limits and cost weights for dispatch decisions.

5. **Planner Agent**  
   Determines dispatch actions using heuristic logic (Battery → Demand Response → Peaker Plants).

6. **Verifier Agent**  
   Simulates grid physics and verifies that system constraints are satisfied.

---

# Replacing Traditional Microservices

| Traditional Approach | Agent-Based Approach |
|---|---|
| Service mesh with multiple containers, HTTP/gRPC overhead | Lightweight AgentField agents |
| Airflow DAG orchestration or cron scheduling | Autonomous reasoning loop |
| Distributed logging across services | Unified audit trail of decisions |
| JSON schema drift between services | Shared Pydantic schemas |

The agent architecture provides **simpler orchestration, clearer decision logs, and easier experimentation**.

---

# Setup

### 1. Clone the repository

### 2. Install dependencies

---

# Running the Simulation

### Option 1 — Streamlit Dashboard

Launch the interactive simulation dashboard:

---

### Option 2 — Jupyter Demo

Run the demonstration notebook:


---

### Option 3 — Direct Python Execution

Run the orchestrator programmatically:


```python
from agents.orchestrator_agent import OrchestratorAgent, RunRequest, DatasetConfig

agent = OrchestratorAgent()

agent.plan_run(
    RunRequest(
        dataset=DatasetConfig(pjm_dir="../data")
    )
)

