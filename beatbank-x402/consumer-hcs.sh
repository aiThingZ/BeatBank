#!/bin/bash

# Activate virtual environment
source ./venv/bin/activate

export JAVA_TOOL_OPTIONS="--enable-native-access=ALL-UNNAMED"

python consumer_hcs.py
