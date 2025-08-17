#!/bin/bash

# Activate virtual environment
source ./venv/bin/activate

export JAVA_TOOL_OPTIONS="--enable-native-access=ALL-UNNAMED"

python worker_hcs_bash.py
#python consumer_hcs.py
#python client_upload_and_wait.py
