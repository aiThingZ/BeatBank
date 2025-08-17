#!/bin/bash

# Exit on any error
set -e

echo "🧼 Cleaning old venv (if any)..."
rm -rf venv

echo "📦 Updating apt and installing required dependencies..."
sudo apt update
sudo apt install -y software-properties-common

# Add deadsnakes PPA if not already present
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update

# Install Python 3.11 and Java 21
sudo apt install -y \
  python3.11 \
  python3.11-venv \
  python3.11-dev \
  openjdk-21-jdk \
  build-essential \
  curl \
  unzip

echo "🐍 Creating Python 3.11 virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

echo "⬆️ Upgrading pip + build tools..."
pip install --upgrade pip setuptools wheel cython

echo "☕ Setting JAVA_HOME for JDK 21..."
export JAVA_HOME="/usr/lib/jvm/java-21-openjdk-amd64"
export PATH="$JAVA_HOME/bin:$PATH"
export CPPFLAGS="-I$JAVA_HOME/include"

echo "📦 Installing Python requirements..."
pip uninstall -y hedera-sdk || true
pip uninstall -y hedera || true
pip install -r requirements.txt

echo "✅ Done!"
python --version
java -version

