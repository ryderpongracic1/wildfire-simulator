#!/usr/bin/env python3
"""
Extract and align California subset from LANDFIRE and USGS data
Handles resolution differences and geographic alignment
"""

import os
import sys

try:
    from osgeo import gdal, osr
    import numpy as np
except ImportError:
    print("Error: GDAL Python bindings required.")
    print("Install with:")
    print("  macOS: brew install gdal && pip3 install gdal")
    print("  Ubuntu: sudo apt-get install python3-gdal")
    sys.exit(1)

def get_raster_info(filename):
    """Get basic raster information"""
    dataset = gdal.Open(filename)
    if not dataset:
        raise ValueError(f"Could not open {filename}")

    gt = dataset.GetGeoTransform()

    info = {
        'width': dataset.RasterXSize,
        'height': dataset.RasterYSize,
        'bands': dataset.RasterCount,
        'projection': dataset.GetProjection(),
        'geotransform': gt,
        'minx': gt[0],
        'maxx': gt[0] + gt[1] * dataset.RasterXSize,
        'maxy': gt[3],
        'miny': gt[3] + gt[5] * dataset.RasterYSize,
        'pixel_width': gt[1],
        'pixel_height': abs(gt[5])
    }

    dataset = None
    return info

def extract_subset(input_file, output_file, minx, miny, maxx, maxy,
                   target_resolution=None):
    """Extract geographic subset from raster"""

    print(f"\nExtracting subset from {os.path.basename(input_file)}...")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")

    # Build gdalwarp command
    options = [
        '-te', str(minx), str(miny), str(maxx), str(maxy),  # Target extent
        '-te_srs', 'EPSG:4326',  # Extent in WGS84
        '-co', 'COMPRESS=LZW',  # Compress output
        '-co', 'TILED=YES',  # Tiled for better performance
    ]

    if target_resolution:
        options.extend(['-tr', str(target_resolution), str(target_resolution)])
        print(f"  Resampling to {target_resolution}° resolution")

    # Use gdalwarp for extraction
    ds = gdal.Warp(output_file, input_file, options=options)

    if ds:
        print(f"  Output: {output_file}")
        print(f"  Size: {ds.RasterXSize}x{ds.RasterYSize} pixels")
        ds = None
        return True
    else:
        print(f"  Error: Failed to extract subset")
        return False

def merge_dem_tiles(tile1, tile2, output_file):
    """Merge two adjacent DEM tiles"""
    print(f"\nMerging DEM tiles...")
    print(f"  {os.path.basename(tile1)}")
    print(f"  {os.path.basename(tile2)}")

    # Use gdal_merge.py or gdalwarp
    options = [
        '-co', 'COMPRESS=LZW',
        '-co', 'TILED=YES',
    ]

    ds = gdal.Warp(output_file, [tile1, tile2], options=options)

    if ds:
        print(f"  Merged output: {output_file}")
        print(f"  Size: {ds.RasterXSize}x{ds.RasterYSize} pixels")
        ds = None
        return True
    else:
        print(f"  Error: Failed to merge tiles")
        return False

