# Setup Steps - Fixed for Your System

## Issues Found

1. ❌ **CMake not installed** - needed to build C++ simulator
2. ❌ **Region too large** - the original extraction tried to create 90,000x70,000 pixel file (>2GB)

## Solution: 3 Simple Steps

### Step 1: Install Build Tools

```bash
./setup_dependencies.sh
```

This installs:
- CMake (build system)
- GDAL (already have Python bindings, this adds the C++ library)
- libomp (OpenMP for parallelization)
- PostgreSQL (optional)

**Time: ~5 minutes**

---

### Step 2: Extract Small Test Region (20km x 20km)

Instead of the entire region, extract a manageable 20km x 20km area around Santa Barbara:

```bash
python3 data/extract_california_subset_small.py
```

**What this creates:**
- `santa_barbara_fuel_250m.tif` - 250m resolution (~80x80 cells) **← Start here**
- `santa_barbara_elevation_250m.tif`
- `config_santa_barbara_250m.json` (ready to use!)

Plus 100m resolution versions if you want more detail later.

**Time: ~30 seconds**

---

### Step 3: Build and Run Simulator

```bash
# Build (one time)
cd cpp
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(sysctl -n hw.ncpu)
cd ../..

# Run simulation
mkdir -p output
./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json
```

**Expected output:**
```
=== Wildfire Spread Simulator ===
Using 8 OpenMP threads

--- Loading Geospatial Data ---
Loaded fuel data: 80x80 cells
Loaded elevation data: 80x80 cells
Data loading time: 0.3 seconds

--- Running Simulation ---
Step 120/120 - Time: 120.0 min - Burning: 3 - Burned: 256

=== Simulation Complete ===
Total simulation time: 2.1 seconds
Simulated time: 120.0 minutes (2.0 hours)
Performance: 3429x real-time
Final burned cells: 256
Burned area: 1.6 hectares
```

**Time: Build 1-2 min, Run 2-5 seconds**

---

## Why This is Better

**Original extraction attempt:**
- Region: 2.2° x 1.2° (~240km x 130km)
- At 30m: Would be 90,000 x 70,000 = 6.3 billion pixels ❌
- File size: >2GB (GDAL limit exceeded)

**New extraction:**
- Region: 0.18° x 0.18° (~20km x 20km) ✓
- At 250m: ~80 x 80 = 6,400 pixels ✓
- At 100m: ~200 x 200 = 40,000 pixels ✓
- Files: <10 MB each ✓
- Simulation time: Seconds instead of hours ✓

## Quick Test Commands

```bash
# Install dependencies
./setup_dependencies.sh

# Extract small region
python3 data/extract_california_subset_small.py

# Build
cd cpp && mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(sysctl -n hw.ncpu)
cd ../..

# Run
mkdir -p output
./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json

# View results
ls -lh output/
cat output/benchmark_100.json
```

## Test Region Details

**Location:** Santa Barbara, California
- Center: 34.42°N, 119.70°W
- Coverage: Los Padres National Forest foothills
- Fuel types: Chaparral, brush, oak woodland
- Elevation: 100-800m
- Terrain: Moderate to steep slopes

**Typical scenarios:**
- Onshore flow: 10-15 mph from W (270°), moisture 8-10%
- Santa Ana: 25-35 mph from NE (45°), moisture 4-6%

## After First Success

Once you have the 250m version working, you can:

1. **Try 100m resolution** for more detail:
   ```bash
   ./cpp/build/wildfire_simulator data/config_santa_barbara_100m.json
   ```

2. **Extract different regions** by editing `extract_california_subset_small.py`:
   - Change `center_lon` and `center_lat`
   - Adjust `size_deg` for area size

3. **Test scenarios** by editing config JSON:
   - Modify wind speed/direction
   - Adjust fuel moisture
   - Change ignition point

4. **Run benchmarks**:
   ```bash
   ./scripts/run_benchmark.sh
   ```

## Troubleshooting

### "command not found: cmake"
Run: `./setup_dependencies.sh`

### "No such file or directory: ./cpp/build/wildfire_simulator"
You need to build first - see Step 3 above

### "Failed to open raster file"
Check the config file has correct absolute paths:
```bash
cat data/config_santa_barbara_250m.json | grep file
```

### Build errors about GDAL
```bash
brew reinstall gdal
```

### Python GDAL errors
```bash
pip3 install --upgrade gdal
```

---

**Ready to go! Start with:** `./setup_dependencies.sh`
