#ifndef GEO_DATA_LOADER_H
#define GEO_DATA_LOADER_H

#include <string>
#include <vector>
#include <stdexcept>

/**
 * Geographic bounds for raster data
 */
struct GeoBounds {
    double minX, maxX, minY, maxY;
    int width, height;
    double pixelSizeX, pixelSizeY;

    GeoBounds() : minX(0), maxX(0), minY(0), maxY(0),
                  width(0), height(0), pixelSizeX(0), pixelSizeY(0) {}
};

/**
 * GeoDataLoader - Load geospatial raster data using GDAL
 * Supports GeoTIFF format for fuel models and elevation data
 */
class GeoDataLoader {
public:
    /**
     * Load integer raster data (e.g., fuel types)
     * @param filename Path to GeoTIFF file
     * @param data Output vector for raster values
     * @param bounds Output geographic bounds
     */
    static void loadIntRaster(const std::string& filename,
                             std::vector<int>& data,
                             GeoBounds& bounds);

    /**
     * Load floating point raster data (e.g., elevation)
     * @param filename Path to GeoTIFF file
     * @param data Output vector for raster values
     * @param bounds Output geographic bounds
     */
    static void loadFloatRaster(const std::string& filename,
                               std::vector<double>& data,
                               GeoBounds& bounds);

    /**
     * Load subset of raster within geographic bounds
     */
    static void loadIntRasterSubset(const std::string& filename,
                                   std::vector<int>& data,
                                   const GeoBounds& requestedBounds,
                                   GeoBounds& actualBounds);

    /**
     * Convert grid coordinates to geographic coordinates
     */
    static void gridToGeo(int x, int y, const GeoBounds& bounds,
                         double& geoX, double& geoY);

    /**
     * Convert geographic coordinates to grid coordinates
     */
    static void geoToGrid(double geoX, double geoY, const GeoBounds& bounds,
                         int& x, int& y);
};

#endif // GEO_DATA_LOADER_H
