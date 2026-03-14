# Autonomous Grid Balancing Agent

An autonomous agent-based simulation of electricity grid balancing built using the **AgentField framework**.

The project demonstrates how specialized AI agents can coordinate to balance supply and demand in a power grid while replacing traditional distributed microservice architectures with a lightweight agent-based system.

Instead of multiple services communicating through REST APIs, message queues, and orchestration frameworks, this system uses **AgentField agents communicating through `app.discover` and `app.call` with shared Pydantic schemas**.

---

# Overview

This project simulates an autonomous grid control system inspired by the **Texas (ERCOT) power grid**.

The system demonstrates how agents can coordinate to:

- ingest electricity demand and generation data  
- forecast near-term demand  
- decide energy dispatch actions  
- simulate physical grid behavior  
- verify system safety constraints  

The architecture is designed to illustrate how **autonomous agents could simplify infrastructure control systems** while maintaining transparency and auditability.

---

# Features

### Real-World Data
Uses historical load data (PJM dataset used as a proxy for grid demand patterns).

### Agentic Control
Six specialized agents collaborate to maintain grid stability and balance supply with demand.

### Physical Simulation
Grid frequency deviation is simulated based on supply–demand imbalance.

### Visual Dashboard
A **Streamlit dashboard** provides real-time visualization of the system:

- Live supply vs demand balance  
- Grid frequency stability  
- Energy mix (Solar, Wind, Gas, Battery)  
- Detailed audit logs of agent decisions  

---

# System Architecture

The architecture follows a **Consolidation → Decision → Audit pipeline**.

Six agents coordinate the grid balancing loop:

### 1. Orchestrator Agent
Drives the simulation loop and coordinates all other agents.

### 2. Telemetry Agent
Ingests and standardizes multi-source data into a canonical `GridState`.

### 3. Forecast Agent
Generates short-term forecasts for electricity demand and renewable generation.

### 4. Policy Agent
Defines operating constraints and dispatch cost priorities.

### 5. Planner Agent
Determines dispatch decisions using a heuristic waterfall strategy:

```
Battery → Demand Response → Peaker Plants
```

### 6. Verifier Agent
Simulates grid physics and verifies that system constraints remain satisfied.

---

# Replacing Traditional Microservices

| Traditional Architecture | Agent-Based Architecture |
|---|---|
| Multiple containers and service mesh | Lightweight Python agents |
| REST/gRPC communication overhead | Direct in-memory agent calls |
| External workflow orchestration | Autonomous reasoning loop |
| Distributed logging | Unified audit trail |
| Schema inconsistencies | Shared Pydantic schemas |

This approach enables **simpler experimentation, clearer reasoning logs, and faster development cycles**.

---

# Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd automated-grid-balancing
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

# Running the Simulation

### Run the Streamlit dashboard

```bash
streamlit run app.py
```

---

### Run the Jupyter demo

```bash
jupyter notebook notebooks/demo.ipynb
```

---

### Run the orchestrator directly

```python
from agents.orchestrator_agent import OrchestratorAgent, RunRequest, DatasetConfig

agent = OrchestratorAgent()

agent.plan_run(
    RunRequest(
        dataset=DatasetConfig(pjm_dir="../data")
    )
)
```

---

# Why This Project Exists

Modern infrastructure systems often rely on complex distributed architectures that are difficult to reason about and experiment with.

This project explores an alternative design:

**autonomous agents coordinating through shared state and reasoning loops.**

The goal is to demonstrate how agent-based control systems could simplify automation in complex environments such as electricity grids.
