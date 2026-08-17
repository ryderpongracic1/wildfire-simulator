#ifndef FIRE_SPREAD_MODEL_H
#define FIRE_SPREAD_MODEL_H

#include <vector>
#include <string>
#include <cmath>
#include <algorithm>

/**
 * LANDFIRE 13 Anderson Fuel Model Classifications
 * Each fuel type has different burning characteristics
 */
enum FuelType {
    FUEL_NONE = 0,           // Non-burnable (water, rock, urban)
    FUEL_SHORT_GRASS = 1,    // Short grass (1 ft)
    FUEL_TIMBER_GRASS = 2,   // Timber grass and understory
    FUEL_TALL_GRASS = 3,     // Tall grass (2.5 ft)
    FUEL_CHAPARRAL = 4,      // Chaparral (6 ft)
    FUEL_BRUSH = 5,          // Brush (2 ft)
    FUEL_DORMANT_BRUSH = 6,  // Dormant brush
    FUEL_SOUTHERN_ROUGH = 7, // Southern rough
    FUEL_COMPACT_TIMBER = 8, // Compact timber litter
    FUEL_HARDWOOD_LITTER = 9,// Hardwood litter
    FUEL_TIMBER = 10,        // Timber (litter and understory)
    FUEL_LIGHT_SLASH = 11,   // Light logging slash
    FUEL_MEDIUM_SLASH = 12,  // Medium logging slash
    FUEL_HEAVY_SLASH = 13    // Heavy logging slash
};

/**
 * Fuel model properties based on Rothermel fire spread equations
 * Values calibrated from LANDFIRE fuel characteristics database
 */
struct FuelProperties {
    double fuelLoad;         // Fuel loading (tons/acre)
    double sav;              // Surface area to volume ratio (ft^-1)
    double fuelDepth;        // Fuel bed depth (ft)
    double moistureExt;      // Moisture of extinction (%)
    double heatContent;      // Heat content (BTU/lb)

    FuelProperties(double load = 0.0, double savRatio = 1.0, double depth = 0.1,
                   double moisture = 30.0, double heat = 8000.0)
        : fuelLoad(load), sav(savRatio), fuelDepth(depth),
          moistureExt(moisture), heatContent(heat) {}
};

/**
 * Cellular automaton cell state
 */
struct Cell {
    FuelType fuelType;
    double elevation;        // Elevation in meters
    int burnStatus;          // 0=unburned, 1=burning, 2=burned
    double ignitionTime;     // Simulation time when ignited (minutes)
    double slopeAngle;       // Slope angle in degrees
    double slopeAspect;      // Slope aspect (direction) in degrees from North

    Cell() : fuelType(FUEL_NONE), elevation(0.0), burnStatus(0),
             ignitionTime(-1.0), slopeAngle(0.0), slopeAspect(0.0) {}
};

/**
 * FireSpreadModel - Implements Rothermel fire spread equations
 * with cellular automaton approach and OpenMP parallelization
 */
class FireSpreadModel {
private:
    int width;
    int height;
    double cellSize;         // Cell size in meters (typically 30m for LANDFIRE)
    std::vector<Cell> grid;
    std::vector<Cell> nextGrid;

    // Simulation parameters
    double windSpeed;        // Wind speed (mph)
    double windDirection;    // Wind direction (degrees from North)
    double fuelMoisture;     // Fuel moisture content (%)
    double simulationTime;   // Current simulation time (minutes)
    double timeStep;         // Time step (minutes)

    // Fuel properties lookup table
    std::vector<FuelProperties> fuelPropertiesTable;

    /**
     * Initialize fuel properties table with LANDFIRE 13 fuel model data
     */
    void initializeFuelProperties();

    /**
     * Calculate rate of spread using Rothermel equation
     * @param fuel Fuel properties
     * @param slope Slope angle in degrees
     * @param windSpeed Wind speed in mph
     * @return Rate of spread in feet per minute
     */
    double calculateRateOfSpread(const FuelProperties& fuel, double slope,
                                 double windSpeed) const;

    /**
     * Calculate wind factor effect on spread rate
     */
    double calculateWindFactor(const FuelProperties& fuel, double windSpeed) const;

    /**
     * Calculate slope factor effect on spread rate
     */
    double calculateSlopeFactor(double slopeAngle) const;

    /**
     * Calculate directional rate of spread (cells per minute) from a burning
     * cell into a neighboring cell, accounting for wind and slope alignment
     * with the spread direction.
     */
    double calculateSpreadRate(int fromX, int fromY, int toX, int toY) const;

    /**
     * Get cell at position with boundary checking
     */
    const Cell& getCell(int x, int y) const;
    Cell& getCell(int x, int y);

    /**
     * Calculate slope between two cells
     */
    void calculateSlope(int x, int y);

public:
    FireSpreadModel(int width, int height, double cellSize);

    /**
     * Load fuel type data from array
     */
    void loadFuelData(const std::vector<int>& fuelData);

    /**
     * Load elevation data from array
     */
    void loadElevationData(const std::vector<double>& elevationData);

    /**
     * Set simulation parameters
     */
    void setWindParameters(double speed, double direction);
    void setFuelMoisture(double moisture);
    void setTimeStep(double dt);

    /**
     * Set ignition point
     */
    void igniteCell(int x, int y);

    /**
     * Run one simulation time step
     * Uses OpenMP for parallel processing
     */
    void step();

    /**
     * Get current grid state
     */
    const std::vector<Cell>& getGrid() const { return grid; }

    /**
     * Get current simulation time
     */
    double getSimulationTime() const { return simulationTime; }

    /**
     * Get grid dimensions
     */
    int getWidth() const { return width; }
    int getHeight() const { return height; }
    double getCellSize() const { return cellSize; }

    /**
     * Export burned area as polygon coordinates
     */
    std::vector<std::pair<double, double>> getBurnedPerimeter() const;

    /**
     * Get statistics
     */
    int getBurnedCellCount() const;
    int getBurningCellCount() const;
};

#endif // FIRE_SPREAD_MODEL_H