def main():
    # Paths
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

    print("=" * 60)
    print("  California Wildfire Data Extraction")
    print("=" * 60)

    # Get DEM info to determine bounds
    print("\nAnalyzing DEM tiles...")
    dem_info = get_raster_info(dem_w119)

    print(f"DEM tile n34_w119:")
    print(f"  Size: {dem_info['width']}x{dem_info['height']} pixels")
    print(f"  Resolution: {dem_info['pixel_width']:.6f}° ({dem_info['pixel_width']*111320:.1f}m)")
    print(f"  Bounds: ({dem_info['minx']:.4f}, {dem_info['miny']:.4f}) to "
          f"({dem_info['maxx']:.4f}, {dem_info['maxy']:.4f})")

    # Option 1: Merge DEM tiles if both exist
    merged_dem = os.path.join(script_dir, "california_elevation_merged.tif")
    if os.path.exists(dem_w118):
        if not os.path.exists(merged_dem):
            merge_dem_tiles(dem_w119, dem_w118, merged_dem)
        dem_file = merged_dem
        dem_info = get_raster_info(merged_dem)
    else:
        dem_file = dem_w119

    # Define region of interest (slightly larger than DEM for context)
    # California coastal area around Santa Barbara/Ventura
    minx = dem_info['minx'] - 0.1  # Add 0.1° buffer
    maxx = dem_info['maxx'] + 0.1
    miny = dem_info['miny'] - 0.1
    maxy = dem_info['maxy'] + 0.1

    print(f"\nRegion of Interest:")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")
    print(f"  Center: {(minx+maxx)/2:.4f}°, {(miny+maxy)/2:.4f}°")

    # Extract LANDFIRE subset
    # Note: LANDFIRE is 250m, DEM is ~30m (1 arc-second)
    # We'll extract LANDFIRE at its native resolution first

    landfire_subset = os.path.join(script_dir, "california_fuel_model.tif")

    if not os.path.exists(landfire_subset):
        landfire_info = get_raster_info(landfire_file)
        print(f"\nLANDFIRE FBFM40 info:")
        print(f"  Size: {landfire_info['width']}x{landfire_info['height']} pixels")
        print(f"  Resolution: {landfire_info['pixel_width']:.6f}° "
              f"({abs(landfire_info['pixel_width'])*111320:.1f}m)")

        extract_subset(landfire_file, landfire_subset, minx, miny, maxx, maxy)
    else:
        print(f"\nFuel model subset already exists: {landfire_subset}")

    # Option 2: Resample fuel model to match DEM resolution (30m)
    # This will make a MUCH larger file but better accuracy
    landfire_30m = os.path.join(script_dir, "california_fuel_model_30m.tif")

    if not os.path.exists(landfire_30m):
        print(f"\nCreating 30m resolution fuel model (this may take a while)...")
        extract_subset(landfire_file, landfire_30m, minx, miny, maxx, maxy,
                      target_resolution=dem_info['pixel_width'])
    else:
        print(f"\n30m fuel model already exists: {landfire_30m}")

    # Option 3: Resample DEM to match LANDFIRE (250m) - faster, less memory
    dem_250m = os.path.join(script_dir, "california_elevation_250m.tif")

    if not os.path.exists(dem_250m):
        print(f"\nCreating 250m resolution elevation (faster option)...")
        landfire_info = get_raster_info(landfire_subset)
        extract_subset(dem_file, dem_250m, minx, miny, maxx, maxy,
                      target_resolution=landfire_info['pixel_width'])
    else:
        print(f"\n250m elevation already exists: {dem_250m}")

    # Summary
    print("\n" + "=" * 60)
    print("  Extraction Complete!")
    print("=" * 60)
    print("\nYou now have two options for simulation:")
    print("\n1. High Resolution (30m) - More accurate but slower:")
    print(f"   Fuel:      {os.path.basename(landfire_30m)}")
    print(f"   Elevation: {os.path.basename(dem_file)}")
    print("   Grid size: ~500x500 to 2000x2000 cells (depending on extent)")

    print("\n2. Standard Resolution (250m) - Faster, less memory:")
    print(f"   Fuel:      {os.path.basename(landfire_subset)}")
    print(f"   Elevation: {os.path.basename(dem_250m)}")
    print("   Grid size: ~100x100 cells")

    print("\nConfiguration files will be created for both options.")

    # Create configuration files
    create_configs(script_dir, landfire_subset, dem_250m,
                   landfire_30m, dem_file, minx, miny, maxx, maxy)

def create_configs(output_dir, fuel_250m, dem_250m, fuel_30m, dem_30m,
                   minx, miny, maxx, maxy):
    """Create simulation configuration files"""

    import json

    # Calculate center point for ignition
    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2

    # Config 1: Standard resolution (250m)
    config_250m = {
        "run_id": 10,
        "fuel_data_file": os.path.abspath(fuel_250m),
        "elevation_data_file": os.path.abspath(dem_250m),
        "ignition_point": {
            "x": 50,  # Will be adjusted based on actual grid size
            "y": 50,
            "note": "Adjust based on actual grid dimensions after loading"
        },
        "wind": {
            "speed": 15,
            "direction": 270,
            "note": "15 mph from West (common California pattern)"
        },
        "fuel_moisture": 6.0,
        "simulation_steps": 120,
        "time_step": 1.0,
        "output_dir": "output",
        "cell_size": 250.0,
        "region": "California - Santa Barbara/Ventura",
        "description": "Standard 250m resolution - faster simulation"
    }

    config_file_250m = os.path.join(output_dir, "config_california_250m.json")
    with open(config_file_250m, 'w') as f:
        json.dump(config_250m, f, indent=2)
    print(f"\nCreated: {config_file_250m}")

    # Config 2: High resolution (30m) - if files exist
    if os.path.exists(fuel_30m):
        config_30m = {
            "run_id": 11,
            "fuel_data_file": os.path.abspath(fuel_30m),
            "elevation_data_file": os.path.abspath(dem_30m),
            "ignition_point": {
                "x": 250,
                "y": 250,
                "note": "Adjust based on actual grid dimensions"
            },
            "wind": {
                "speed": 15,
                "direction": 270
            },
            "fuel_moisture": 6.0,
            "simulation_steps": 180,
            "time_step": 1.0,
            "output_dir": "output",
            "cell_size": 30.0,
            "region": "California - Santa Barbara/Ventura",
            "description": "High resolution 30m - more accurate but slower"
        }

        config_file_30m = os.path.join(output_dir, "config_california_30m.json")
        with open(config_file_30m, 'w') as f:
            json.dump(config_30m, f, indent=2)
        print(f"Created: {config_file_30m}")

if __name__ == '__main__':
    main()
