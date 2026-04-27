#!/usr/bin/env bash

# Installs build time dependencies for producing the PyInstaller binary.
# Used by the GitHub Actions release workflow.

# Installs CPU only torch from PyTorch's CPU index to avoid pulling ~2.7 GB
# of CUDA libraries that would otherwise be bundled into the binary.

set -euo pipefail

python -m pip install --upgrade pip
python -m pip install pyinstaller
# Install CPU only torch first to avoid CUDA deps.
python -m pip install --index-url 'https://download.pytorch.org/whl/cpu' torch
# Now install the project; pip sees torch already satisfied and skips it.
python -m pip install --extra-index-url 'https://pypi.org/simple' .
