#!/usr/bin/env bash

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
readonly ROOT
cd -- "$ROOT" || exit 1

echo "Using $(python --version)"

echo "Cleaning up old build artifacts..."
rm -rf -- dist/ build/

echo "Creating .venv..."
python -m venv .venv

echo "Activating .venv..."
source .venv/bin/activate

echo "Installing build dependencies..."
"$ROOT"/scripts/install-build-deps.sh

echo "Building PyInstaller binary..."
"$ROOT"/scripts/build-binary.sh

echo ""
echo "Build complete. Binary stored in ./dist"
echo "Binary size:"
du -sh dist/*
