#!/usr/bin/env bash
# Regenerate every report from the raw files.
#
# To add a race day: drop the files in place, change the dates below, re-run.
set -uo pipefail

# ---- edit these for a new race day -------------------------------------------
ABANDONED_DATE="2026-09-07"   # the day the race was not sailed to a finish
RACED_DATE="2026-09-08"       # a day of completed races
WIND_DEG=325                  # estimated wind direction, for labelling legs
# ------------------------------------------------------------------------------

cd "$(dirname "$0")/.."

# Use the venv if it exists; the analysis works without it, only the wind
# commands need eccodes.
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
fi
PY=$(command -v python || command -v python3)

step() { printf '\n=== %s\n' "$1"; }

step "1/5  Per-boat legs, abandoned race ($ABANDONED_DATE)"
"$PY" -m src.sailing_agents.report "data/raw/team/team_${ABANDONED_DATE}.vkx" || true

step "2/5  Start line and wind from geometry ($ABANDONED_DATE)"
"$PY" -m src.sailing_agents.start_line_report \
  --team "data/raw/team/team_${ABANDONED_DATE}.vkx" \
  --competitors "data/raw/competitors/*.vkx" \
  --json-out "reports/start_line_analysis.json" \
  --html-out "dashboard/start_line_section.html" || true

step "3/5  Fleet report, completed races ($RACED_DATE)"
"$PY" -m src.sailing_agents.fleet_report \
  --team "data/raw/team/team_${RACED_DATE}.vkx" \
  --competitors "data/raw/competitors_${RACED_DATE}/*.vkx" \
  --wind-deg "$WIND_DEG" \
  -o "reports/${RACED_DATE}_fleet_report.json" || true

step "4/5  Wind GRIBs ($RACED_DATE) - needs eccodes"
if [ -d "data/wind/${RACED_DATE}/icon-eu-06z" ]; then
  "$PY" -m src.sailing_agents.wind_grib \
    --icon-dir "data/wind/${RACED_DATE}/icon-eu-06z" \
    --ecmwf-dir "data/wind/${RACED_DATE}/ecmwf-ifs-06z" \
    --fleet-report "reports/${RACED_DATE}_fleet_report.json" \
    -o "reports/${RACED_DATE}_wind.json" \
    --html-out "dashboard/wind_section.html" \
    || echo "  skipped (eccodes missing? see local-setup/README.md)"
else
  echo "  no GRIBs for ${RACED_DATE}, skipping"
fi

step "5/5  Analyser digest"
"$PY" -m src.sailing_agents.digest \
  "reports/${ABANDONED_DATE}_race_comparison_raw.json" \
  --start-line "reports/start_line_analysis.json" \
  --fleet-report "reports/${RACED_DATE}_fleet_report.json" \
  --wind "reports/${RACED_DATE}_wind.json" \
  --day-label "day_${RACED_DATE//-/_}" \
  -o "reports/analyser_digest.json" || true

cat <<EOF

Done. Written to reports/:
$(ls -1 reports/ 2>/dev/null | sed 's/^/  /')

The written debriefs are the markdown files in reports/.
Open docs/index.html in a browser for the dashboard.
EOF
