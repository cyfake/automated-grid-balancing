# Texas Grid Agent

An autonomous agent-based simulation of the Texas (ERCOT) power grid, demonstrating real-time grid balancing using AI agents.

## Features
- **Real-World Data**: Uses 20-year historical load data (PJM proxy for Texas load profile).
- **Agentic Control**: 6 specialized agents (Orchestrator, Planner, Verifier, etc.) collaborate to maintain grid frequency (60Hz).
- **Physical Simulation**: Realistic frequency deviation based on Supply/Demand imbalance.
- **Visual Dashboard**: Real-time Streamlit dashboard showing:
  - Live Supply vs Demand balance
  - Frequency stability
  - Energy mix (Solar, Wind, Gas, Battery)
  - Detailed audit logs of agent decisions

## Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd AgentField
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the simulation**:
   ```bash
   streamlit run app.py
   ```

## Architecture
The system uses the **AgentField** framework to coordinate:
- **TelemetryAgent**: Ingests load and renewable data.
- **ForecasterAgent**: Predicts near-term demand.
- **PlannerAgent**: Decides dispatch (Gas/Battery) to meet demand, uncapped for realistic physics.
- **VerifierAgent**: Simulates grid physics (frequency response) and audits safety.
