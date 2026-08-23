#!/usr/bin/env bash

set -euo pipefail

echo "Formatting $PWD"

ROOT=$(git rev-parse --show-toplevel)
readonly ROOT
cd -- "$ROOT" || exit 1

readarray -t FILES <<<"$(find "$ROOT/tests" "$ROOT/lancet" -type f -iname '*.py')"
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

pyupgrade --py313-plus "${FILES[@]}"
isort "${FILES[@]}"
black "${FILES[@]}"
