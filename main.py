import os
import sys
from dotenv import load_dotenv
from agentfield import Agent, AIConfig

# Ensure project root is on path so src/ package resolves
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

from reasoners import grid_router

# AI config is optional — only used if ENABLE_LLM_SUMMARY=true
ai_config = None
if os.environ.get("ENABLE_LLM_SUMMARY", "false").lower() == "true":
    ai_config = AIConfig(
        model="gemini/gemini-2.0-flash",
        temperature=0.3,
    )

app = Agent(
    node_id="grid-balance-agent",
    agentfield_server=os.environ.get("AGENTFIELD_SERVER", "http://localhost:8080"),
    version="1.0.0",
    dev_mode=True,
    ai_config=ai_config,
)

app.include_router(grid_router)

if __name__ == "__main__":
    app.serve(auto_port=True, dev=True, reload=False)
