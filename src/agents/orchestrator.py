"""
Orchestrator: calls all components in order and returns final artifacts.
This is the main pipeline — pure Python, no LLM required.
"""
import os
import time
from typing import Dict, List, Optional
from pathlib import Path

from ..schemas.models import (
    Plan,
    KPIs,
    Recommendation,
    PolicyConfig,
)
from ..agents.ingestion_agent import ingest
from ..agents.state_builder_agent import build_state_series
from ..agents.transfer_agent import build_topology
from ..agents.forecast_agent import build_forecast
from ..agents.policy_agent import default_policy
from ..planning.planner_agent import plan as run_planner
from ..sim.simulation_agent import simulate
from ..agents.stress_agent import find_stress_windows
from ..agents.recommendation_agent import generate_recommendations
from ..agents.audit_agent import (
    write_decisions_log,
    write_kpis,
    write_recommendations,
    write_summary_md,
)
from ..agents.ingestion_agent import data_provenance
from ..utils.helpers import ensure_dirs, LOGS_DIR, REPORTS_DIR


def run_pipeline(
    data_dir: str = None,
    start_hour: int = 0,
    horizon: int = 24,
    enable_llm: bool = False,
) -> Dict:
    """
    Run the full grid load-balancing pipeline.

    Parameters
    ----------
    data_dir : str, optional
        Directory containing the processed CSV.  Defaults to data/processed/.
        If no processed CSV exists, the EIA client will fetch one automatically.
    """
    t0 = time.time()
    ensure_dirs()

    print("[1/9] Ingesting data...")
    records = ingest(data_dir)

    print("[2/9] Building state series...")
    state_series, battery_configs = build_state_series(records, start_hour=0, num_hours=start_hour + horizon + 24)

    print("[3/9] Building transfer topology...")
    states = sorted(state_series.keys())
    topology = build_topology(states)

    print("[4/9] Building forecast...")
    forecast = build_forecast(state_series, start_hour=start_hour, horizon=horizon)

    print("[5/9] Loading policy...")
    policy = default_policy()

    print("[6/9] Running planner...")
    dispatch_plan = run_planner(forecast, topology, battery_configs, policy)

    print("[7/9] Simulating and computing KPIs...")
    kpis = simulate(dispatch_plan, forecast, topology, battery_configs)

    print("[8/9] Finding stress windows...")
    stress_events = find_stress_windows(dispatch_plan, forecast)

    print("[9/9] Generating recommendations...")
    recs = generate_recommendations(forecast, topology, battery_configs, policy, kpis)

    # Optional LLM narrative
    llm_narrative = None
    if enable_llm:
        llm_narrative = _get_llm_summary(kpis, recs, stress_events)

    # Write outputs
    provenance = data_provenance()
    write_decisions_log(dispatch_plan)
    write_kpis(kpis)
    write_recommendations(recs)
    write_summary_md(
        kpis, recs, stress_events, dispatch_plan,
        llm_narrative=llm_narrative,
        forecast=forecast,
        battery_configs=battery_configs,
        topology=topology,
        provenance=provenance,
    )

    elapsed = time.time() - t0
    print(f"\nPipeline complete in {elapsed:.2f}s")
    print(f"  Decisions log: logs/decisions.jsonl")
    print(f"  KPIs:          logs/kpis.json")
    print(f"  Recommendations: logs/recommendations.json")
    print(f"  Summary:       reports/summary.md")

    return {
        "status": "success",
        "elapsed_seconds": round(elapsed, 2),
        "kpis": kpis.to_dict(),
        "num_recommendations": len(recs),
        "num_stress_events": len(stress_events),
        "output_paths": {
            "decisions": str(LOGS_DIR / "decisions.jsonl"),
            "kpis": str(LOGS_DIR / "kpis.json"),
            "recommendations": str(LOGS_DIR / "recommendations.json"),
            "summary": str(REPORTS_DIR / "summary.md"),
        },
    }


def _get_llm_summary(kpis: KPIs, recs, stress_events) -> Optional[str]:
    """
    Optional Gemini-powered narrative. Only called if ENABLE_LLM_SUMMARY=true.
    Uses simple caching to avoid repeated calls.
    """
    import hashlib
    import json

    cache_dir = LOGS_DIR / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Build prompt context
    context = {
        "kpis": kpis.to_dict(),
        "top_recs": [r.to_dict() for r in recs[:3]],
        "stress_count": len(stress_events),
        "critical_count": len([e for e in stress_events if e.get("severity") == "critical"]),
    }
    context_str = json.dumps(context, sort_keys=True)
    cache_key = hashlib.md5(context_str.encode()).hexdigest()
    cache_path = cache_dir / f"{cache_key}.txt"

    if cache_path.exists():
        return cache_path.read_text()

    # Try Gemini via Agentfield or direct API
    try:
        narrative = _call_gemini(context_str)
        cache_path.write_text(narrative)
        return narrative
    except Exception as e:
        print(f"[warn] LLM summary failed ({e}), using template fallback")
        return _template_summary(kpis, recs, stress_events)


def _call_gemini(context_str: str) -> str:
    """
    Call Gemini via google.generativeai if available.
    Falls back to template if not configured.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = (
        "You are a grid operations analyst. Given the following JSON data from a "
        "24-hour grid load-balancing simulation for 3 US states (CA, TX, NY), "
        "write a concise executive summary (5-10 bullet points) highlighting:\n"
        "- Overall reliability (unserved energy)\n"
        "- Renewable performance\n"
        "- Key risks and stress events\n"
        "- Top infrastructure recommendations\n\n"
        f"Data:\n{context_str}"
    )

    response = model.generate_content(prompt)
    return response.text


def _template_summary(kpis: KPIs, recs, stress_events) -> str:
    """Fallback template-based summary (no LLM needed)."""
    lines = []
    if kpis.total_unserved_mwh < 1:
        lines.append("- All load was served with zero unserved energy — excellent reliability.")
    else:
        lines.append(f"- {kpis.total_unserved_mwh:,.1f} MWh of unserved energy detected — reliability at risk.")

    lines.append(f"- Renewable utilization: {kpis.renewable_utilization:.1%} of available renewable generation was used.")

    if kpis.total_curtailment_mwh > 0:
        lines.append(f"- {kpis.total_curtailment_mwh:,.1f} MWh of renewable energy was curtailed.")

    lines.append(f"- Fuel fallback: {kpis.total_fuel_mwh:,.1f} MWh of fossil fuel was dispatched.")

    critical = [e for e in stress_events if e.get("severity") == "critical"]
    if critical:
        lines.append(f"- {len(critical)} critical stress events (unserved energy) detected.")
    else:
        lines.append("- No critical stress events detected.")

    if recs:
        lines.append(f"- Top recommendation: {recs[0].description}")

    return "\n".join(lines)
