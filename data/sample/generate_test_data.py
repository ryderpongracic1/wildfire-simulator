#!/usr/bin/env python3
"""
Generate synthetic test data for wildfire simulator
Creates GeoTIFF files with simulated fuel types and elevation
"""

import numpy as np
from osgeo import gdal, osr
import os

def create_geotiff(filename, data, geotransform, projection, nodata_value=None):
    """Create a GeoTIFF file from numpy array"""
    driver = gdal.GetDriverByName('GTiff')
    rows, cols = data.shape

    # Determine data type
    if data.dtype == np.int32 or data.dtype == np.int16:
        gdal_dtype = gdal.GDT_Int32
    else:
        gdal_dtype = gdal.GDT_Float32

    dataset = driver.Create(filename, cols, rows, 1, gdal_dtype)
    dataset.SetGeoTransform(geotransform)
    dataset.SetProjection(projection)

    band = dataset.GetRasterBand(1)
    band.WriteArray(data)

    if nodata_value is not None:
        band.SetNoDataValue(nodata_value)

    band.FlushCache()
    dataset = None

    print(f"Created {filename} ({rows}x{cols})")


def generate_fuel_data(rows, cols):
    """Generate synthetic fuel type data"""
    fuel_data = np.zeros((rows, cols), dtype=np.int32)

    # Create different fuel zones
    # Bottom third: grassland (fuel type 1-3)
    fuel_data[:rows//3, :] = np.random.choice([1, 2, 3], size=(rows//3, cols))

    # Middle third: brush and chaparral (fuel type 4-5)
    fuel_data[rows//3:2*rows//3, :] = np.random.choice([4, 5, 6], size=(rows//3, cols))

    # Top third: timber (fuel type 8-10)
    fuel_data[2*rows//3:, :] = np.random.choice([8, 9, 10], size=(rows-2*rows//3, cols))

    # Add some random heavy fuel patches (slash)
    num_patches = 5
    for _ in range(num_patches):
        cx, cy = np.random.randint(0, cols), np.random.randint(0, rows)
        size = np.random.randint(20, 40)
        x1, x2 = max(0, cx-size), min(cols, cx+size)
        y1, y2 = max(0, cy-size), min(rows, cy+size)
        fuel_data[y1:y2, x1:x2] = 12  # Medium slash

    # Add non-burnable areas (water, rock)
    num_water = 3
    for _ in range(num_water):
        cx, cy = np.random.randint(0, cols), np.random.randint(0, rows)
        size = np.random.randint(10, 30)
        x1, x2 = max(0, cx-size), min(cols, cx+size)
        y1, y2 = max(0, cy-size), min(rows, cy+size)
        fuel_data[y1:y2, x1:x2] = 0  # Non-burnable

    return fuel_data


def generate_elevation_data(rows, cols):
    """Generate synthetic elevation data with realistic terrain"""
    # Create base elevation
    elevation = np.zeros((rows, cols), dtype=np.float32)

    # Add large-scale terrain (hills/valleys)
    x = np.linspace(0, 4*np.pi, cols)
    y = np.linspace(0, 4*np.pi, rows)
    X, Y = np.meshgrid(x, y)

    # Multiple sine waves for varied terrain
    elevation += 200 * np.sin(X) * np.cos(Y)
    elevation += 150 * np.cos(X/2) * np.sin(Y/2)
    elevation += 100 * np.sin(X*1.5) * np.cos(Y*1.5)

    # Add random noise for roughness
    elevation += np.random.normal(0, 20, (rows, cols))

    # Overall slope (lower left to upper right)
    slope_x = np.linspace(0, 300, cols)
    slope_y = np.linspace(0, 400, rows)
    Slope_X, Slope_Y = np.meshgrid(slope_x, slope_y)
    elevation += Slope_X + Slope_Y

    # Add some peaks
    num_peaks = 4
    for _ in range(num_peaks):
        cx, cy = np.random.randint(0, cols), np.random.randint(0, rows)
        peak_height = np.random.uniform(300, 500)

        for i in range(rows):
            for j in range(cols):
                dist = np.sqrt((i-cy)**2 + (j-cx)**2)
                elevation[i, j] += peak_height * np.exp(-(dist**2) / 1000)

    # Ensure all elevations are positive
    elevation -= elevation.min()
    elevation += 100  # Base elevation of 100m

    return elevation


def main():
    """Generate test datasets"""
    # Parameters
    rows, cols = 300, 300  # Grid size
    cell_size = 30  # 30 meters (LANDFIRE standard)

    # Geographic extent (example: California Sierra Nevada)
    # Center approximately at 38.5°N, 120.5°W
    center_lat = 38.5
    center_lon = -120.5

    # Calculate extent (approximate, using degrees)
    width_deg = (cols * cell_size) / 111320  # meters to degrees at equator
    height_deg = (rows * cell_size) / 110540  # meters to degrees

    min_lon = center_lon - width_deg / 2
    max_lon = center_lon + width_deg / 2
    min_lat = center_lat - height_deg / 2
    max_lat = center_lat + height_deg / 2

    # Geotransform: [top-left x, pixel width, 0, top-left y, 0, -pixel height]
    pixel_width = (max_lon - min_lon) / cols
    pixel_height = (max_lat - min_lat) / rows

    geotransform = (
        min_lon,        # top-left x
        pixel_width,    # pixel width
        0,              # rotation (0 for north-up)
        max_lat,        # top-left y
        0,              # rotation (0 for north-up)
        -pixel_height   # pixel height (negative for north-up)
    )

    # Projection: WGS84 (EPSG:4326)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    projection = srs.ExportToWkt()

    # Create output directory
    output_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)

    # Generate and save fuel data
    print("Generating fuel type data...")
    fuel_data = generate_fuel_data(rows, cols)
    fuel_file = os.path.join(output_dir, 'test_fuel_model.tif')
    create_geotiff(fuel_file, fuel_data, geotransform, projection, nodata_value=0)

    print(f"\nFuel type distribution:")
    unique, counts = np.unique(fuel_data, return_counts=True)
    for fuel_type, count in zip(unique, counts):
        pct = 100 * count / fuel_data.size
        print(f"  Type {fuel_type}: {count} cells ({pct:.1f}%)")

    # Generate and save elevation data
    print("\n\nGenerating elevation data...")
    elevation_data = generate_elevation_data(rows, cols)
    elevation_file = os.path.join(output_dir, 'test_elevation.tif')
    create_geotiff(elevation_file, elevation_data, geotransform, projection)

    print(f"\nElevation statistics:")
    print(f"  Min: {elevation_data.min():.1f} m")
    print(f"  Max: {elevation_data.max():.1f} m")
    print(f"  Mean: {elevation_data.mean():.1f} m")
    print(f"  Std: {elevation_data.std():.1f} m")

    # Calculate slope statistics
    slope = np.zeros_like(elevation_data)
    for i in range(1, rows-1):
        for j in range(1, cols-1):
            dz_dx = (elevation_data[i, j+1] - elevation_data[i, j-1]) / (2 * cell_size)
            dz_dy = (elevation_data[i+1, j] - elevation_data[i-1, j]) / (2 * cell_size)
            slope[i, j] = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)) * 180 / np.pi

    print(f"\nSlope statistics:")
    print(f"  Mean: {slope.mean():.1f}°")
    print(f"  Max: {slope.max():.1f}°")

    # Print usage instructions
    print("\n" + "="*60)
    print("Test data generated successfully!")
    print("="*60)
    print(f"\nFiles created:")
    print(f"  - {fuel_file}")
    print(f"  - {elevation_file}")
    print(f"\nExtent:")
    print(f"  Longitude: {min_lon:.4f}° to {max_lon:.4f}°")
    print(f"  Latitude: {min_lat:.4f}° to {max_lat:.4f}°")
    print(f"  Grid: {rows}x{cols} cells at {cell_size}m resolution")
    print(f"\nSuggested ignition point: ({cols//2}, {rows//2})")
    print(f"Suggested wind: 10-15 mph from West (270°)")
    print(f"Suggested fuel moisture: 6-10%")
    print(f"\nUse these files in your simulation configuration!")


if __name__ == '__main__':
    main()
