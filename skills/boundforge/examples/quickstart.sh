#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
DB="${1:-/tmp/boundforge-demo-$$.db}"
REGISTRY="${2:-$PWD/examples/model_registry.json}"
run() { python -m boundforge --db "$DB" "$@"; }
run init --registry "$REGISTRY" --model-index 2 --problem 'A=inf_{x>0} (2+1/x)' --inner 75 --outer 85 --max-work-minutes 90
D=$(run direction --name 'Elementary inequality' --why 'Check direct lower and asymptotic upper' | python -c 'import sys,json; print(json.load(sys.stdin)["result"])')
E=$(run episode-start --direction "$D" --role researcher --why 'Pilot proof construction' | python -c 'import sys,json;print(json.load(sys.stdin)["result"])')
W=$(run work-start --episode "$E" --actor example-gpt-model --action 'prove lower bound' | python -c 'import sys,json;print(json.load(sys.stdin)["result"])')
L=$(run submit --episode "$E" --actor example-gpt-model --kind lower --value 2 --statement 'inf f >= 2' --artifact examples/proof_lower.txt | python -c 'import sys,json;print(json.load(sys.stdin)["result"])')
run review --claim "$L" --verifier example-gpt-model --decision accept --level self_check
U=$(run submit --episode "$E" --actor example-gpt-model --kind upper --value 2 --statement 'inf f <= 2 via x_n=n' --artifact examples/proof_upper.txt | python -c 'import sys,json;print(json.load(sys.stdin)["result"])')
run review --claim "$U" --verifier example-gpt-model --decision accept --level self_check
run work-end --work "$W" --actor example-gpt-model --outcome 'Direct arguments checked; recorded endpoints match'
run decide
run episode-end --episode "$E" --why 'Optimum established under toy assumptions'
run finalize
run verify-ledger
printf '\nDemo database: %s\n' "$DB"
