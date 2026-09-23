#!/bin/sh
# Mutation testing (mutmut): the code is changed in thousands of small ways and the tests run against each change;
# a change no test notices ("survived") marks behaviour nothing checks. Writes OUT_DIR/mutation.md (totals and per
# module) and the raw results. mutmut, the latest from PyPI, goes into a throwaway venv; the job holds no secret.
# Usage: scripts/mutation.sh OUT_DIR
set -eu
cd "$(dirname "$0")/.."
out="${1:?usage: scripts/mutation.sh OUT_DIR}"
mkdir -p "$out"
venv="$(mktemp -d)"
python -m venv --system-site-packages "$venv"
"$venv/bin/pip" install --quiet --disable-pip-version-check mutmut
"$venv/bin/mutmut" run --max-children "$(nproc)" > "$out/mutmut.log" 2>&1
"$venv/bin/mutmut" results --all true > "$out/results.txt"
python3 - "$out" <<'PY'
import collections, sys
from pathlib import Path

out = Path(sys.argv[1])
per_module = collections.defaultdict(collections.Counter)
for line in (out / "results.txt").read_text().splitlines():
    name, _, status = line.strip().rpartition(": ")
    if name:
        per_module[name.split(".")[1] if name.count(".") else name][status] += 1
total = sum(per_module.values(), collections.Counter())

def score(c):
    tested = c["killed"] + c["survived"] + c["timeout"]
    return f"{100 * (c['killed'] + c['timeout']) / tested:.0f}%" if tested else "—"

rows = ["| Module | Caught | Survived | No test reaches it | Score |", "|---|---|---|---|---|"]
for module, c in sorted(per_module.items(), key=lambda kv: -sum(kv[1].values())):
    rows.append(f"| `{module}` | {c['killed'] + c['timeout']} | {c['survived']} | {c['no tests']} | {score(c)} |")
rows.append(f"| **all** | {total['killed'] + total['timeout']} | {total['survived']} | {total['no tests']} | {score(total)} |")
(out / "mutation.md").write_text(
    "## Mutation testing (mutmut)\n\nScore = changes the tests caught, over the changes some test runs. "
    "The GTK frontend and the command line are exercised by desktop and subprocess tests mutmut cannot follow.\n\n"
    + "\n".join(rows) + "\n"
)
print((out / "mutation.md").read_text())
PY
