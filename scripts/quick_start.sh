#!/bin/bash
# Quick Start Script for Wildfire Simulator
# Sets up test data and runs a sample simulation

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "  Wildfire Simulator - Quick Start"
echo "=========================================="
echo ""

# Check dependencies
echo "Checking dependencies..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi
echo "✓ Python 3 found"

# Check GDAL
if ! command -v gdalinfo &> /dev/null; then
    echo "Warning: GDAL not found. Install with:"
    echo "  Ubuntu/Debian: sudo apt-get install gdal-bin python3-gdal"
    echo "  macOS: brew install gdal"
    echo ""
fi

# Step 1: Generate test data
echo ""
echo "Step 1: Generating test data..."
echo "================================"

mkdir -p data/sample

if [ ! -f "data/sample/test_fuel_model.tif" ] || [ ! -f "data/sample/test_elevation.tif" ]; then
    if command -v python3 &> /dev/null; then
        # Check if GDAL Python bindings are available
        if python3 -c "from osgeo import gdal" 2>/dev/null; then
            python3 data/sample/generate_test_data.py
        else
            echo "Warning: GDAL Python bindings not found."
            echo "Install with: pip install gdal"
            echo ""
            echo "For now, you'll need to provide your own GeoTIFF data files."
            exit 1
        fi
    else
        echo "Error: Python 3 required for test data generation"
        exit 1
    fi
else
    echo "Test data already exists. Skipping generation."
fi

# Step 2: Build C++ simulator
echo ""
echo "Step 2: Building C++ simulator..."
echo "================================"

if [ ! -f "cpp/build/wildfire_simulator" ]; then
    echo "Building simulator..."
    mkdir -p cpp/build
    cd cpp/build

    cmake -DCMAKE_BUILD_TYPE=Release ..
    make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

    cd "$PROJECT_DIR"
    echo "✓ Simulator built successfully"
else
    echo "✓ Simulator already built"
fi

# Step 3: Create output directory
echo ""
echo "Step 3: Creating output directory..."
echo "===================================="
mkdir -p output
echo "✓ Output directory ready"

# Step 4: Run test simulation
echo ""
echo "Step 4: Running test simulation..."
echo "===================================="
echo ""
echo "Configuration:"
echo "  Fuel data: data/sample/test_fuel_model.tif"
echo "  Elevation: data/sample/test_elevation.tif"
echo "  Ignition: (150, 150)"
echo "  Wind: 12 mph from West (270°)"
echo "  Fuel moisture: 8%"
echo "  Duration: 60 steps (60 minutes)"
echo ""

export OMP_NUM_THREADS=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

./cpp/build/wildfire_simulator data/sample/config_test.json

# Step 5: Display results
echo ""
echo "=========================================="
echo "  Simulation Complete!"
echo "=========================================="
echo ""

if [ -f "output/benchmark_1.json" ]; then
    echo "Results:"
    if command -v python3 &> /dev/null; then
        python3 - <<EOF
import json
import sys

try:
    with open('output/benchmark_1.json', 'r') as f:
        bench = json.load(f)

    print(f"  Threads used: {bench.get('threads', 'N/A')}")
    print(f"  Grid size: {bench.get('grid_size', 'N/A'):,} cells")
    print(f"  Simulation steps: {bench.get('simulation_steps', 'N/A')}")
    print(f"  Wall time: {bench.get('wall_time_seconds', 0):.2f} seconds")
    print(f"  Simulated time: {bench.get('simulated_time_minutes', 0):.1f} minutes")
    print(f"  Speedup vs realtime: {bench.get('speedup_vs_realtime', 0):.1f}x")
    print(f"  Cells burned: {bench.get('cells_burned', 'N/A'):,}")
    print()
except Exception as e:
    print(f"Could not read benchmark file: {e}")
    sys.exit(1)
EOF
    fi

    echo "Output files:"
    ls -lh output/ | grep "^-" | awk '{print "  " $9 " (" $5 ")"}'
fi

echo ""
echo "=========================================="
echo "  Next Steps"
echo "=========================================="
echo ""
echo "1. View results in output/ directory"
echo "2. Run benchmark: ./scripts/run_benchmark.sh"
echo "3. Start web interface with Docker:"
echo "     docker-compose up --build"
echo "     Access at http://localhost:8080"
echo "4. Try different scenarios:"
echo "     - High wind: data/sample/config_high_wind.json"
echo "     - Benchmark: data/sample/config_benchmark.json"
echo ""
echo "For more information, see README.md"
echo ""
