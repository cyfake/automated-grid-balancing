import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import sys
import os

# Ensure AgentField integration
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agentfield import app
from automated_grid_balancing.agents.orchestrator_agent import OrchestratorAgent
from automated_grid_balancing.agents.telemetry_agent import TelemetryAgent
from automated_grid_balancing.agents.forecast_agent import ForecastAgent
from automated_grid_balancing.agents.policy_agent import PolicyAgent
from automated_grid_balancing.agents.planner_agent import PlannerAgent
from automated_grid_balancing.agents.verifier_agent import VerifierAgent
from automated_grid_balancing.common.schemas import DatasetConfig, RunRequest, ExogenousConfig

st.set_page_config(page_title="Agentic Grid Management", layout="wide")

st.title("⚡ Texas Grid Agent")
st.markdown("""
This dashboard demonstrates the **Autonomous Grid Balancing** backend. 
It uses 6 specialized agents to manage the grid in real-time.
""")

# --- Session State Initialization ---
if 'orchestrator' not in st.session_state:
    st.session_state.orchestrator = OrchestratorAgent()
    st.session_state.context = None 
    st.session_state.history = []
    st.session_state.step_count = 0
    st.session_state.running = False
    
    # Initialize Context
    try:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "automated_grid_balancing", "data", "processed"))
        dataset = DatasetConfig(pjm_dir=data_dir, pjm_pattern="pjm_hourly_est.csv", region="Texas")
        req = RunRequest(dataset=dataset, horizon_steps=6, n_steps=8760)
        
        # Prepare Run
        context = st.session_state.orchestrator.prepare_run(req)
        
        # Filter for a specific year (e.g., 2000) to ensure meaningful simulation
        # The Orchestrator returns the full stream in context['df_stream']
        df = context['df_stream']
        year_to_simulate = 2000
        df = df[df['timestamp'].dt.year == year_to_simulate]
        
        if df.empty:
            st.error(f"No data found for year {year_to_simulate} in {dataset.pjm_pattern}")
            st.stop()
            
        context['df_stream'] = df.reset_index(drop=True)
        st.session_state.context = context
    except Exception as e:
        st.error(f"Failed to initialize simulation context: {e}")
        st.stop()

    # KPI State
    st.session_state.kpis = {
        "max_freq_dev": 0.0,
        "total_cost": 0.0,
        "violations": 0,
        "battery_cycles": 0,
        "gen_solar": 0.0,
        "gen_wind": 0.0,
        "gen_gas": 0.0,
        "gen_battery": 0.0
    }

# --- Sidebar ---
st.sidebar.header("Simulation Controls")
is_running = st.sidebar.checkbox("Start Agentic Loop", value=st.session_state.running)
reset_button = st.sidebar.button("Reset Simulation")

if reset_button:
    st.session_state.orchestrator = OrchestratorAgent()
    st.session_state.history = []
    st.session_state.step_count = 0
    st.session_state.running = False
    st.session_state.kpis = {
        "max_freq_dev": 0.0,
        "total_cost": 0.0,
        "violations": 0,
        "battery_cycles": 0,
        "gen_solar": 0.0,
        "gen_wind": 0.0,
        "gen_gas": 0.0,
        "gen_battery": 0.0
    }
    # Re-init context
    try:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "automated_grid_balancing", "data", "processed"))
        dataset = DatasetConfig(pjm_dir=data_dir, pjm_pattern="pjm_hourly_est.csv", region="Texas")
        req = RunRequest(dataset=dataset, horizon_steps=6, n_steps=8760)
        
        context = st.session_state.orchestrator.prepare_run(req)
        
        # Filter 2000
        df = context['df_stream']
        year_to_simulate = 2000
        df = df[df['timestamp'].dt.year == year_to_simulate]
        context['df_stream'] = df.reset_index(drop=True)
        
        st.session_state.context = context
    except Exception as e:
        st.error(f"Failed to reset context: {e}")
    st.rerun()

# --- Layout ---
tab1, tab2 = st.tabs(["⚡ Live Dynamics", "📊 Analytics & Insights"])

with tab1:
    st.subheader("Real-Time Balance")
    dynamics_placeholder = st.empty()
    
    st.subheader("Current Grid State")
    state_placeholder = st.empty()
    
    st.subheader("Energy Composition (Fuel Mix)")
    history_placeholder = st.empty()

with tab2:
    st.subheader("Audit Logs")
    log_placeholder = st.empty()
    st.subheader("Run Metrics")
    metric_placeholder = st.empty()

