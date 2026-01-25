#include "GeoDataLoader.h"
#include <gdal_priv.h>
#include <cpl_conv.h>
#include <iostream>

void GeoDataLoader::loadIntRaster(const std::string& filename,
                                 std::vector<int>& data,
                                 GeoBounds& bounds) {
    GDALAllRegister();

    GDALDataset* dataset = (GDALDataset*)GDALOpen(filename.c_str(), GA_ReadOnly);
    if (dataset == nullptr) {
        throw std::runtime_error("Failed to open raster file: " + filename);
    }

    // Get raster dimensions
    bounds.width = dataset->GetRasterXSize();
    bounds.height = dataset->GetRasterYSize();

    // Get geotransform (maps pixel coordinates to geographic coordinates)
    double geoTransform[6];
    if (dataset->GetGeoTransform(geoTransform) == CE_None) {
        bounds.minX = geoTransform[0];
        bounds.pixelSizeX = geoTransform[1];
        bounds.maxY = geoTransform[3];
        bounds.pixelSizeY = geoTransform[5]; // Usually negative

        bounds.maxX = bounds.minX + bounds.width * bounds.pixelSizeX;
        bounds.minY = bounds.maxY + bounds.height * bounds.pixelSizeY;
    }

    // Read raster band (usually band 1)
    GDALRasterBand* band = dataset->GetRasterBand(1);
    if (band == nullptr) {
        GDALClose(dataset);
        throw std::runtime_error("Failed to get raster band");
    }

    // Allocate data buffer
    data.resize(bounds.width * bounds.height);

    // Read data based on data type
    GDALDataType dataType = band->GetRasterDataType();

    if (dataType == GDT_Byte || dataType == GDT_Int16 || dataType == GDT_Int32) {
        // Read directly as integers
        std::vector<int> buffer(bounds.width * bounds.height);
        CPLErr err = band->RasterIO(GF_Read, 0, 0, bounds.width, bounds.height,
                                    buffer.data(), bounds.width, bounds.height,
                                    GDT_Int32, 0, 0);

        if (err != CE_None) {
            GDALClose(dataset);
            throw std::runtime_error("Failed to read raster data");
        }

        data = buffer;
    } else {
        // Read as float and convert
        std::vector<float> buffer(bounds.width * bounds.height);
        CPLErr err = band->RasterIO(GF_Read, 0, 0, bounds.width, bounds.height,
                                    buffer.data(), bounds.width, bounds.height,
                                    GDT_Float32, 0, 0);

        if (err != CE_None) {
            GDALClose(dataset);
            throw std::runtime_error("Failed to read raster data");
        }

        for (size_t i = 0; i < buffer.size(); ++i) {
            data[i] = static_cast<int>(buffer[i]);
        }
    }

    // Handle NoData values
    int hasNoData;
    double noDataValue = band->GetNoDataValue(&hasNoData);
    if (hasNoData) {
        for (auto& val : data) {
            if (val == static_cast<int>(noDataValue)) {
                val = 0; // Set to non-burnable
            }
        }
    }

    GDALClose(dataset);
}

void GeoDataLoader::loadFloatRaster(const std::string& filename,
                                   std::vector<double>& data,
                                   GeoBounds& bounds) {
    GDALAllRegister();

    GDALDataset* dataset = (GDALDataset*)GDALOpen(filename.c_str(), GA_ReadOnly);
    if (dataset == nullptr) {
        throw std::runtime_error("Failed to open raster file: " + filename);
    }

    // Get raster dimensions
    bounds.width = dataset->GetRasterXSize();
    bounds.height = dataset->GetRasterYSize();

    // Get geotransform
    double geoTransform[6];
    if (dataset->GetGeoTransform(geoTransform) == CE_None) {
        bounds.minX = geoTransform[0];
        bounds.pixelSizeX = geoTransform[1];
        bounds.maxY = geoTransform[3];
        bounds.pixelSizeY = geoTransform[5];

        bounds.maxX = bounds.minX + bounds.width * bounds.pixelSizeX;
        bounds.minY = bounds.maxY + bounds.height * bounds.pixelSizeY;
    }

    // Read raster band
    GDALRasterBand* band = dataset->GetRasterBand(1);
    if (band == nullptr) {
        GDALClose(dataset);
        throw std::runtime_error("Failed to get raster band");
    }

    // Allocate data buffer
    data.resize(bounds.width * bounds.height);

    // Read as double
    CPLErr err = band->RasterIO(GF_Read, 0, 0, bounds.width, bounds.height,
                                data.data(), bounds.width, bounds.height,
                                GDT_Float64, 0, 0);

    if (err != CE_None) {
        GDALClose(dataset);
        throw std::runtime_error("Failed to read raster data");
    }

    // Handle NoData values
    int hasNoData;
    double noDataValue = band->GetNoDataValue(&hasNoData);
    if (hasNoData) {
        for (auto& val : data) {
            if (val == noDataValue) {
                val = 0.0;
            }
        }
    }

    GDALClose(dataset);
}

