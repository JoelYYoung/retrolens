#!/usr/bin/env bash
# Install retrolens CLI tool.
#
# Usage:
#   bash scripts/setup.sh
#
# This installs the retrolens package from PyPI, which provides
# the `retrolens` CLI command used by this skill.

set -euo pipefail

echo "Installing retrolens..."

if command -v uv &>/dev/null; then
    uv pip install retrolens
elif command -v pip &>/dev/null; then
    pip install retrolens
elif command -v pip3 &>/dev/null; then
    pip3 install retrolens
else
    echo "Error: No Python package manager found (uv, pip, or pip3)"
    echo "Install Python first: https://www.python.org/downloads/"
    exit 1
fi

echo "Verifying installation..."
retrolens --version

echo "Done! Run 'retrolens --help' to get started."
