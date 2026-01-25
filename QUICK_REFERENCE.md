# Wildfire Simulator - Quick Reference Card

## One-Time Setup (Do Once)

```bash
# 1. Install dependencies
./setup_dependencies.sh

# 2. Extract small test region (20km x 20km)
python3 data/extract_california_subset_small.py

# 3. Build simulator
cd cpp && mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(sysctl -n hw.ncpu)
cd ../..
```

---

## Run Simulation (Fast)

```bash
mkdir -p output
./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json
```

**Expected:** 2-5 seconds, ~80x80 grid, 2 hours simulated time

---

## Run Simulation (Detailed)

```bash
./cpp/build/wildfire_simulator data/config_santa_barbara_100m.json
```

**Expected:** 10-30 seconds, ~200x200 grid, 3 hours simulated time

---

## View Results

```bash
# List output files
ls -lh output/

# View performance metrics
cat output/benchmark_100.json

# View final state
cat output/final_state_100.json | head -50
```

---

## Common Scenarios

### Santa Ana Winds (Extreme)
Edit `data/config_santa_barbara_250m.json`:
```json
{
  "wind": {"speed": 35, "direction": 45},
  "fuel_moisture": 4.0
}
```

### Summer Day (Moderate)
```json
{
  "wind": {"speed": 12, "direction": 270},
  "fuel_moisture": 8.0
}
```

### High Moisture (Suppression)
```json
{
  "wind": {"speed": 5, "direction": 180},
  "fuel_moisture": 14.0
}
```

---

## Benchmark Performance

```bash
./scripts/run_benchmark.sh
```

---

## Web Interface

```bash
# Start all services
docker-compose up --build

# Open browser
open http://localhost:8080
```

---

## Troubleshooting

### Build failed?
```bash
# Reinstall GDAL
brew reinstall gdal

# Try again
cd cpp/build && make clean && cmake .. && make -j$(sysctl -n hw.ncpu)
```

### Can't find simulator?
```bash
# Check it exists
ls -la cpp/build/wildfire_simulator

# If not, rebuild
cd cpp/build && make
```

### Wrong paths in config?
```bash
# Check paths
cat data/config_santa_barbara_250m.json | grep file

# Should be absolute paths starting with /Users/...
```

---

## File Locations

**Input Data:**
- Fuel: `data/santa_barbara_fuel_250m.tif`
- Elevation: `data/santa_barbara_elevation_250m.tif`
- Config: `data/config_santa_barbara_250m.json`

**Simulator:**
- Binary: `cpp/build/wildfire_simulator`

**Output:**
- Results: `output/snapshot_*.json`
- Final: `output/final_state_*.json`
- Metrics: `output/benchmark_*.json`

---

## Wind Direction Guide

- `0°` = North (N)
- `45°` = Northeast (NE) ← Santa Ana winds
- `90°` = East (E)
- `135°` = Southeast (SE)
- `180°` = South (S)
- `225°` = Southwest (SW)
- `270°` = West (W) ← Onshore flow
- `315°` = Northwest (NW)

---

## Fuel Moisture Guide

- `3-5%` = Extreme drought ⚠️ Critical fire danger
- `6-8%` = Dry conditions 🔥 High fire danger
- `9-12%` = Normal summer ⚡ Moderate danger
- `13-20%` = Elevated moisture 🌧️ Lower danger
- `>20%` = Wet conditions ✅ Minimal danger

---

## Quick Commands Cheat Sheet

```bash
# Extract data
python3 data/extract_california_subset_small.py

# Build
cd cpp/build && cmake -DCMAKE_BUILD_TYPE=Release .. && make -j$(sysctl -n hw.ncpu) && cd ../..

# Run
./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json

# Benchmark
./scripts/run_benchmark.sh

# Web UI
docker-compose up

# Clean build
rm -rf cpp/build && mkdir cpp/build

# Clean output
rm -rf output/*.json
```

---

## Configuration Template

```json
{
  "run_id": 100,
  "fuel_data_file": "/full/path/to/fuel.tif",
  "elevation_data_file": "/full/path/to/elevation.tif",
  "ignition_point": {"x": 40, "y": 40},
  "wind": {"speed": 15, "direction": 270},
  "fuel_moisture": 8.0,
  "simulation_steps": 120,
  "time_step": 1.0,
  "output_dir": "output",
  "cell_size": 250.0
}
```

---

## Help & Documentation

- **Setup Issues:** `SETUP_STEPS.md`
- **Full Guide:** `README.md`
- **Real Data:** `data/REAL_DATA_GUIDE.md`
- **Quick Start:** `QUICKSTART_REAL_DATA.md`
- **Architecture:** `docs/PROJECT_STRUCTURE.md`

---

**Most Common Workflow:**

```bash
# 1. Extract (once)
python3 data/extract_california_subset_small.py

# 2. Build (once)
cd cpp/build && cmake .. && make -j8 && cd ../..

# 3. Run (many times with different configs)
./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json
```
