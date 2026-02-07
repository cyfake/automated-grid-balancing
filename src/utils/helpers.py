"""Shared helpers."""
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
LOGS_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"
RUNS_DIR = PROJECT_ROOT / "runs"


def ensure_dirs():
    for d in [DATA_RAW, DATA_PROCESSED, LOGS_DIR, REPORTS_DIR, RUNS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def read_json(path):
    with open(path) as f:
        return json.load(f)
