"""
Agentfield reasoners for the Grid Load-Balancing MVP.

Exposes two reasoners:
  - grid_run_grid_mvp  : runs the full pipeline, returns KPIs + output paths
  - grid_explain_run   : (optional) generates a Gemini-powered narrative from logs
"""
import os
import json
from pathlib import Path
from agentfield import AgentRouter
from pydantic import BaseModel, Field

from src.agents.orchestrator import run_pipeline
from src.utils.helpers import LOGS_DIR, REPORTS_DIR, read_json

grid_router = AgentRouter(prefix="grid", tags=["grid-balance"])


# ---------- Reasoner 1: run_grid_mvp ----------

@grid_router.reasoner()
async def run_grid_mvp(
    start_hour: int = 0,
    horizon: int = 24,
    enable_llm: bool = False,
) -> dict:
    """
    Run the full grid load-balancing pipeline.

    Returns dispatch schedule paths, summary KPIs, and recommendation count.

    Example:
      curl -X POST http://localhost:8080/api/v1/execute/grid-balance-agent.grid_run_grid_mvp \\
        -H "Content-Type: application/json" \\
        -d '{"input": {"start_hour": 0, "horizon": 24, "enable_llm": false}}'
    """
    result = run_pipeline(
        start_hour=start_hour,
        horizon=horizon,
        enable_llm=enable_llm,
    )

    grid_router.app.note(
        f"Pipeline complete: unserved={result['kpis']['total_unserved_mwh']} MWh, "
        f"fuel={result['kpis']['total_fuel_mwh']} MWh, "
        f"renewable_util={result['kpis']['renewable_utilization']}",
        tags=["pipeline", "kpis"],
    )

    return result


# ---------- Reasoner 2: explain_run (LLM-powered, disabled by default) ----------

class RunExplanation(BaseModel):
    """Structured LLM output for explaining a grid run."""
    summary_bullets: list[str] = Field(description="5-10 bullet points summarizing the run")
    risk_level: str = Field(description="low, medium, or high")
    top_action: str = Field(description="Most impactful recommended action")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the assessment")


@grid_router.reasoner()
async def explain_run() -> dict:
    """
    Generate a human-friendly narrative from the most recent run logs.
    Uses Gemini if available; otherwise returns a template-based summary.

    This reasoner is optional and should only be called when LLM summaries
    are desired. It reads from logs/kpis.json and logs/recommendations.json.

    Example:
      curl -X POST http://localhost:8080/api/v1/execute/grid-balance-agent.grid_explain_run \\
        -H "Content-Type: application/json" \\
        -d '{"input": {}}'
    """
    kpis_path = LOGS_DIR / "kpis.json"
    recs_path = LOGS_DIR / "recommendations.json"

    if not kpis_path.exists():
        return {"error": "No run logs found. Run the pipeline first via run_grid_mvp."}

    kpis = read_json(kpis_path)
    recs = read_json(recs_path) if recs_path.exists() else []

    context = json.dumps({"kpis": kpis, "top_recommendations": recs[:3]}, indent=2)

    # Try LLM-powered explanation
    llm_enabled = os.environ.get("ENABLE_LLM_SUMMARY", "false").lower() == "true"

    if llm_enabled and grid_router.app.ai_config is not None:
        try:
            result = await grid_router.ai(
                system=(
                    "You are a grid operations analyst. Given JSON data from a "
                    "24-hour grid simulation for 3 US states (CA, TX, NY), provide "
                    "a concise executive summary."
                ),
                user=(
                    f"Analyze this grid simulation output and provide 5-10 bullet points "
                    f"covering reliability, renewable performance, risks, and recommendations.\n\n"
                    f"{context}"
                ),
                schema=RunExplanation,
            )

            grid_router.app.note(
                f"LLM explanation generated: risk_level={result.risk_level}",
                tags=["explain", "llm"],
            )

            return result.model_dump()
        except Exception as e:
            # Fall through to template
            pass

    # Template fallback (no LLM needed)
    bullets = _template_bullets(kpis, recs)
    return {
        "summary_bullets": bullets,
        "risk_level": "high" if kpis.get("total_unserved_mwh", 0) > 0 else "low",
        "top_action": recs[0]["description"] if recs else "No recommendations",
        "confidence": 0.8,
        "source": "template",
    }


def _template_bullets(kpis: dict, recs: list) -> list:
    bullets = []
    unserved = kpis.get("total_unserved_mwh", 0)
    if unserved < 1:
        bullets.append("All load served with zero unserved energy — excellent reliability.")
    else:
        bullets.append(f"{unserved:,.1f} MWh of unserved energy — reliability at risk.")

    bullets.append(
        f"Renewable utilization: {kpis.get('renewable_utilization', 0):.1%} of available generation used."
    )

    curt = kpis.get("total_curtailment_mwh", 0)
    if curt > 0:
        bullets.append(f"{curt:,.1f} MWh of renewable energy curtailed.")

    fuel = kpis.get("total_fuel_mwh", 0)
    bullets.append(f"Fossil fuel dispatch: {fuel:,.1f} MWh.")

    if recs:
        bullets.append(f"Top recommendation: {recs[0].get('description', 'N/A')}")
        score = recs[0].get("kpi_deltas", {}).get("score_delta", 0)
        if score < 0:
            bullets.append(f"  -> Estimated penalty reduction: {abs(score):,.0f} points.")

    return bullets
