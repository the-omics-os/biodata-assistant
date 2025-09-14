#!/bin/bash

# Biodata Assistant Demo Runner
echo "🔬 BIODATA ASSISTANT - Hackathon Demo"
echo "======================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10+"
    exit 1
fi

# Check if we're in the backend directory
if [ ! -f "demo.py" ]; then
    echo "❌ Please run this script from the backend directory"
    exit 1
fi

# Install dependencies if needed
echo "📦 Checking dependencies..."
pip install rich --quiet 2>/dev/null || pip3 install rich --quiet 2>/dev/null

# Clear screen for better presentation
clear

# Run the demo
echo "🚀 Starting demo..."
echo ""
python3 demo.py || python demo.py

echo ""
echo "Thank you for using Biodata Assistant!"
