import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT_S = 300

DATASETS = {
    "istat": {
        "id": "41_269_DF_DCIS_INCIDENTISTR1_1",
        "provider_flag": ["--provider", "istat"],
        "get_args": ["--FREQ", "A", "--REF_AREA", "082053", "--Y_DEADLY_ACCIDENT", "1", "--last-n", "1"],
        "has_constraints": False,
    },
    "eurostat": {
        "id": "TRAN_SF_ROADNU",
        "provider_flag": [],
        "get_args": ["--freq", "A", "--geo", "ITG12+ITG27", "--last-n", "1"],
        "has_constraints": True,
    },
}

OUTPUT_FILE = Path("output/latency.jsonl")


def run_call(call_type, provider, dataset_id, provider_flag, extra_args=None):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if call_type == "info":
        cmd = ["opensdmx", "info", dataset_id] + provider_flag
    elif call_type == "constraints":
        cmd = ["opensdmx", "constraints", dataset_id] + provider_flag
    elif call_type == "get":
        cmd = ["opensdmx", "--output", "csv", "get", dataset_id] + (extra_args or []) + provider_flag

    env = os.environ.copy()
    if call_type == "constraints":
        env["OPENSDMX_AVAILCONSTRAINT_TIMEOUT"] = str(TIMEOUT_S)

    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env)
        duration = round(time.monotonic() - start, 3)

        if result.returncode == 0:
            n_rows = None
            if call_type == "get":
                lines = [line for line in result.stdout.strip().splitlines() if line]
                n_rows = max(0, len(lines) - 1)
            return {
                "ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                "duration_s": duration, "status": "ok", "n_rows": n_rows, "error": None,
            }
        else:
            err = (result.stderr or "").strip()
            status = "timeout" if "timed out" in err.lower() else "error"
            return {
                "ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                "duration_s": duration, "status": status, "n_rows": None,
                "error": err[:300] if err else f"exit {result.returncode}",
            }
    except subprocess.TimeoutExpired:
        duration = round(time.monotonic() - start, 3)
        return {
            "ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
            "duration_s": duration, "status": "timeout", "n_rows": None,
            "error": f"subprocess timeout after {TIMEOUT_S}s",
        }


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    results = []

    for provider, config in DATASETS.items():
        for call_type in ["info", "constraints", "get"]:
            if call_type == "constraints" and not config.get("has_constraints"):
                continue
            extra = config["get_args"] if call_type == "get" else None
            record = run_call(call_type, provider, config["id"], config["provider_flag"], extra)
            results.append(record)
            print(json.dumps(record), flush=True)

    with open(OUTPUT_FILE, "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
