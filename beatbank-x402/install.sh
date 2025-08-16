#!/bin/bash

# Exit if any command fails
set -e

echo "🧼 Cleaning old venv (if any)..."
rm -rf venv

echo "🐍 Creating Python 3.11 virtual environment..."
/opt/homebrew/opt/python@3.11/bin/python3.11 -m venv venv
source venv/bin/activate

echo "⬆️ Upgrading pip + build tools..."
pip install --upgrade pip setuptools wheel cython

echo "☕ Setting JAVA_HOME for JDK 21..."
export JAVA_HOME="$(/usr/libexec/java_home -v21)"
export PATH="$JAVA_HOME/bin:$PATH"
export CPPFLAGS="-I$JAVA_HOME/include"

echo "📦 Installing requirements..."
pip install -r requirements.txt

echo "✅ Done! Python $(python --version), Java $(java -version)"

