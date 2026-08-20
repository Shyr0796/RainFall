#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 validation/experiments/04_infiltration_runoff/code/run_validation.py 2>&1 | tee validation/experiments/04_infiltration_runoff/logs/run.log
