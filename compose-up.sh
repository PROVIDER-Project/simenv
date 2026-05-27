#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <path-to-pdl-file> [docker compose args...]" >&2
  echo "Example: $0 src/provider_simenv/scenarios/s1-soja.pdl.yaml" >&2
  exit 1
fi

pdl_input="$1"
shift || true

if [[ ! -f "$pdl_input" ]]; then
  echo "Error: PDL file not found: $pdl_input" >&2
  exit 1
fi

pdl_abs="$(cd "$(dirname "$pdl_input")" && pwd)/$(basename "$pdl_input")"
export PDL_DIR="$(dirname "$pdl_abs")"
export PDL_FILE="$(basename "$pdl_abs")"

# Start postgres and simulation. The postgres named volume keeps DB data across runs.
docker compose up simenv "$@"
