#!/bin/bash

set -euo pipefail

echo "Formatting $PWD"

ROOT=$(git rev-parse --show-toplevel)
readonly ROOT
readarray -t FILES <<<"$(find "$ROOT" -type f -iname '*.py')"
readonly -a FILES

pyupgrade --py313-plus "${FILES[@]}"
isort "${FILES[@]}"
black "${FILES[@]}"
