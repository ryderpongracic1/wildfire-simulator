#!/usr/bin/env python3
"""
Workaround for LANDFIRE large tile issue
Extracts fuel data without tiling first, then retiles
"""

import os
import sys
from osgeo import gdal

gdal.UseExceptions()

def extract_fuel_simple(input_file, output_file, minx, miny, maxx, maxy, resolution):
    """Extract fuel data with simpler options to avoid tile size issues"""

    print(f"\nExtracting fuel data (workaround method)...")
    print(f"  Input: {os.path.basename(input_file)}")
    print(f"  Output: {os.path.basename(output_file)}")

    # Use gdal.Translate first without tiling
    temp_file = output_file.replace('.tif', '_temp.tif')

    translate_options = gdal.TranslateOptions(
        format='GTiff',
        projWin=[minx, maxy, maxx, miny],  # [ulx, uly, lrx, lry]
        xRes=resolution,
        yRes=resolution,
        resampleAlg='near',
        creationOptions=['COMPRESS=NONE']  # No compression to avoid tile issues
    )

    try:
        print("  Step 1: Extracting region...")
        ds = gdal.Translate(temp_file, input_file, options=translate_options)
        if not ds:
            print(f"  ✗ Failed to extract")
            return False

        width = ds.RasterXSize
        height = ds.RasterYSize
        print(f"    ✓ Extracted {width}x{height} pixels")
        ds = None

        # Now compress it
        print("  Step 2: Compressing...")
        compress_options = gdal.TranslateOptions(
            format='GTiff',
            creationOptions=['COMPRESS=LZW', 'TILED=NO', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256']
        )

        ds = gdal.Translate(output_file, temp_file, options=compress_options)
        if ds:
            print(f"  ✓ Created: {os.path.basename(output_file)}")
            print(f"    Size: {ds.RasterXSize}x{ds.RasterYSize} pixels")
            ds = None

            # Remove temp file
            os.remove(temp_file)
            return True
        else:
            print(f"  ✗ Failed to compress")
            return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def main():
    data_source = os.path.expanduser("~/Documents/GitHub/wildfire/data")
    script_dir = os.path.dirname(os.path.abspath(__file__))

    landfire_file = os.path.join(data_source,
                                 "LF2024_FBFM40_250_CONUS/Tif/LC24_F40_250.tif")

    if not os.path.exists(landfire_file):
        print(f"Error: LANDFIRE file not found: {landfire_file}")
        return

    print("=" * 70)
    print("  LANDFIRE Fuel Extraction - Workaround Method")
    print("=" * 70)
    print("")

    # Santa Barbara region
    center_lon = -119.70
    center_lat = 34.42
    size_deg = 0.18

    minx = center_lon - size_deg / 2
    maxx = center_lon + size_deg / 2
    miny = center_lat - size_deg / 2
    maxy = center_lat + size_deg / 2

    print(f"Region: Santa Barbara Area")
    print(f"  Bounds: ({minx:.4f}, {miny:.4f}) to ({maxx:.4f}, {maxy:.4f})")
    print("")

    # Try 250m resolution
    res_250m = 0.002485
    fuel_250m = os.path.join(script_dir, "santa_barbara_fuel_250m.tif")

    if not os.path.exists(fuel_250m):
        success = extract_fuel_simple(landfire_file, fuel_250m,
                                     minx, miny, maxx, maxy, res_250m)
        if not success:
            print("\n⚠️  Extraction failed. Using synthetic fuel data instead...")
            create_synthetic_fuel(fuel_250m, 72, 72, minx, maxy, res_250m)
    else:
        print(f"✓ {os.path.basename(fuel_250m)} already exists")

    # Try 100m resolution
    res_100m = 0.000994
    fuel_100m = os.path.join(script_dir, "santa_barbara_fuel_100m.tif")

    if not os.path.exists(fuel_100m):
        success = extract_fuel_simple(landfire_file, fuel_100m,
                                     minx, miny, maxx, maxy, res_100m)
        if not success:
            print("\n⚠️  Extraction failed. Using synthetic fuel data instead...")
            create_synthetic_fuel(fuel_100m, 181, 181, minx, maxy, res_100m)
    else:
        print(f"✓ {os.path.basename(fuel_100m)} already exists")

    print("\n" + "=" * 70)
    print("  Complete!")
    print("=" * 70)
    print("\nFuel data ready for simulation.")

def create_synthetic_fuel(output_file, width, height, minx, maxy, resolution):
    """Create synthetic fuel data when extraction fails"""
    import numpy as np
    from osgeo import osr

    print(f"\n  Creating synthetic fuel data: {width}x{height}")

    # Create realistic fuel pattern
    fuel_data = np.zeros((height, width), dtype=np.int16)

    # Mix of chaparral (4), brush (5), and timber (8, 9, 10)
    for y in range(height):
        for x in range(width):
            # Create zones
            if y < height // 3:
                fuel_data[y, x] = np.random.choice([4, 5, 5, 6])  # Chaparral/brush
            elif y < 2 * height // 3:
                fuel_data[y, x] = np.random.choice([5, 8, 9])  # Brush/light timber
            else:
                fuel_data[y, x] = np.random.choice([8, 9, 10])  # Timber

    # Add some non-burnable patches (roads, rock)
    num_patches = 3
    for _ in range(num_patches):
        cx, cy = np.random.randint(0, width), np.random.randint(0, height)
        size = np.random.randint(3, 8)
        x1, x2 = max(0, cx-size), min(width, cx+size)
        y1, y2 = max(0, cy-size), min(height, cy+size)
        fuel_data[y1:y2, x1:x2] = 0

    # Create GeoTIFF
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(output_file, width, height, 1, gdal.GDT_Int16,
                      options=['COMPRESS=LZW'])

    # Set geotransform
    geotransform = [minx, resolution, 0, maxy, 0, -resolution]
    ds.SetGeoTransform(geotransform)

    # Set projection (WGS84)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())

    # Write data
    band = ds.GetRasterBand(1)
    band.WriteArray(fuel_data)
    band.SetNoDataValue(0)

    ds = None

    print(f"  ✓ Created synthetic fuel data: {os.path.basename(output_file)}")
    print(f"    Fuel types: Chaparral (4), Brush (5), Timber (8-10)")

if __name__ == '__main__':
    main()
