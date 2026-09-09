#!/usr/bin/env bash
# One-time local setup: a virtual environment plus the one external dependency.
#
# The analysis pipeline itself is pure standard library, so this script exists
# only for the GRIB wind decoding. If eccodes fails to build on your machine,
# everything except `wind_grib.py` still runs.
set -uo pipefail

cd "$(dirname "$0")/.."
echo "Repo: $(pwd)"

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
if ! command -v $PY >/dev/null 2>&1; then
  echo "ERROR: no python3 on PATH. Install Python 3.9+ from python.org and re-run." >&2
  exit 1
fi

echo "Python: $($PY --version)"
$PY - <<'EOF' || exit 1
import sys
if sys.version_info < (3, 9):
    sys.exit(f"ERROR: Python 3.9+ required, found {sys.version.split()[0]}")
EOF

if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  $PY -m venv .venv || { echo "ERROR: could not create the virtualenv." >&2; exit 1; }
else
  echo ".venv already exists, reusing it"
fi

# shellcheck disable=SC1091
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
else
  source .venv/Scripts/activate   # Git Bash on Windows
fi

python -m pip install --quiet --upgrade pip

echo "Installing eccodes (for the wind GRIBs) ..."
if python -m pip install --quiet eccodes; then
  python - <<'EOF'
import eccodes
print(f"  eccodes OK, version {eccodes.codes_get_api_version()}")
EOF
else
  cat >&2 <<'EOF'
  eccodes did NOT install. This is not fatal:
  everything except the wind GRIB decoding still works.
  On macOS try:  brew install eccodes  then re-run this script.
EOF
fi

cat <<'EOF'

Setup done. Next:

    bash local-setup/run_all.sh

To run individual commands, activate the venv first:

    source .venv/bin/activate        # Windows: .venv\Scripts\activate
EOF
