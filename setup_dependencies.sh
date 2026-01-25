#!/bin/bash
# Install all dependencies for wildfire simulator on macOS

set -e

echo "=========================================="
echo "  Installing Wildfire Simulator Dependencies"
echo "=========================================="
echo ""

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Please install from https://brew.sh/"
    echo ""
    echo "Run this command:"
    echo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

echo "✓ Homebrew found"
echo ""

# Install build tools
echo "Installing CMake..."
brew install cmake

echo "Installing GDAL..."
brew install gdal

echo "Installing OpenMP support (libomp)..."
brew install libomp

echo "Installing PostgreSQL (optional, for database features)..."
brew install postgresql@15

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Build the simulator:"
echo "     cd cpp && mkdir -p build && cd build"
echo "     cmake -DCMAKE_BUILD_TYPE=Release .."
echo "     make -j\$(sysctl -n hw.ncpu)"
echo ""
echo "  2. Extract a smaller California region:"
echo "     python3 data/extract_california_subset_small.py"
echo ""
