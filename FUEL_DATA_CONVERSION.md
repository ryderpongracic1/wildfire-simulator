# Fuel Data Conversion Guide

## Overview

The wildfire simulator requires fuel data in **Anderson 13 fuel model format** (values 0-13). If you have LANDFIRE FBFM40 data (values 101-204), you'll need to convert it first.

## Anderson 13 Fuel Models

The simulator uses these 14 fuel types:

| Value | Fuel Type | Description |
|-------|-----------|-------------|
| 0 | No fuel | Non-burnable areas (water, rock, urban) |
| 1 | Short grass | 1 ft tall grass |
| 2 | Timber (grass and understory) | Forest with grass understory |
| 3 | Tall grass | 2.5 ft tall grass |
| 4 | Chaparral | 6 ft tall chaparral |
| 5 | Brush | 2 ft tall brush |
| 6 | Dormant brush | Hardwood slash |
| 7 | Southern rough | Heavy forest litter |
| 8 | Closed timber litter | Compact conifer litter |
| 9 | Hardwood litter | Deciduous forest litter |
| 10 | Timber (litter and understory) | Forest with heavy understory |
| 11 | Light logging slash | Light fuel loading |
| 12 | Medium logging slash | Medium fuel loading |
| 13 | Heavy logging slash | Heavy fuel loading |

## Converting FBFM40 to Anderson 13

### Using the Provided Script

1. Ensure you have Python with GDAL/OGR installed:
   ```bash
   pip install gdal numpy
   ```

2. Run the conversion script:
   ```bash
   python scripts/remap_fbfm40_to_anderson13.py input_fbfm40.tif output_anderson13.tif
   ```

3. Upload the converted file through the web interface

### Manual Conversion

If you need to customize the mapping, edit the `fbfm40_to_anderson13` dictionary in the script:

```python
fbfm40_to_anderson13 = {
    101: 1,  # Short grass -> Anderson 1
    102: 3,  # Low load grass -> Anderson 3
    121: 4,  # Grass-shrub -> Anderson 4
    # ... etc
}
```

## File Requirements

### GeoTIFF Format
- **File extension**: `.tif` or `.tiff`
- **Data type**: Byte (8-bit unsigned integer) or Int16
- **Projection**: Any (NAD83 Conus Albers EPSG:5070 recommended)
- **NoData value**: 0 or 32767

### Fuel Data
- **Values**: 0-13 only
- **Resolution**: Any (30m or 100m recommended)
- **Extent**: Any size

### Elevation Data
- **Values**: Meters above sea level
- **Resolution**: Must match fuel data exactly
- **Dimensions**: Must match fuel data exactly
- **Projection**: Must match fuel data exactly

## Data Sources

### Compatible Data
- **Custom Anderson 13 files** - Upload directly
- **Converted FBFM40** - Use conversion script first

### Data to Convert
- **LANDFIRE FBFM40** (fbfm40 or fbfm2020) - Convert first
- **LANDFIRE FBFM13** - May need value verification

## Example Workflow

1. **Download LANDFIRE data** for your area of interest
   - Visit https://landfire.gov/
   - Download FBFM40 (Fuel Model) and DEM (Elevation)

2. **Convert FBFM40 to Anderson 13**
   ```bash
   python scripts/remap_fbfm40_to_anderson13.py \
       landfire_fbfm40.tif \
       fuel_anderson13.tif
   ```

3. **Ensure elevation matches**
   ```bash
   gdalwarp -tr 30 30 -t_srs EPSG:5070 \
       -te <xmin> <ymin> <xmax> <ymax> \
       landfire_dem.tif elevation_aligned.tif
   ```

4. **Verify dimensions match**
   ```bash
   gdalinfo fuel_anderson13.tif | grep "Size is"
   gdalinfo elevation_aligned.tif | grep "Size is"
   # Should show same dimensions
   ```

5. **Upload through web interface**
   - Open http://localhost:8080
   - Scroll to "Upload Custom Data"
   - Select your converted fuel and aligned elevation files
   - Click "Upload Files"

## Troubleshooting

### "No fire spread" or "0 cells burned"
- **Problem**: Fuel data is not in Anderson 13 format
- **Solution**: Convert your fuel data using the script

### "Dimensions don't match"
- **Problem**: Fuel and elevation files have different sizes
- **Solution**: Use `gdalwarp` to align elevation to fuel grid

### "Invalid fuel values"
- **Problem**: Fuel values outside 0-13 range
- **Solution**: Re-run conversion script, check for errors

### Upload fails
- **Problem**: File format not recognized
- **Solution**: Ensure file is GeoTIFF (.tif), check with `gdalinfo`

## Additional Resources

- LANDFIRE: https://landfire.gov/
- GDAL documentation: https://gdal.org/
- Anderson fuel models: https://www.fs.usda.gov/rm/pubs_int/int_gtr122.pdf

## Questions?

If you encounter issues with fuel data conversion or have questions about compatibility, please open an issue on the GitHub repository.
