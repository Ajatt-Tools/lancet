#!/usr/bin/env bash

set -euo pipefail

echo "Formatting $PWD"

ROOT=$(git rev-parse --show-toplevel)
readonly ROOT
cd -- "$ROOT" || exit 1

mapfile -d '' -t FILES < <(find "$ROOT/tests" "$ROOT/lancet" -type f -iname '*.py' -print0)
readonly -a FILES

is_installed() {
	[[ -x $(command -v "$1") ]]
}

for prog in pyupgrade isort black; do
	if ! is_installed "$prog"; then
		echo "command not found: $prog"
		exit 1
	fi
done

# Successful rewrites must not stop fix mode before isort and Black run.
pyupgrade --exit-zero-even-if-changed --py313-plus "${FILES[@]}"
isort "${FILES[@]}"
black "${FILES[@]}"
