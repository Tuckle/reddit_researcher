#!/bin/bash

# Activation script for the Reddit Researcher virtual environment
# Usage: source activate_env.sh

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate the virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

echo "✅ Reddit Researcher virtual environment activated!"
echo "📁 Project directory: $SCRIPT_DIR"
echo ""
echo "Available scripts:"
echo "  • Streamlit app: streamlit run app/streamlit_app.py"
echo "  • Ingestor: python ingestor/ingest.py"
echo "  • Pipeline: python scheduler/run_pipeline.py"
echo "  • Test environment: python test_environment.py"
echo ""
echo "To deactivate: deactivate"
