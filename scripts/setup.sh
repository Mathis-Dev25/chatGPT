#!/usr/bin/env bash
# Installation reproductible Linux/macOS, sans changer les fichiers du projet.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python -m pip check
