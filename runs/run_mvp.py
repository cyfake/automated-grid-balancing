#!/usr/bin/env python3
"""
run_mvp.py — Entry point for the Grid Load-Balancing MVP.

Usage:
    python runs/run_mvp.py                     # default: no LLM
    python runs/run_mvp.py --enable-llm        # with Gemini summary
    python runs/run_mvp.py --start-hour 0 --horizon 24
"""
import argparse
import os
import sys
import json

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env (EIA_API_KEY, ENABLE_LLM_SUMMARY, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell-exported env vars

from src.agents.orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Grid Load-Balancing MVP")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Path to processed CSV directory (default: data/processed/)",
    )
    parser.add_argument(
        "--start-hour",
        type=int,
        default=0,
        help="Starting hour index in the data (default: 0)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=24,
        help="Planning horizon in hours (default: 24)",
    )
    parser.add_argument(
        "--enable-llm",
        action="store_true",
        default=False,
        help="Enable Gemini LLM summary (default: disabled)",
    )
    args = parser.parse_args()

    # Env var override for LLM
    enable_llm = args.enable_llm or os.environ.get("ENABLE_LLM_SUMMARY", "false").lower() == "true"

    print("=" * 60)
    print("  Grid Load-Balancing MVP")
    print("  Autonomous 24h Dispatch + Recommendations")
    print("=" * 60)
    print(f"  Start hour: {args.start_hour}")
    print(f"  Horizon:    {args.horizon}h")
    print(f"  LLM:        {'enabled' if enable_llm else 'disabled'}")
    print("=" * 60)
    print()

    result = run_pipeline(
        data_dir=args.data_dir,
        start_hour=args.start_hour,
        horizon=args.horizon,
        enable_llm=enable_llm,
    )

    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
