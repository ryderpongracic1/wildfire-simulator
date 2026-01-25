# Using Real LANDFIRE and USGS Data

## Your Data

Located in `~/Documents/GitHub/wildfire/data/`:

- **LANDFIRE FBFM40**: `LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif`
  - Fuel model: 40 Anderson fuel models
  - Resolution: 250m
  - Coverage: Entire Continental US (CONUS)
  - Size: Very large (CONUS-wide)

- **USGS DEM Elevation**:
  - `n34_w119_1arc_v3.tif` - Tile for 34°N, 119°W
  - `n34_w118_1arc_v3.tif` - Tile for 34°N, 118°W
  - Resolution: 1 arc-second (~30 meters)
  - Coverage: California coastal region (Santa Barbara/Ventura area)
  - Size: 3601x3601 pixels per tile

## Quick Setup

### Step 1: Extract California Subset

The LANDFIRE file covers all of CONUS and is huge. We need to extract just the California region matching your DEM tiles:

```bash
cd data
python3 extract_california_subset.py
```

This will:
1. Merge your two DEM tiles (if both exist)
2. Extract LANDFIRE data for the matching geographic region
3. Create two versions:
   - **250m resolution** (faster, standard) - recommended to start
   - **30m resolution** (slower, high detail) - for production runs
4. Generate ready-to-use configuration files

### Step 2: Choose Resolution

**Option A: Standard Resolution (250m) - Recommended**
- Grid size: ~100x100 cells
- Simulation time: ~10-30 seconds
- Memory: ~100 MB
- Good for: Testing, quick iterations, parameter tuning

**Option B: High Resolution (30m)**
- Grid size: ~500x500 to 2000x2000 cells
- Simulation time: 1-10 minutes
- Memory: 1-4 GB
- Good for: Production runs, detailed analysis, publication

### Step 3: Run Simulation

Using the generated configuration:

```bash
# Standard resolution (fast)
cd ..
./cpp/build/wildfire_simulator data/config_california_250m.json

# High resolution (detailed)
./cpp/build/wildfire_simulator data/config_california_30m.json
```

## Region Details

**Geographic Coverage:**
- Latitude: ~34°N (Santa Barbara/Ventura/Los Angeles area)
- Longitude: ~118-119°W (California coast)
- Area: Covers parts of:
  - Los Padres National Forest
  - Santa Monica Mountains
  - Coastal chaparral and brush

**Typical Fuel Types in This Region:**
- Fuel Model 4: Chaparral (6 ft) - very common
- Fuel Model 5: Brush (2 ft)
- Fuel Model 8: Compact timber litter
- Fuel Model 10: Timber understory
- Some grassland (Models 1-3) in valleys

**Common Fire Weather:**
- Santa Ana winds: 20-40 mph from NE (direction: 45°)
- Onshore flow: 5-15 mph from W (direction: 270°)
- Fuel moisture: 3-6% during drought, 8-12% normal

## Example Scenarios

### Scenario 1: Santa Ana Wind Event (High Risk)
```json
{
    "wind": {
        "speed": 35,
        "direction": 45
    },
    "fuel_moisture": 4.0,
    "description": "Extreme fire weather - hot, dry Santa Ana winds"
}
```

### Scenario 2: Normal Summer Day
```json
{
    "wind": {
        "speed": 10,
        "direction": 270
    },
    "fuel_moisture": 8.0,
    "description": "Typical summer conditions - moderate risk"
}
```

### Scenario 3: Favorable Conditions (Lower Risk)
```json
{
    "wind": {
        "speed": 5,
        "direction": 270
    },
    "fuel_moisture": 12.0,
    "description": "Light winds, higher moisture - slower spread"
}
```

## Adjusting Ignition Point

After extraction, check the actual grid size:

```bash
# For 250m data
gdalinfo data/california_fuel_model.tif | grep "Size is"
# Output: Size is XXX, YYY

# Set ignition point to center
# ignition_point: { "x": XXX/2, "y": YYY/2 }
```

Or pick a specific location:
1. Find coordinates of interest (e.g., from Google Maps)
2. Use `gdallocationinfo` to convert to grid coordinates
3. Update config file

## Performance Expectations

**250m Resolution (~100x100 grid):**
- Load time: <1 second
- Simulation: ~10-30 seconds for 120 steps
- Speedup: 6-12x with OpenMP (8 threads)
- Memory: ~100 MB

**30m Resolution (~500x500 grid):**
- Load time: 2-5 seconds
- Simulation: 1-5 minutes for 120 steps
- Speedup: 8-12x with OpenMP (8 threads)
- Memory: 500 MB - 1 GB

**30m Resolution (~1000x1000 grid):**
- Load time: 5-10 seconds
- Simulation: 5-15 minutes for 120 steps
- Memory: 2-4 GB
- Note: May benefit from 16+ threads

## Troubleshooting

### Error: "Failed to open raster file"
- Check file paths in config are absolute or relative to working directory
- Verify GDAL can read files: `gdalinfo <filename>`

### Grid size too large / out of memory
- Use 250m resolution instead of 30m
- Extract smaller geographic subset
- Reduce simulation steps

### GDAL not found
```bash
# macOS
brew install gdal
pip3 install gdal

# Ubuntu/Debian
sudo apt-get install gdal-bin python3-gdal libgdal-dev
```

## Data Attribution

- **LANDFIRE**: https://landfire.gov/
  - "Landscape Fire and Resource Management Planning Tools Project"
  - Public domain, U.S. Department of Agriculture and Department of Interior

- **USGS 3DEP**: https://www.usgs.gov/3d-elevation-program
  - "3D Elevation Program Digital Elevation Model"
  - Public domain, U.S. Geological Survey

## Next Steps

1. Extract data: `python3 data/extract_california_subset.py`
2. Test with 250m: `./cpp/build/wildfire_simulator data/config_california_250m.json`
3. Review results in `output/` directory
4. Adjust parameters (wind, moisture, ignition point)
5. Run production simulations with 30m resolution
6. Visualize in web interface: `docker-compose up`

Happy simulating! 🔥
