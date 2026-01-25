#!/bin/bash
# Install GDAL for macOS

echo "Installing GDAL for Wildfire Simulator..."
echo ""

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew not found. Install from https://brew.sh/"
    exit 1
fi

echo "Installing GDAL via Homebrew..."
brew install gdal

echo ""
echo "Installing Python GDAL bindings..."

# Get GDAL version
GDAL_VERSION=$(gdal-config --version 2>/dev/null)

if [ -z "$GDAL_VERSION" ]; then
    echo "Error: GDAL installation failed"
    exit 1
fi

echo "GDAL version: $GDAL_VERSION"

# Install matching Python bindings
pip3 install gdal==$GDAL_VERSION

echo ""
echo "Testing installation..."
python3 -c "from osgeo import gdal; print('✓ GDAL Python bindings working')" || {
    echo "Warning: Python bindings installation may have failed"
    echo "Try: pip3 install gdal"
    exit 1
}

echo ""
echo "✓ GDAL installation complete!"
echo ""
echo "You can now run:"
echo "  python3 data/extract_california_subset.py"
