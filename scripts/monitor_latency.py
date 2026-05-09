import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT_S = 300

ISTAT_BASE = "https://esploradati.istat.it/SDMXWS/rest"
ESTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"

# (url, download_body_for_row_count)
CALLS = [
    ("istat", "41_269_DF_DCIS_INCIDENTISTR1_1", "info",
     f"{ISTAT_BASE}/dataflow/IT1/41_269_DF_DCIS_INCIDENTISTR1_1/1.0",
     False),
    ("istat", "41_269_DF_DCIS_INCIDENTISTR1_1", "get",
     f"{ISTAT_BASE}/data/41_269_DF_DCIS_INCIDENTISTR1_1"
     f"/A.082053+092009+118006.....1...?startPeriod=2022&endPeriod=2023",
     False),  # ISTAT returns XML — row count not applicable
    ("eurostat", "TRAN_SF_ROADNU", "info",
     f"{ESTAT_BASE}/dataflow/ESTAT/TRAN_SF_ROADNU/1.0?detail=allstubs&references=none",
     False),
    ("eurostat", "TRAN_SF_ROADNU", "get",
     f"{ESTAT_BASE}/data/TRAN_SF_ROADNU/A..ITG12+ITG27/"
     f"?startPeriod=2022&endPeriod=2023&format=SDMX-CSV",
     True),  # CSV — count rows
]

OUTPUT_FILE = Path("output/latency.jsonl")


def run_curl(provider, dataset_id, call_type, url, download_body):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fmt = "%{http_code}|%{time_total}|%{size_download}"

    if download_body:
        cmd = ["curl", "-s", "--max-time", str(TIMEOUT_S), "-w", f"\n{fmt}", url]
    else:
        cmd = ["curl", "-s", "-o", "/dev/null", "--max-time", str(TIMEOUT_S), "-w", fmt, url]

    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S + 10)
        duration = round(time.monotonic() - start, 3)

        if result.returncode == 28:  # curl --max-time exceeded
            return {"ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                    "duration_s": duration, "status": "timeout",
                    "http_code": None, "n_rows": None, "error": f"timeout after {TIMEOUT_S}s"}

        lines = result.stdout.strip().splitlines()
        parts = (lines[-1] if lines else "").split("|")
        if len(parts) != 3:
            return {"ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                    "duration_s": duration, "status": "error",
                    "http_code": None, "n_rows": None, "error": f"unexpected output: {result.stdout!r}"}

        http_code = int(parts[0])
        size_bytes = int(float(parts[2]))
        status = "ok" if 200 <= http_code < 300 else "error"

        n_rows = None
        if download_body and status == "ok":
            body = [l for l in lines[:-1] if l]
            n_rows = max(0, len(body) - 1)

        return {"ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                "duration_s": duration, "status": status,
                "http_code": http_code, "n_rows": n_rows,
                "error": None if status == "ok" else f"HTTP {http_code}"}
    except subprocess.TimeoutExpired:
        duration = round(time.monotonic() - start, 3)
        return {"ts": ts, "provider": provider, "dataset": dataset_id, "call": call_type,
                "duration_s": duration, "status": "timeout",
                "http_code": None, "n_rows": None, "error": f"subprocess timeout after {TIMEOUT_S + 10}s"}


PAUSE_S = 15  # between calls — respects ISTAT rate limit (5 req/min)


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    results = []

    for i, (provider, dataset_id, call_type, url, download_body) in enumerate(CALLS):
        if i > 0:
            time.sleep(PAUSE_S)
        record = run_curl(provider, dataset_id, call_type, url, download_body)
        results.append(record)
        print(json.dumps(record), flush=True)

    with open(OUTPUT_FILE, "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
