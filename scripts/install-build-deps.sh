#!/usr/bin/env bash

# Installs build time dependencies for producing the PyInstaller binary.
# Used by the GitHub Actions release workflow.

# Installs CPU only torch from PyTorch's CPU index to avoid pulling ~2.7 GB
# of CUDA libraries that would otherwise be bundled into the binary.

set -euo pipefail

# Clear pip cache to avoid corruption issues
python -m pip cache purge

python -m pip install --upgrade pip

# Install CPU only torch and torchvision from PyTorch's CPU index
# to avoid CUDA deps and ensure torchvision ops (e.g., nms) are available.
python -m pip install --index-url 'https://download.pytorch.org/whl/cpu' torch torchvision
# Now install the project. pip sees torch and torchvision already satisfied.
python -m pip install --group="binary" --extra-index-url 'https://pypi.org/simple' .
