#!/usr/bin/env bash
# Run an e2e sweep on the box and bring the report back.
#
#   ./tools/e2e/run.sh cases.json            # results land in work/e2e/
#
# Takes over the TV for roughly a minute per case, so run it when the box is
# idle - the probe refuses any case that starts with something already playing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CASES="${1:?usage: run.sh <cases.json>}"
OUT="${2:-$HERE/../../work/e2e}"
mkdir -p "$OUT"

"$HERE/../box" 'cat > /storage/e2e-probe.py' < "$HERE/probe.py"
"$HERE/../box" 'cat > /storage/e2e-cases.json' < "$CASES"
"$HERE/../box" 'cd /storage && python3 e2e-probe.py e2e-cases.json e2e-report.json' \
  | tee "$OUT/run.log"
"$HERE/../box" 'python3 -c "import sys;sys.stdout.write(open(\"/storage/e2e-report.json\").read())"' \
  > "$OUT/report.json"
"$HERE/../box" 'rm -f /storage/e2e-probe.py /storage/e2e-cases.json /storage/e2e-report.json'

python3 "$HERE/report.py" "$OUT/report.json" | tee "$OUT/report.md"
