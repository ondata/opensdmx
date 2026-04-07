#!/usr/bin/env bash
# probe_providers.sh — test constraints and last_n for all built-in providers
#
# Usage:
#   bash scripts/probe_providers.sh
#   bash scripts/probe_providers.sh --update   # update portals.json after review
#
# Output: tmp/provider-capabilities.json
#
# After running, review the results and update portals.json manually or with --update.

set -uo pipefail

REPORT="tmp/provider-capabilities.json"
mkdir -p tmp

# One small/reliable probe dataflow per provider.
# If a provider is missing here, the script will try 'opensdmx search GDP --n 1'.
declare -A PROBES=(
  [eurostat]="TEC00115"
  [istat]="151_929"
  [ecb]="EXR"
  [oecd]="DSD_NAMAIN10@DF_TABLE1_EXPENDITURE_GROWTH"
  [insee]="CNA-2010-PIB"
  [bundesbank]="BBSEI"
  [worldbank]="DF_WITS_TradeStats_Tariff"
  [abs]="ANA_EXP"
  [bis]="WS_CREDIT_GAP"
  [imf]="WEO"
)

PROVIDERS=(eurostat istat ecb oecd insee bundesbank worldbank abs bis imf)

# ── helpers ──────────────────────────────────────────────────────────────────

test_constraints() {
  local provider="$1" probe="$2"
  if opensdmx constraints "$probe" --provider "$provider" > /dev/null 2>&1; then
    echo "true"
  else
    echo "false"
  fi
}

test_last_n() {
  local provider="$1" probe="$2"
  # Pass --last-n 1 with no other filters; check for explicit "not supported" error.
  local out
  out=$(opensdmx get "$probe" --provider "$provider" --last-n 1 2>&1) || true
  if echo "$out" | grep -qi "not supported\|lastNObservations\|unsupported"; then
    echo "false"
  elif echo "$out" | grep -q "TIME_PERIOD\|OBS_VALUE"; then
    echo "true"
  else
    # Unknown: request failed for another reason (dataset not found, timeout, etc.)
    echo "null"
  fi
}

# ── main loop ─────────────────────────────────────────────────────────────────

echo "opensdmx provider capability probe"
echo "==================================="
echo ""

results=()

for provider in "${PROVIDERS[@]}"; do
  probe="${PROBES[$provider]:-}"

  # Fallback: search for any dataset
  if [[ -z "$probe" ]]; then
    probe=$(opensdmx search "GDP" --provider "$provider" 2>/dev/null \
      | awk '/^│/ && !/df_id/ { gsub(/^│[[:space:]]+/, ""); gsub(/[[:space:]]+.*/, ""); print; exit }')
  fi

  if [[ -z "$probe" ]]; then
    printf "%-12s  probe: not found — skipping\n" "$provider"
    results+=("  {\"provider\": \"$provider\", \"probe\": null, \"constraints\": null, \"last_n\": null}")
    continue
  fi

  printf "%-12s  probe: %-50s  " "$provider" "$probe"

  constraints=$(test_constraints "$provider" "$probe")
  last_n=$(test_last_n "$provider" "$probe")

  c_icon=$([ "$constraints" = "true" ] && echo "✓" || ([ "$constraints" = "false" ] && echo "✗" || echo "?"))
  l_icon=$([ "$last_n" = "true" ] && echo "✓" || ([ "$last_n" = "false" ] && echo "✗" || echo "?"))

  printf "constraints: %s   last_n: %s\n" "$c_icon" "$l_icon"

  results+=("  {\"provider\": \"$provider\", \"probe\": \"$probe\", \"constraints\": $constraints, \"last_n\": $last_n}")
done

# ── write report ──────────────────────────────────────────────────────────────

{
  echo "["
  for i in "${!results[@]}"; do
    if [[ $i -lt $((${#results[@]} - 1)) ]]; then
      echo "${results[$i]},"
    else
      echo "${results[$i]}"
    fi
  done
  echo "]"
} > "$REPORT"

echo ""
echo "Report saved to $REPORT"
echo ""
echo "Review results, then update portals.json:"
echo "  constraints_supported: true/false"
echo "  last_n_supported: true/false"
