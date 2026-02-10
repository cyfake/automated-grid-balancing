import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime
import sys
import os

# Ensure project root is on path so src/ package resolves
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.agents.ingestion_agent import ingest
from src.agents.state_builder_agent import build_state_series
from src.agents.transfer_agent import build_topology
from src.agents.forecast_agent import build_forecast
from src.agents.policy_agent import default_policy
from src.planning.planner_agent import plan as run_planner
from src.sim.simulation_agent import simulate
from src.agents.stress_agent import find_stress_windows
from src.agents.recommendation_agent import generate_recommendations

st.set_page_config(page_title="Agentic Grid Management", layout="wide")

st.title("⚡ Multi-State Grid Agent")
st.markdown("""
This dashboard demonstrates the **Autonomous Grid Balancing** backend.
It uses 6 specialized agents to manage the grid across CA, TX, and NY.
""")


# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "pipeline_run" not in st.session_state:
    st.session_state.pipeline_run = False
    st.session_state.step_count = 0
    st.session_state.running = False
    st.session_state.history = []  # list of (hour, action, per_state_snapshot)

    try:
        records = ingest()
        state_series, battery_configs = build_state_series(
            records, start_hour=0, num_hours=48
        )
        states = sorted(state_series.keys())
        topology = build_topology(states)
        forecast = build_forecast(state_series, start_hour=0, horizon=24)
        policy = default_policy()
        dispatch_plan = run_planner(forecast, topology, battery_configs, policy)
        kpis = simulate(dispatch_plan, forecast, topology, battery_configs)
        stress_events = find_stress_windows(dispatch_plan, forecast)
        recs = generate_recommendations(
            forecast, topology, battery_configs, policy, kpis
        )

        st.session_state.forecast = forecast
        st.session_state.dispatch_plan = dispatch_plan
        st.session_state.kpis = kpis
        st.session_state.stress_events = stress_events
        st.session_state.recs = recs
        st.session_state.states = states
        st.session_state.battery_configs = battery_configs
        st.session_state.topology = topology
        st.session_state.policy = policy
        st.session_state.pipeline_run = True
    except Exception as e:
        st.error(f"Failed to initialize pipeline: {e}")
        st.stop()

    # Running KPI accumulators
    st.session_state.running_kpis = {
        "total_fuel_mwh": 0.0,
        "total_unserved_mwh": 0.0,
        "total_curtailment_mwh": 0.0,
        "total_renewable_mwh": 0.0,
        "total_load_mwh": 0.0,
        "battery_discharge_mwh": 0.0,
    }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.header("Simulation Controls")
focus_state = st.sidebar.selectbox(
    "Focus State", st.session_state.states, index=st.session_state.states.index("TX")
)
is_running = st.sidebar.checkbox(
    "Start Agentic Loop", value=st.session_state.running
)
reset_button = st.sidebar.button("Reset Simulation")

if reset_button:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
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
    st.subheader("Recommendations")
    rec_placeholder = st.empty()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_step_cost(action, policy, forecast, h, states):
    """Compute an approximate cost for a single hour from penalties."""
    cost = 0.0
    for st in states:
        cost += action.fuel_dispatch_mw.get(st, 0) * policy.fuel_penalty
        cost += action.unserved_mw.get(st, 0) * policy.unserved_penalty
        cost += action.curtailment_mw.get(st, 0) * policy.curtailment_penalty
    return cost


def _explain_step(action, forecast, h, focus):
    """Generate a one-line explanation for the step."""
    sf = forecast.states[focus]
    load = sf.load[h]
    solar = sf.solar[h]
    wind = sf.wind[h]
    fuel = action.fuel_dispatch_mw.get(focus, 0)
    discharge = action.battery_discharge_mw.get(focus, 0)
    charge = action.battery_charge_mw.get(focus, 0)
    curtail = action.curtailment_mw.get(focus, 0)
    unserved = action.unserved_mw.get(focus, 0)

    parts = [f"Load {load:.0f} MW"]
    if solar + wind > 0:
        parts.append(f"RE {solar + wind:.0f}")
    if fuel > 0:
        parts.append(f"Fuel {fuel:.0f}")
    if discharge > 0:
        parts.append(f"Batt↑ {discharge:.0f}")
    if charge > 0:
        parts.append(f"Batt↓ {charge:.0f}")
    if curtail > 0:
        parts.append(f"Curtail {curtail:.0f}")
    if unserved > 0:
        parts.append(f"UNSERVED {unserved:.0f}")
    return " | ".join(parts)


