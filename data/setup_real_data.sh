#!/bin/bash
# Setup script to link existing LANDFIRE and USGS data

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_SOURCE="$HOME/Documents/GitHub/wildfire/data"

echo "=========================================="
echo "  Setup Real Wildfire Data"
echo "=========================================="
echo ""

# Check if source data exists
if [ ! -d "$DATA_SOURCE" ]; then
    echo "Error: Data directory not found at $DATA_SOURCE"
    exit 1
fi

echo "Source data directory: $DATA_SOURCE"
echo ""

# Create symlinks to real data
echo "Creating symbolic links..."

# Link LANDFIRE fuel model
if [ -f "$DATA_SOURCE/LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif" ]; then
    ln -sf "$DATA_SOURCE/LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif" \
           "$SCRIPT_DIR/landfire_fbfm40_conus.tif"
    echo "✓ Linked LANDFIRE FBFM40 (250m CONUS)"
fi

# Link USGS DEM tiles
if [ -f "$DATA_SOURCE/n34_w119_1arc_v3.tif" ]; then
    ln -sf "$DATA_SOURCE/n34_w119_1arc_v3.tif" \
           "$SCRIPT_DIR/dem_n34_w119.tif"
    echo "✓ Linked USGS DEM (34°N, 119°W)"
fi

if [ -f "$DATA_SOURCE/n34_w118_1arc_v3.tif" ]; then
    ln -sf "$DATA_SOURCE/n34_w118_1arc_v3.tif" \
           "$SCRIPT_DIR/dem_n34_w118.tif"
    echo "✓ Linked USGS DEM (34°N, 118°W)"
fi

echo ""
echo "Data files linked successfully!"
echo ""
echo "Note: The LANDFIRE file is 250m resolution (CONUS-wide),"
echo "while USGS DEM is ~30m (1 arc-second). You'll need to either:"
echo "  1. Extract a subset from LANDFIRE for your region, or"
echo "  2. Resample one to match the other's resolution"
echo ""
echo "See extract_california_subset.py for extraction tools."
echo ""