void GeoDataLoader::loadIntRasterSubset(const std::string& filename,
                                       std::vector<int>& data,
                                       const GeoBounds& requestedBounds,
                                       GeoBounds& actualBounds) {
    GDALAllRegister();

    GDALDataset* dataset = (GDALDataset*)GDALOpen(filename.c_str(), GA_ReadOnly);
    if (dataset == nullptr) {
        throw std::runtime_error("Failed to open raster file: " + filename);
    }

    // Get full raster bounds
    int fullWidth = dataset->GetRasterXSize();
    int fullHeight = dataset->GetRasterYSize();

    double geoTransform[6];
    dataset->GetGeoTransform(geoTransform);

    // Convert requested geographic bounds to pixel coordinates
    // Create full bounds structure
    GeoBounds fullBounds;
    fullBounds.minX = geoTransform[0];
    fullBounds.maxX = geoTransform[0] + fullWidth * geoTransform[1];
    fullBounds.minY = geoTransform[3] + fullHeight * geoTransform[5];
    fullBounds.maxY = geoTransform[3];
    fullBounds.width = fullWidth;
    fullBounds.height = fullHeight;
    fullBounds.pixelSizeX = geoTransform[1];
    fullBounds.pixelSizeY = geoTransform[5];

    int xOff, yOff;
    geoToGrid(requestedBounds.minX, requestedBounds.maxY, fullBounds, xOff, yOff);

    int xSize, ySize;
    geoToGrid(requestedBounds.maxX, requestedBounds.minY, fullBounds, xSize, ySize);

    xSize = xSize - xOff;
    ySize = ySize - yOff;

    // Clamp to raster bounds
    xOff = std::max(0, std::min(xOff, fullWidth));
    yOff = std::max(0, std::min(yOff, fullHeight));
    xSize = std::max(0, std::min(xSize, fullWidth - xOff));
    ySize = std::max(0, std::min(ySize, fullHeight - yOff));

    // Update actual bounds
    actualBounds.width = xSize;
    actualBounds.height = ySize;
    actualBounds.pixelSizeX = geoTransform[1];
    actualBounds.pixelSizeY = geoTransform[5];
    actualBounds.minX = geoTransform[0] + xOff * geoTransform[1];
    actualBounds.maxY = geoTransform[3] + yOff * geoTransform[5];
    actualBounds.maxX = actualBounds.minX + xSize * geoTransform[1];
    actualBounds.minY = actualBounds.maxY + ySize * geoTransform[5];

    // Read subset
    GDALRasterBand* band = dataset->GetRasterBand(1);
    data.resize(xSize * ySize);

    CPLErr err = band->RasterIO(GF_Read, xOff, yOff, xSize, ySize,
                                data.data(), xSize, ySize,
                                GDT_Int32, 0, 0);

    if (err != CE_None) {
        GDALClose(dataset);
        throw std::runtime_error("Failed to read raster subset");
    }

    GDALClose(dataset);
}

void GeoDataLoader::gridToGeo(int x, int y, const GeoBounds& bounds,
                             double& geoX, double& geoY) {
    geoX = bounds.minX + x * bounds.pixelSizeX;
    geoY = bounds.maxY + y * bounds.pixelSizeY;
}

void GeoDataLoader::geoToGrid(double geoX, double geoY, const GeoBounds& bounds,
                             int& x, int& y) {
    x = static_cast<int>((geoX - bounds.minX) / bounds.pixelSizeX);
    y = static_cast<int>((geoY - bounds.maxY) / bounds.pixelSizeY);
}
