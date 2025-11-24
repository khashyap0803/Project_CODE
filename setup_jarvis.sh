#!/bin/bash

# JARVIS Voice Assistant - Setup Script
# Professional installation and configuration

set -e

echo "========================================"
echo "JARVIS Voice Assistant Setup"
echo "========================================"
echo ""

# Check Python version
python_version=$(python3 --version | awk '{print $2}' | cut -d. -f1,2)
echo "✓ Python version: $python_version"

# Check CUDA
if command -v nvidia-smi &> /dev/null; then
    echo "✓ CUDA detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "⚠ CUDA not detected - will use CPU mode"
fi
echo ""

# Install Piper TTS if not present
if ! command -v piper &> /dev/null; then
    echo "Installing Piper TTS..."
    wget -qO- https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz | tar -xz -C /usr/local/bin
    echo "✓ Piper installed"
else
    echo "✓ Piper already installed"
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Start LLM server: ./start_llm_server.sh"
echo "2. Start JARVIS: ./start_jarvis.sh"
echo ""
echo "Or run both: ./start_all.sh"
echo ""
