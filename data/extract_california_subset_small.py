#!/usr/bin/env python3
"""
Extract a small manageable subset from LANDFIRE and USGS data
Uses a 20km x 20km region for testing
"""

import os
import sys

try:
    from osgeo import gdal, osr
    import numpy as np
except ImportError:
    print("Error: GDAL Python bindings required.")
    print("Install with: pip3 install gdal")
    sys.exit(1)

# Enable exceptions for better error messages
gdal.UseExceptions()

def extract_subset(input_file, output_file, minx, miny, maxx, maxy,
                   target_resolution=None, resample_method='near'):
    """Extract geographic subset from raster"""

    print(f"\nExtracting from {os.path.basename(input_file)}...")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")

    warp_options = gdal.WarpOptions(
        format='GTiff',
        outputBounds=[minx, miny, maxx, maxy],
        outputBoundsSRS='EPSG:4326',
        xRes=target_resolution,
        yRes=target_resolution,
        resampleAlg=resample_method,
        creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER']
    )

    try:
        ds = gdal.Warp(output_file, input_file, options=warp_options)
        if ds:
            print(f"  ✓ Created: {os.path.basename(output_file)}")
            print(f"    Size: {ds.RasterXSize}x{ds.RasterYSize} pixels")
            ds = None
            return True
        else:
            print(f"  ✗ Failed to create output")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    data_source = os.path.expanduser("~/Documents/GitHub/wildfire/data")
    script_dir = os.path.dirname(os.path.abspath(__file__))

    landfire_file = os.path.join(data_source,
                                 "LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif")
    dem_w119 = os.path.join(data_source, "n34_w119_1arc_v3.tif")
    dem_w118 = os.path.join(data_source, "n34_w118_1arc_v3.tif")

    # Check files exist
    if not os.path.exists(landfire_file):
        print(f"Error: LANDFIRE file not found: {landfire_file}")
        return
    if not os.path.exists(dem_w119):
        print(f"Error: DEM file not found: {dem_w119}")
        return

    print("=" * 70)
    print("  California Wildfire Simulator - Small Region Extraction")
    print("=" * 70)
    print("\nThis will extract a manageable 20km x 20km region for testing.")
    print("")

    # Define a small test region (20km x 20km)
    # Centered around Santa Barbara area: 34.42°N, 119.70°W
    center_lon = -119.70
    center_lat = 34.42

    # 20km = ~0.18 degrees at this latitude
    size_deg = 0.18

    minx = center_lon - size_deg / 2
    maxx = center_lon + size_deg / 2
    miny = center_lat - size_deg / 2
    maxy = center_lat + size_deg / 2

    print(f"Test Region: Santa Barbara Area")
    print(f"  Center: {center_lat:.4f}°N, {abs(center_lon):.4f}°W")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")
    print(f"  Size: ~20km x 20km")
    print("")

    # Option 1: Standard resolution (250m)
    print("=" * 70)
    print("  OPTION 1: Standard Resolution (250m)")
    print("=" * 70)

    # Calculate 250m in degrees at this latitude
    # At 34° latitude: 1° longitude ≈ 92 km, 1° latitude ≈ 111 km
    res_250m_lon = 250.0 / 92000.0  # ~0.00272°
    res_250m_lat = 250.0 / 111000.0  # ~0.00225°
    res_250m = (res_250m_lon + res_250m_lat) / 2  # Average

    print(f"\nTarget resolution: 250m (~{res_250m:.6f}°)")
    print(f"Expected grid size: ~80x80 cells")
    print("")

    fuel_250m = os.path.join(script_dir, "santa_barbara_fuel_250m.tif")
    dem_250m = os.path.join(script_dir, "santa_barbara_elevation_250m.tif")

    # Extract fuel model at 250m
    success_fuel = extract_subset(
        landfire_file, fuel_250m,
        minx, miny, maxx, maxy,
        target_resolution=res_250m,
        resample_method='near'  # Nearest neighbor for categorical data
    )

    # Extract elevation at 250m
    success_dem = extract_subset(
        dem_w119, dem_250m,
        minx, miny, maxx, maxy,
        target_resolution=res_250m,
        resample_method='bilinear'  # Bilinear for continuous data
    )

    # Option 2: High resolution (100m) - more reasonable than 30m
    print("")
    print("=" * 70)
    print("  OPTION 2: High Resolution (100m)")
    print("=" * 70)

    res_100m_lon = 100.0 / 92000.0
    res_100m_lat = 100.0 / 111000.0
    res_100m = (res_100m_lon + res_100m_lat) / 2

    print(f"\nTarget resolution: 100m (~{res_100m:.6f}°)")
    print(f"Expected grid size: ~200x200 cells")
    print("")

    fuel_100m = os.path.join(script_dir, "santa_barbara_fuel_100m.tif")
    dem_100m = os.path.join(script_dir, "santa_barbara_elevation_100m.tif")

    success_fuel_100m = extract_subset(
        landfire_file, fuel_100m,
        minx, miny, maxx, maxy,
        target_resolution=res_100m,
        resample_method='near'
    )

    success_dem_100m = extract_subset(
        dem_w119, dem_100m,
        minx, miny, maxx, maxy,
        target_resolution=res_100m,
        resample_method='bilinear'
    )

    # Create configuration files
    print("")
    print("=" * 70)
    print("  Creating Configuration Files")
    print("=" * 70)

    import json

    if success_fuel and success_dem:
        # Get actual grid size
        ds = gdal.Open(fuel_250m)
        width = ds.RasterXSize
        height = ds.RasterYSize
        ds = None

        config_250m = {
            "run_id": 100,
            "fuel_data_file": os.path.abspath(fuel_250m),
            "elevation_data_file": os.path.abspath(dem_250m),
            "ignition_point": {
                "x": width // 2,
                "y": height // 2
            },
            "wind": {
                "speed": 15,
                "direction": 270,
                "note": "15 mph westerly wind (typical onshore flow)"
            },
            "fuel_moisture": 8.0,
            "simulation_steps": 120,
            "time_step": 1.0,
            "output_dir": "output",
            "cell_size": 250.0,
            "region": "Santa Barbara, California",
            "description": "20km x 20km test region at 250m resolution"
        }

        config_file = os.path.join(script_dir, "config_santa_barbara_250m.json")
        with open(config_file, 'w') as f:
            json.dump(config_250m, f, indent=2)
        print(f"\n✓ Created: {os.path.basename(config_file)}")
        print(f"  Grid size: {width}x{height} cells")
        print(f"  Ignition point: ({width//2}, {height//2})")

    if success_fuel_100m and success_dem_100m:
        ds = gdal.Open(fuel_100m)
        width = ds.RasterXSize
        height = ds.RasterYSize
        ds = None

        config_100m = {
            "run_id": 101,
            "fuel_data_file": os.path.abspath(fuel_100m),
            "elevation_data_file": os.path.abspath(dem_100m),
            "ignition_point": {
                "x": width // 2,
                "y": height // 2
            },
            "wind": {
                "speed": 15,
                "direction": 270
            },
            "fuel_moisture": 8.0,
            "simulation_steps": 180,
            "time_step": 1.0,
            "output_dir": "output",
            "cell_size": 100.0,
            "region": "Santa Barbara, California",
            "description": "20km x 20km test region at 100m resolution"
        }

        config_file = os.path.join(script_dir, "config_santa_barbara_100m.json")
        with open(config_file, 'w') as f:
            json.dump(config_100m, f, indent=2)
        print(f"\n✓ Created: {os.path.basename(config_file)}")
        print(f"  Grid size: {width}x{height} cells")
        print(f"  Ignition point: ({width//2}, {height//2})")

    # Summary
    print("")
    print("=" * 70)
    print("  Extraction Complete!")
    print("=" * 70)
    print("\nFiles created:")
    print("  250m resolution (fast):")
    print(f"    • {os.path.basename(fuel_250m)}")
    print(f"    • {os.path.basename(dem_250m)}")
    print(f"    • config_santa_barbara_250m.json")
    print("")
    print("  100m resolution (detailed):")
    print(f"    • {os.path.basename(fuel_100m)}")
    print(f"    • {os.path.basename(dem_100m)}")
    print(f"    • config_santa_barbara_100m.json")
    print("")
    print("Next steps:")
    print("  1. Build the simulator:")
    print("     cd cpp && mkdir -p build && cd build")
    print("     cmake -DCMAKE_BUILD_TYPE=Release ..")
    print("     make -j$(sysctl -n hw.ncpu)")
    print("     cd ../..")
    print("")
    print("  2. Run simulation:")
    print("     mkdir -p output")
    print("     ./cpp/build/wildfire_simulator data/config_santa_barbara_250m.json")
    print("")

if __name__ == '__main__':
    main()
