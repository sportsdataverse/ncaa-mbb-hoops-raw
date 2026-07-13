#!/usr/bin/env bash
# User-run launcher: parse captured raw bundles -> combined per-contest JSON.
# Fully offline (reads local raw/*.json.gz only) -- no proxy creds needed.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1   # -> ncaa-mbb-hoops-raw repo root
ROOT="$(pwd)"
SDV_PY="C:/Users/saiem/Documents/GitHub-Data/sdv-dev/sdv-py"

export PYTHONPATH="${SDV_PY}:${ROOT}/python"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

mkdir -p logs
LOG="logs/parse_$(date +%Y%m%d_%H%M%S).log"
echo "log -> ${LOG}  (watch: tail -f ${LOG})"
"${SDV_PY}/.venv/Scripts/python.exe" python/ncaa_parse.py "$@" 2>&1 | tee -a "${LOG}"
echo "EXIT=${PIPESTATUS[0]}" | tee -a "${LOG}"