def update_ui():
    """Refresh all visualisation placeholders from session history."""
    if not st.session_state.history:
        return

    forecast = st.session_state.forecast
    policy = st.session_state.policy
    states = st.session_state.states
    focus = focus_state

    # Build a dataframe from history
    rows = []
    for h, action in st.session_state.history:
        sf = forecast.states[focus]
        row = {
            "hour": h,
            "Demand": sf.load[h],
            "Solar": sf.solar[h],
            "Wind": sf.wind[h],
            "Gas": action.fuel_dispatch_mw.get(focus, 0),
            "Battery": action.battery_discharge_mw.get(focus, 0),
            "Curtailment": action.curtailment_mw.get(focus, 0),
            "Unserved": action.unserved_mw.get(focus, 0),
            "SoC": action.soc_after_mwh.get(focus, 0),
            "Cost": _compute_step_cost(action, policy, forecast, h, states),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return

    # --- Live bar chart: supply stack vs demand for latest hour ---
    last = df.iloc[-1]
    supply_traces = []
    for name, color in [
        ("Gas", "#e71d36"),
        ("Battery", "#ff9f1c"),
        ("Wind", "#00A4E4"),
        ("Solar", "#FDB813"),
    ]:
        if last[name] > 0:
            supply_traces.append(
                go.Bar(name=name, x=["Supply"], y=[last[name]], marker_color=color)
            )
    demand_trace = go.Bar(
        name="Demand", x=["Demand"], y=[last["Demand"]], marker_color="white"
    )
    fig_bar = go.Figure(data=[demand_trace] + supply_traces)
    fig_bar.update_layout(
        barmode="stack",
        title=f"Hour {int(last['hour'])} — {focus} Balance (MW)",
        height=300,
        yaxis=dict(title="Power (MW)"),
        showlegend=True,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    dynamics_placeholder.plotly_chart(fig_bar, use_container_width=True)

    # --- Time-series stacked area ---
    fig_ts = go.Figure()
    for name, color in [
        ("Solar", "#FDB813"),
        ("Wind", "#00A4E4"),
        ("Battery", "#ff9f1c"),
        ("Gas", "#e71d36"),
    ]:
        fig_ts.add_trace(
            go.Scatter(
                x=df["hour"],
                y=df[name],
                mode="lines",
                stackgroup="one",
                name=name,
                line=dict(width=0, color=color),
            )
        )
    fig_ts.add_trace(
        go.Scatter(
            x=df["hour"],
            y=df["Demand"],
            mode="lines",
            name="Demand",
            line=dict(color="white", width=2, dash="dot"),
        )
    )
    fig_ts.update_layout(
        height=400,
        xaxis=dict(title="Hour"),
        yaxis=dict(title="Power (MW)"),
        margin=dict(l=0, r=0, t=0, b=0),
        hovermode="x unified",
    )
    history_placeholder.plotly_chart(fig_ts, use_container_width=True)

    # --- Metrics cards ---
    h_idx = int(last["hour"])
    action = st.session_state.dispatch_plan.actions[h_idx]
    sf = forecast.states[focus]
    renewable_total = sf.solar[h_idx] + sf.wind[h_idx]
    supply_total = renewable_total + last["Gas"] + last["Battery"]
    balance_delta = supply_total - last["Demand"]

    with state_placeholder.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Demand", f"{last['Demand']:.0f} MW")
        c2.metric(
            "Solar / Wind",
            f"{sf.solar[h_idx]:.0f} / {sf.wind[h_idx]:.0f} MW",
        )
        c3.metric(
            "Balance",
            f"{supply_total:.0f} MW supplied",
            delta=f"{balance_delta:+.0f} MW",
        )
        c4.metric("Step Cost", f"${last['Cost']:,.0f}")

    # --- Audit logs ---
    with log_placeholder.container():
        for h, action in reversed(st.session_state.history[-10:]):
            explanation = _explain_step(action, forecast, h, focus)
            cost = _compute_step_cost(action, policy, forecast, h, states)
            st.text(f"[H{h:02d}] {explanation} | Cost: ${cost:,.0f}")

    # --- Run metrics ---
    rk = st.session_state.running_kpis
    with metric_placeholder.container():
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Fuel", f"{rk['total_fuel_mwh']:,.0f} MWh")
        m2.metric("Total Unserved", f"{rk['total_unserved_mwh']:,.0f} MWh")
        m3.metric("Curtailed", f"{rk['total_curtailment_mwh']:,.0f} MWh")
        m4.metric("Renewable Used", f"{rk['total_renewable_mwh']:,.0f} MWh")

    # --- Recommendations ---
    recs = st.session_state.recs
    if recs:
        with rec_placeholder.container():
            for r in recs[:5]:
                st.markdown(f"**#{r.rank}** `{r.rec_type}` — {r.description}")


# ---------------------------------------------------------------------------
# Main Run Logic
# ---------------------------------------------------------------------------
if is_running:
    status_text = st.empty()

    step_idx = st.session_state.step_count
    plan = st.session_state.dispatch_plan
    forecast = st.session_state.forecast
    policy = st.session_state.policy
    states = st.session_state.states
    total_hours = len(plan.actions)

    while step_idx < total_hours:
        with status_text.container():
            st.write(
                f"**Step {step_idx} / {total_hours}** — _Agents processing..._"
            )

        time.sleep(0.15)

        try:
            action = plan.actions[step_idx]

            # Accumulate running KPIs
            rk = st.session_state.running_kpis
            for st_name in states:
                sf = forecast.states[st_name]
                rk["total_fuel_mwh"] += action.fuel_dispatch_mw.get(st_name, 0)
                rk["total_unserved_mwh"] += action.unserved_mw.get(st_name, 0)
                rk["total_curtailment_mwh"] += action.curtailment_mw.get(st_name, 0)
                rk["total_renewable_mwh"] += (
                    sf.solar[step_idx]
                    + sf.wind[step_idx]
                    - action.curtailment_mw.get(st_name, 0)
                )
                rk["total_load_mwh"] += sf.load[step_idx]
                rk["battery_discharge_mwh"] += action.battery_discharge_mw.get(
                    st_name, 0
                )

            st.session_state.history.append((step_idx, action))
            st.session_state.step_count += 1
            step_idx += 1

            update_ui()

        except Exception as e:
            st.error(f"Error at step {step_idx}: {e}")
            st.session_state.running = False
            break

    if step_idx >= total_hours:
        status_text.success("Simulation Complete!")
        st.session_state.running = False

# Show UI if paused but has history
if not is_running and st.session_state.history:
    update_ui()
