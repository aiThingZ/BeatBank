#!/bin/bash

# Exit on error
set -e

# Activate virtual environment
source ./venv/bin/activate

# Set JAVA_HOME properly for Pyjnius
export JAVA_HOME=$(/usr/libexec/java_home -v21)
export PATH="$JAVA_HOME/bin:$PATH"
export DYLD_LIBRARY_PATH="$JAVA_HOME/lib/server:$DYLD_LIBRARY_PATH"

# Run the Hedera topic creation
python test_publish.py