# --- Visualization Helper ---
def update_ui():
    if not st.session_state.history:
        return

    # Data Prep
    df_data = []
    for state, log in st.session_state.history:
        row = {
            "time": state.timestamp,
            "Demand": state.demand_mw,
            "Renewables": state.renewable_mw,
            "Solar": state.solar_mw,
            "Wind": state.wind_mw,
            "Gas": log.action.peaker_mw,
            "Battery": max(0, -log.action.battery_mw), # Discharge
            "Curtailment": log.action.curtail_mw,
            "Cost": log.cost,
            "Violations": len(log.violations)
        }
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    
    
    if not df.empty:
        # --- Live Dynamics (Supply vs Demand) ---
        last_row = df.iloc[-1]
        
        supply_traces = []
        # Stack order: Gas (base), Battery, Wind, Solar
        if last_row['Gas'] > 0: supply_traces.append(go.Bar(name='Gas', x=['Supply'], y=[last_row['Gas']], marker_color='#e71d36'))
        if last_row['Battery'] > 0: supply_traces.append(go.Bar(name='Battery', x=['Supply'], y=[last_row['Battery']], marker_color='#ff9f1c'))
        if last_row['Wind'] > 0: supply_traces.append(go.Bar(name='Wind', x=['Supply'], y=[last_row['Wind']], marker_color='#00A4E4'))
        if last_row['Solar'] > 0: supply_traces.append(go.Bar(name='Solar', x=['Supply'], y=[last_row['Solar']], marker_color='#FDB813'))
        
        demand_trace = go.Bar(name='Demand', x=['Demand'], y=[last_row['Demand']], marker_color='white')
        
        fig_dynamics = go.Figure(data=[demand_trace] + supply_traces)
        fig_dynamics.update_layout(
            barmode='stack', 
            title="Real-Time Grid Balance (MW)",
            height=300,
            yaxis=dict(title='Power (MW)'),
            showlegend=True,
            margin=dict(l=0, r=0, t=30, b=0)
        )
        dynamics_placeholder.plotly_chart(fig_dynamics, use_container_width=True)

        # --- Time Series History ---
        # st.subheader("Energy Composition (Fuel Mix)") # Removed to prevent duplication
        fig = go.Figure()
        # Stacked Area Chart (Order matters)
        fig.add_trace(go.Scatter(x=df['time'], y=df['Solar'], mode='lines', stackgroup='one', name='Solar', line=dict(width=0, color='#FDB813')))
        fig.add_trace(go.Scatter(x=df['time'], y=df['Wind'], mode='lines', stackgroup='one', name='Wind', line=dict(width=0, color='#00A4E4')))
        fig.add_trace(go.Scatter(x=df['time'], y=df['Battery'], mode='lines', stackgroup='one', name='Battery', line=dict(width=0, color='#ff9f1c')))
        fig.add_trace(go.Scatter(x=df['time'], y=df['Gas'], mode='lines', stackgroup='one', name='Gas', line=dict(width=0, color='#e71d36')))
        fig.add_trace(go.Scatter(x=df['time'], y=df['Demand'], mode='lines', name='Demand', line=dict(color='white', width=2, dash='dot')))
        fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), hovermode="x unified")
        history_placeholder.plotly_chart(fig, use_container_width=True)
    
    # Metrics
    last_state, last_log = st.session_state.history[-1]
    with state_placeholder.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Demand", f"{last_state.demand_mw:.0f} MW")
        c2.metric("Solar/Wind", f"{last_state.solar_mw:.0f} / {last_state.wind_mw:.0f} MW")
        c3.metric("Frequency", f"{last_state.freq_proxy:.2f} Hz", delta=f"{last_state.freq_proxy-60:.2f}")
        c4.metric("Step Cost", f"${last_log.cost:,.2f}")

    # Logs
    with log_placeholder.container():
        for state, log in reversed(st.session_state.history[-10:]):
            st.text(f"[{state.timestamp.strftime('%H:%M')}] {log.explanation} | Cost: ${log.cost:.0f}")

# --- Main Run Logic ---
# --- Main Run Logic ---
if is_running:
    # Use a loop within the script execution to avoid full page reloads
    # This keeps the session active and updates placeholders dynamically.
    
    status_text = st.empty()
    stop_button_pl = st.empty()
    
    # Initial step index from session state
    step_idx = st.session_state.step_count
    context = st.session_state.context
    
    # We need a way to stop inside the loop since the sidebar checkbox won't update session state 
    # until the script finishes or reruns.
    # So we add a "Stop" button in the main area or check for a file flag (too complex).
    # Streamlit's "Stop" button in the top right works, but let's just make the loop check a placeholder button?
    # Actually, simpler: Just run for X steps or until finished, then rerun to update state.
    # OR, rely on the user unchecking the box which triggers a rerun... WAit.
    # If we are in a while loop, the script effectively hangs in the loop. The "checkbox" change in UI 
    # will trigger a thread interrupt/RerunRequest in Streamlit server, effectively breaking the loop.
    # So `while is_running:` (where `is_running` is the value at START of script) is fine, 
    # because if user unchecks it, Streamlit kills the script and changes `is_running` to False on next run.
    
    while step_idx < len(context['df_stream']):
        
        with status_text.container():
            st.write(f"**Step {step_idx} / {len(context['df_stream'])}** - _Agents processing..._")
        
        time.sleep(0.1) 
        try:
            result = st.session_state.orchestrator.run_step(context, step_idx)
            
            st.session_state.history.append((result['state'], result['log']))
            st.session_state.step_count += 1
            step_idx += 1
            
            update_ui()
            
        except Exception as e:
            st.error(f"Error at step {step_idx}: {e}")
            st.session_state.running = False
            break
            
    if step_idx >= len(context['df_stream']):
        status_text.success("Simulation Complete!")
        st.session_state.running = False

# Show UI if paused but has history
if not is_running and st.session_state.history:
    update_ui()
