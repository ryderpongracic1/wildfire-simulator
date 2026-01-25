#!/usr/bin/env python3
"""
Remap LANDFIRE FBFM40 fuel models to Anderson 13 fuel models
FBFM40 uses values 101-204, but the simulator expects Anderson 13 models (0-13)
"""

import sys
from osgeo import gdal
import numpy as np

# Mapping from FBFM40 to Anderson 13
# Based on fuel characteristics similarity
fbfm40_to_anderson13 = {
    # Grass and Grass-dominated (GR)
    101: 1,  # Short grass -> Anderson 1 (Short grass)
    102: 3,  # Low load, dry climate grass -> Anderson 3 (Tall grass)
    103: 3,  # Low load, very coarse -> Anderson 3
    104: 3,  # Moderate load, dry climate grass -> Anderson 3
    105: 3,  # Low load, humid climate grass -> Anderson 3
    106: 3,  # Moderate load, humid climate grass -> Anderson 3
    107: 3,  # High load, dry climate grass -> Anderson 3
    108: 3,  # High load, very coarse -> Anderson 3
    109: 3,  # Very high load, humid climate grass -> Anderson 3

    # Grass-Shrub (GS)
    121: 4,  # Low load, dry climate grass-shrub -> Anderson 4 (Chaparral)
    122: 5,  # Moderate load, dry climate grass-shrub -> Anderson 5 (Brush)
    123: 4,  # Moderate load, humid climate grass-shrub -> Anderson 4
    124: 5,  # High load, humid climate grass-shrub -> Anderson 5

    # Shrub (SH)
    141: 5,  # Low load, dry climate shrub -> Anderson 5 (Brush)
    142: 5,  # Moderate load, dry climate shrub -> Anderson 5
    143: 6,  # Moderate load, humid climate shrub -> Anderson 6 (Dormant brush)
    144: 5,  # Low load, humid climate shrub -> Anderson 5
    145: 5,  # High load, dry climate shrub -> Anderson 5
    146: 6,  # Low load, humid climate shrub -> Anderson 6
    147: 6,  # Very high load, dry climate shrub -> Anderson 6
    148: 5,  # Low load, humid climate shrub -> Anderson 5
    149: 5,  # High load, humid climate shrub -> Anderson 5

    # Timber-Understory (TU)
    161: 8,  # Light load, dry climate timber-grass-shrub -> Anderson 8 (Compact timber litter)
    162: 8,  # Moderate load, dry climate timber-shrub -> Anderson 8
    163: 9,  # Moderate load, humid climate timber-grass-shrub -> Anderson 9 (Hardwood litter)
    164: 10, # Dwarf conifer with understory -> Anderson 10 (Timber litter & understory)
    165: 8,  # Light load, humid climate timber-shrub -> Anderson 8

    # Timber Litter (TL)
    181: 8,  # Low load, compact conifer litter -> Anderson 8 (Compact timber litter)
    182: 9,  # Low load, broadleaf litter -> Anderson 9 (Hardwood litter)
    183: 8,  # Moderate load conifer litter -> Anderson 8
    184: 10, # Small downed logs -> Anderson 10 (Timber litter & understory)
    185: 10, # High load conifer litter -> Anderson 10
    186: 10, # Moderate load, broadleaf litter -> Anderson 10
    187: 11, # Large downed logs -> Anderson 11 (Light logging slash)
    188: 11, # Long-needle pine litter -> Anderson 11
    189: 11, # Very high load, broadleaf litter -> Anderson 11

    # Slash-Blowdown (SB)
    201: 11, # Low load activity fuel -> Anderson 11 (Light logging slash)
    202: 12, # Moderate load activity fuel -> Anderson 12 (Medium logging slash)
    203: 13, # High load activity fuel -> Anderson 13 (Heavy logging slash)
    204: 13, # Very high load activity fuel -> Anderson 13

    # Non-burnable (NB)
    91: 0,   # Urban/Developed -> No fuel
    92: 0,   # Snow/Ice -> No fuel
    93: 0,   # Agriculture -> No fuel
    98: 0,   # Water -> No fuel
    99: 0,   # Barren -> No fuel
}

def remap_fuel_data(input_file, output_file):
    """Remap FBFM40 fuel data to Anderson 13"""

    print(f"Reading {input_file}...")
    ds = gdal.Open(input_file)
    if ds is None:
        print(f"Error: Could not open {input_file}")
        return False

    band = ds.GetRasterBand(1)
    data = band.ReadAsArray()

    print(f"Input data shape: {data.shape}")
    print(f"Input data range: {data.min()} to {data.max()}")

    # Count unique values
    unique_values = np.unique(data)
    print(f"Found {len(unique_values)} unique fuel values")

    # Create output array
    output_data = np.zeros_like(data, dtype=np.uint8)

    # Remap values
    remapped_count = 0
    unmapped_count = 0

    for old_val in unique_values:
        if old_val in fbfm40_to_anderson13:
            new_val = fbfm40_to_anderson13[old_val]
            output_data[data == old_val] = new_val
            remapped_count += np.sum(data == old_val)
        else:
            # Unknown values -> no fuel (0)
            output_data[data == old_val] = 0
            unmapped_count += np.sum(data == old_val)
            if old_val != 0:  # Don't warn about existing zeros
                print(f"Warning: Unmapped value {old_val} -> setting to 0 (no fuel)")

    print(f"\nRemapped {remapped_count} cells")
    print(f"Set {unmapped_count} cells to no fuel (unmapped values)")
    print(f"Output data range: {output_data.min()} to {output_data.max()}")

    # Create output file
    print(f"\nWriting {output_file}...")
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(
        output_file,
        ds.RasterXSize,
        ds.RasterYSize,
        1,
        gdal.GDT_Byte,
        options=['COMPRESS=LZW', 'TILED=YES']
    )

    out_ds.SetGeoTransform(ds.GetGeoTransform())
    out_ds.SetProjection(ds.GetProjection())

    out_band = out_ds.GetRasterBand(1)
    out_band.WriteArray(output_data)
    out_band.SetNoDataValue(0)

    out_ds.FlushCache()
    out_ds = None
    ds = None

    print("Done!")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python remap_fbfm40_to_anderson13.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    success = remap_fuel_data(input_file, output_file)
    sys.exit(0 if success else 1)
