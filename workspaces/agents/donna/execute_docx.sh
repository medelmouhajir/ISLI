#!/bin/bash
set -e

# Create a temporary virtual environment
python3 -m venv /tmp/docx_venv
source /tmp/docx_venv/bin/activate

# Install python-docx
pip install --quiet python-docx

# Run the generator
python create_docx.py

# Deactivate
deactivate

echo "Renter_Marketing_Demo.docx generated successfully."
