#!/usr/bin/env python3
"""
Extract a TINY manageable region (2km x 2km) for testing
This will create ~10x10 to 80x80 grids depending on resolution
"""

import os
import sys
import json
from osgeo import gdal, osr
import numpy as np

gdal.UseExceptions()

def extract_tiny_subset(input_file, output_file, minx, miny, maxx, maxy, target_cells):
    """Extract and resample to target cell count"""

    print(f"\n  Extracting from {os.path.basename(input_file)}...")

    # Calculate target resolution in degrees
    width_deg = maxx - minx
    height_deg = maxy - miny

    target_res = max(width_deg / target_cells, height_deg / target_cells)

    print(f"    Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")
    print(f"    Target: ~{target_cells}x{target_cells} cells")
    print(f"    Resolution: {target_res:.6f}°")

    # Determine resample method from filename
    if 'fuel' in output_file.lower():
        resample = 'near'  # Nearest neighbor for categorical
    else:
        resample = 'bilinear'  # Bilinear for continuous

    warp_options = gdal.WarpOptions(
        format='GTiff',
        outputBounds=[minx, miny, maxx, maxy],
        xRes=target_res,
        yRes=target_res,
        resampleAlg=resample,
        creationOptions=['COMPRESS=LZW', 'TILED=NO']
    )

    try:
        ds = gdal.Warp(output_file, input_file, options=warp_options)
        if ds:
            print(f"    ✓ Created: {ds.RasterXSize}x{ds.RasterYSize} pixels")
            ds = None
            return True
        else:
            print(f"    ✗ Failed")
            return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def main():
    data_source = os.path.expanduser("~/Documents/GitHub/wildfire/data")
    script_dir = os.path.dirname(os.path.abspath(__file__))

    landfire_file = os.path.join(data_source,
                                 "LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif")
    dem_file = os.path.join(data_source, "n34_w119_1arc_v3.tif")

    if not os.path.exists(landfire_file) or not os.path.exists(dem_file):
        print("Error: Required data files not found")
        return

    print("=" * 70)
    print("  TINY Test Region Extraction (2km x 2km)")
    print("=" * 70)
    print("\nThis creates manageable grids for quick testing")
    print("")

    # TINY region: 2km x 2km around Santa Barbara
    center_lon = -119.70
    center_lat = 34.42

    # 2km = ~0.018 degrees at this latitude
    size_deg = 0.018

    minx = center_lon - size_deg / 2
    maxx = center_lon + size_deg / 2
    miny = center_lat - size_deg / 2
    maxy = center_lat + size_deg / 2

    print(f"Region: Santa Barbara (TINY test area)")
    print(f"  Center: {center_lat:.4f}°N, {abs(center_lon):.4f}°W")
    print(f"  Size: 2km x 2km")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")
    print("")

    # Option 1: Coarse resolution (~200m) - Very fast
    print("=" * 70)
    print("  OPTION 1: Coarse Resolution (~200m)")
    print("=" * 70)

    fuel_coarse = os.path.join(script_dir, "test_fuel_coarse.tif")
    dem_coarse = os.path.join(script_dir, "test_elevation_coarse.tif")

    target_cells_coarse = 10  # 10x10 grid

    extract_tiny_subset(landfire_file, fuel_coarse, minx, miny, maxx, maxy, target_cells_coarse)
    extract_tiny_subset(dem_file, dem_coarse, minx, miny, maxx, maxy, target_cells_coarse)

    # Option 2: Medium resolution (~100m)
    print("")
    print("=" * 70)
    print("  OPTION 2: Medium Resolution (~100m)")
    print("=" * 70)

    fuel_medium = os.path.join(script_dir, "test_fuel_medium.tif")
    dem_medium = os.path.join(script_dir, "test_elevation_medium.tif")

    target_cells_medium = 20  # 20x20 grid

    extract_tiny_subset(landfire_file, fuel_medium, minx, miny, maxx, maxy, target_cells_medium)
    extract_tiny_subset(dem_file, dem_medium, minx, miny, maxx, maxy, target_cells_medium)

    # Option 3: Fine resolution (~50m)
    print("")
    print("=" * 70)
    print("  OPTION 3: Fine Resolution (~50m)")
    print("=" * 70)

    fuel_fine = os.path.join(script_dir, "test_fuel_fine.tif")
    dem_fine = os.path.join(script_dir, "test_elevation_fine.tif")

    target_cells_fine = 40  # 40x40 grid

    extract_tiny_subset(landfire_file, fuel_fine, minx, miny, maxx, maxy, target_cells_fine)
    extract_tiny_subset(dem_file, dem_fine, minx, miny, maxx, maxy, target_cells_fine)

    # Create config files
    print("")
    print("=" * 70)
    print("  Creating Configuration Files")
    print("=" * 70)

    configs = [
        ("test_coarse", fuel_coarse, dem_coarse, 200.0, "10x10 grid, very fast (<1 sec)"),
        ("test_medium", fuel_medium, dem_medium, 100.0, "20x20 grid, fast (~2 sec)"),
        ("test_fine", fuel_fine, dem_fine, 50.0, "40x40 grid, moderate (~5 sec)")
    ]

    for name, fuel_file, dem_file, cell_size, desc in configs:
        if os.path.exists(fuel_file):
            ds = gdal.Open(fuel_file)
            width = ds.RasterXSize
            height = ds.RasterYSize
            ds = None

            config = {
                "run_id": 200 + configs.index((name, fuel_file, dem_file, cell_size, desc)),
                "fuel_data_file": os.path.abspath(fuel_file),
                "elevation_data_file": os.path.abspath(dem_file),
                "ignition_point": {
                    "x": width // 2,
                    "y": height // 2
                },
                "wind": {
                    "speed": 15,
                    "direction": 270
                },
                "fuel_moisture": 8.0,
                "simulation_steps": 60,
                "time_step": 1.0,
                "output_dir": "output",
                "cell_size": cell_size,
                "region": "Santa Barbara - Tiny Test Area (2km x 2km)",
                "description": desc
            }

            config_file = os.path.join(script_dir, f"config_{name}.json")
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"\n  ✓ {os.path.basename(config_file)}")
            print(f"    Grid: {width}x{height} cells")
            print(f"    {desc}")

    print("")
    print("=" * 70)
    print("  Complete! Ready to Simulate")
    print("=" * 70)
    print("")
    print("Next steps:")
    print("  1. Build simulator (if not done):")
    print("     cd cpp/build && cmake .. && make -j$(sysctl -n hw.ncpu) && cd ../..")
    print("")
    print("  2. Run FAST test:")
    print("     ./cpp/build/wildfire_simulator data/config_test_coarse.json")
    print("")
    print("  3. Or try medium resolution:")
    print("     ./cpp/build/wildfire_simulator data/config_test_medium.json")
    print("")
    print("  4. Or fine resolution:")
    print("     ./cpp/build/wildfire_simulator data/config_test_fine.json")
    print("")

if __name__ == '__main__':
    main()
