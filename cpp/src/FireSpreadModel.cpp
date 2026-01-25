#include "FireSpreadModel.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#ifndef NO_OPENMP
#include <omp.h>
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

FireSpreadModel::FireSpreadModel(int w, int h, double cellSz)
    : width(w), height(h), cellSize(cellSz), windSpeed(0.0), windDirection(0.0),
      fuelMoisture(8.0), simulationTime(0.0), timeStep(1.0) {

    grid.resize(width * height);
    nextGrid.resize(width * height);
    initializeFuelProperties();
}

void FireSpreadModel::initializeFuelProperties() {
    // Initialize with LANDFIRE 13 Anderson fuel model properties
    // Values based on Rothermel 1972 and Albini 1976

    fuelPropertiesTable.resize(14);

    // Fuel Model 0: Non-burnable
    fuelPropertiesTable[0] = FuelProperties(0.0, 1.0, 0.1, 100.0, 8000.0);

    // Fuel Model 1: Short grass (1 ft)
    fuelPropertiesTable[1] = FuelProperties(0.74, 3500, 1.0, 12.0, 8000.0);

    // Fuel Model 2: Timber (grass and understory)
    fuelPropertiesTable[2] = FuelProperties(2.0, 3000, 1.0, 15.0, 8000.0);

    // Fuel Model 3: Tall grass (2.5 ft)
    fuelPropertiesTable[3] = FuelProperties(3.01, 1500, 2.5, 25.0, 8000.0);

    // Fuel Model 4: Chaparral (6 ft)
    fuelPropertiesTable[4] = FuelProperties(5.01, 2000, 6.0, 20.0, 8000.0);

    // Fuel Model 5: Brush (2 ft)
    fuelPropertiesTable[5] = FuelProperties(2.5, 2000, 2.0, 20.0, 8000.0);

    // Fuel Model 6: Dormant brush, hardwood slash
    fuelPropertiesTable[6] = FuelProperties(2.92, 1750, 2.5, 25.0, 8000.0);

    // Fuel Model 7: Southern rough
    fuelPropertiesTable[7] = FuelProperties(3.5, 1550, 2.5, 40.0, 8000.0);

    // Fuel Model 8: Compact timber litter
    fuelPropertiesTable[8] = FuelProperties(3.0, 2000, 0.2, 30.0, 8000.0);

    // Fuel Model 9: Hardwood litter
    fuelPropertiesTable[9] = FuelProperties(2.92, 2500, 0.2, 25.0, 8000.0);

    // Fuel Model 10: Timber (litter and understory)
    fuelPropertiesTable[10] = FuelProperties(6.0, 2000, 1.0, 25.0, 8000.0);

    // Fuel Model 11: Light logging slash
    fuelPropertiesTable[11] = FuelProperties(3.9, 1500, 1.0, 15.0, 8000.0);

    // Fuel Model 12: Medium logging slash
    fuelPropertiesTable[12] = FuelProperties(13.0, 1500, 2.3, 20.0, 8000.0);

    // Fuel Model 13: Heavy logging slash
    fuelPropertiesTable[13] = FuelProperties(25.0, 1500, 3.0, 25.0, 8000.0);
}

void FireSpreadModel::loadFuelData(const std::vector<int>& fuelData) {
    for (int i = 0; i < width * height && i < static_cast<int>(fuelData.size()); ++i) {
        int fuelValue = fuelData[i];
        if (fuelValue >= 0 && fuelValue <= 13) {
            grid[i].fuelType = static_cast<FuelType>(fuelValue);
        } else {
            grid[i].fuelType = FUEL_NONE;
        }
    }
}

void FireSpreadModel::loadElevationData(const std::vector<double>& elevationData) {
    for (int i = 0; i < width * height && i < static_cast<int>(elevationData.size()); ++i) {
        grid[i].elevation = elevationData[i];
    }

    // Calculate slopes for all cells
#ifndef NO_OPENMP
    #pragma omp parallel for collapse(2)
#endif
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            calculateSlope(x, y);
        }
    }
}

void FireSpreadModel::calculateSlope(int x, int y) {
    // Use finite difference method to calculate slope
    double dz_dx = 0.0, dz_dy = 0.0;

    if (x > 0 && x < width - 1) {
        dz_dx = (getCell(x + 1, y).elevation - getCell(x - 1, y).elevation) / (2.0 * cellSize);
    }

    if (y > 0 && y < height - 1) {
        dz_dy = (getCell(x, y + 1).elevation - getCell(x, y - 1).elevation) / (2.0 * cellSize);
    }

    // Calculate slope angle (rise/run)
    double slopeRise = sqrt(dz_dx * dz_dx + dz_dy * dz_dy);
    getCell(x, y).slopeAngle = atan(slopeRise) * 180.0 / M_PI;

    // Calculate aspect (direction of steepest descent)
    if (dz_dx != 0.0 || dz_dy != 0.0) {
        getCell(x, y).slopeAspect = atan2(dz_dy, dz_dx) * 180.0 / M_PI;
        // Convert to compass bearing (0 = North)
        getCell(x, y).slopeAspect = 90.0 - getCell(x, y).slopeAspect;
        if (getCell(x, y).slopeAspect < 0.0) {
            getCell(x, y).slopeAspect += 360.0;
        }
    }
}

void FireSpreadModel::setWindParameters(double speed, double direction) {
    windSpeed = speed;
    windDirection = direction;
}

void FireSpreadModel::setFuelMoisture(double moisture) {
    fuelMoisture = moisture;
}

void FireSpreadModel::setTimeStep(double dt) {
    timeStep = dt;
}

void FireSpreadModel::igniteCell(int x, int y) {
    if (x >= 0 && x < width && y >= 0 && y < height) {
        int idx = y * width + x;
        if (grid[idx].fuelType != FUEL_NONE) {
            grid[idx].burnStatus = 1;
            grid[idx].ignitionTime = simulationTime;
        }
    }
}

double FireSpreadModel::calculateWindFactor(const FuelProperties& fuel, double windSpeed) const {
    // Simplified wind factor based on Rothermel model
    // Wind coefficient depends on surface-area-to-volume ratio
    double B = 0.02526 * pow(fuel.sav, 0.54);
    double C = 7.47 * exp(-0.133 * pow(fuel.sav, 0.55));
    double E = 0.715 * exp(-3.59e-4 * fuel.sav);

    // Wind speed in ft/min
    double windSpeedFpm = windSpeed * 88.0; // mph to ft/min

    // Phi_w (wind factor)
    double phiW = C * pow(windSpeedFpm, B) * pow(fuel.sav / 0.0001, -E);

    return phiW;
}

double FireSpreadModel::calculateSlopeFactor(double slopeAngle) const {
    // Slope factor based on Rothermel model
    // Phi_s = 5.275 * beta^(-0.3) * (tan(slope))^2
    // Simplified version for cellular automaton
    double slopeRadians = slopeAngle * M_PI / 180.0;
    double tanSlope = tan(slopeRadians);

    // Slope factor (dimensionless)
    double phiS = 5.275 * pow(0.4, -0.3) * tanSlope * tanSlope;

    return phiS;
}

double FireSpreadModel::calculateEffectiveWind(double windSpeed, double windDir,
                                               double slopeAngle, double slopeAspect) const {
    // Calculate effective wind by combining actual wind and slope-induced wind
    // This is a simplified model

    // Slope-induced wind (fire creates upslope draft)
    double slopeWind = slopeAngle * 0.5; // Empirical relationship

    // Combine wind vectors
    double windRad = windDir * M_PI / 180.0;
    double slopeRad = slopeAspect * M_PI / 180.0;

    double windX = windSpeed * sin(windRad);
    double windY = windSpeed * cos(windRad);

    double slopeWindX = slopeWind * sin(slopeRad);
    double slopeWindY = slopeWind * cos(slopeRad);

    double effectiveWindX = windX + slopeWindX;
    double effectiveWindY = windY + slopeWindY;

    return sqrt(effectiveWindX * effectiveWindX + effectiveWindY * effectiveWindY);
}

double FireSpreadModel::calculateRateOfSpread(const FuelProperties& fuel, double slope,
                                              double windSpeed) const {
    // Rothermel rate of spread equation (simplified)

    // Check fuel moisture vs extinction moisture
    if (fuelMoisture >= fuel.moistureExt) {
        return 0.0; // Too wet to burn
    }

    // Reaction intensity (BTU/ft^2/min)
    double moistureDamping = 1.0 - 2.59 * (fuelMoisture / fuel.moistureExt) +
                             5.11 * pow(fuelMoisture / fuel.moistureExt, 2) -
                             3.52 * pow(fuelMoisture / fuel.moistureExt, 3);

    moistureDamping = std::max(0.0, moistureDamping);

    // Reaction intensity
    double reactionIntensity = fuel.fuelLoad * fuel.heatContent * moistureDamping * 0.1;

    // Propagating flux ratio
    double propagatingFlux = 0.048 * reactionIntensity;

    // Wind and slope factors
    double windFactor = calculateWindFactor(fuel, windSpeed);
    double slopeFactor = calculateSlopeFactor(slope);

    // Rate of spread (ft/min)
    double ros = propagatingFlux * (1.0 + windFactor + slopeFactor) / (0.3 * fuel.fuelLoad);

    // Apply realistic bounds
    ros = std::max(0.0, std::min(ros, 300.0)); // Max 300 ft/min

    return ros;
}

double FireSpreadModel::calculateIgnitionProbability(int fromX, int fromY,
                                                     int toX, int toY) const {
    const Cell& fromCell = getCell(fromX, fromY);
    const Cell& toCell = getCell(toX, toY);

    // Can't ignite non-burnable fuel
    if (toCell.fuelType == FUEL_NONE || toCell.burnStatus != 0) {
        return 0.0;
    }

    // Calculate direction of spread
    double dx = toX - fromX;
    double dy = toY - fromY;
    double spreadDirection = atan2(dy, dx) * 180.0 / M_PI;
    spreadDirection = 90.0 - spreadDirection; // Convert to compass bearing
    if (spreadDirection < 0.0) spreadDirection += 360.0;

    // Get fuel properties
    const FuelProperties& fuel = fuelPropertiesTable[toCell.fuelType];

    // Calculate effective wind in spread direction
    double directionDiff = fabs(spreadDirection - windDirection);
    if (directionDiff > 180.0) directionDiff = 360.0 - directionDiff;

    double effectiveWind = windSpeed * cos(directionDiff * M_PI / 180.0);
    effectiveWind = std::max(0.0, effectiveWind);

    // Consider slope effect
    double slopeDiff = fabs(spreadDirection - toCell.slopeAspect);
    if (slopeDiff > 180.0) slopeDiff = 360.0 - slopeDiff;

    double effectiveSlope = toCell.slopeAngle * cos(slopeDiff * M_PI / 180.0);

    // Calculate rate of spread
    double ros = calculateRateOfSpread(fuel, effectiveSlope, effectiveWind);

    // Convert ROS (ft/min) to cells/timestep
    double cellSizeFt = cellSize * 3.28084; // meters to feet
    double spreadRate = (ros * timeStep) / cellSizeFt;

    // Diagonal cells are sqrt(2) farther
    if (dx != 0 && dy != 0) {
        spreadRate /= 1.414;
    }

    // Probability is based on spread rate (0 to 1)
    double probability = std::min(1.0, spreadRate);

    return probability;
}

const Cell& FireSpreadModel::getCell(int x, int y) const {
    static Cell dummyCell;
    if (x < 0 || x >= width || y < 0 || y >= height) {
        return dummyCell;
    }
    return grid[y * width + x];
}

Cell& FireSpreadModel::getCell(int x, int y) {
    static Cell dummyCell;
    if (x < 0 || x >= width || y < 0 || y >= height) {
        return dummyCell;
    }
    return grid[y * width + x];
}

void FireSpreadModel::step() {
    // Copy current grid to next grid
    nextGrid = grid;

    // OpenMP parallel processing of grid cells
    // Each thread processes a subset of cells independently
#ifndef NO_OPENMP
    #pragma omp parallel for collapse(2) schedule(dynamic)
#endif
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int idx = y * width + x;
            Cell& currentCell = nextGrid[idx];

            // Cells that are burning transition to burned after one timestep
            if (grid[idx].burnStatus == 1) {
                currentCell.burnStatus = 2;
            }

            // Check if this cell should ignite
            if (grid[idx].burnStatus == 0 && grid[idx].fuelType != FUEL_NONE) {
                // Check all 8 neighbors
                bool ignited = false;
                double maxProbability = 0.0;

                for (int dy = -1; dy <= 1 && !ignited; ++dy) {
                    for (int dx = -1; dx <= 1 && !ignited; ++dx) {
                        if (dx == 0 && dy == 0) continue;

                        int nx = x + dx;
                        int ny = y + dy;

                        if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
                            int nidx = ny * width + nx;

                            // If neighbor is burning
                            if (grid[nidx].burnStatus == 1) {
                                double prob = calculateIgnitionProbability(nx, ny, x, y);
                                maxProbability = std::max(maxProbability, prob);

                                // Stochastic ignition based on probability
                                if (prob > 0.3) { // Threshold for ignition (lowered to allow better spread)
                                    ignited = true;
                                }
                            }
                        }
                    }
                }

                if (ignited) {
                    currentCell.burnStatus = 1;
                    currentCell.ignitionTime = simulationTime;
                }
            }
        }
    }

    // Swap grids
    grid = nextGrid;
    simulationTime += timeStep;
}

std::vector<std::pair<double, double>> FireSpreadModel::getBurnedPerimeter() const {
    // Simple perimeter extraction - cells that are burned and adjacent to unburned
    std::vector<std::pair<double, double>> perimeter;

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const Cell& cell = getCell(x, y);

            if (cell.burnStatus >= 1) { // Burning or burned
                // Check if on perimeter (has unburned neighbor)
                bool onPerimeter = false;
                for (int dy = -1; dy <= 1 && !onPerimeter; ++dy) {
                    for (int dx = -1; dx <= 1 && !onPerimeter; ++dx) {
                        if (dx == 0 && dy == 0) continue;

                        int nx = x + dx;
                        int ny = y + dy;

                        if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
                            if (getCell(nx, ny).burnStatus == 0) {
                                onPerimeter = true;
                            }
                        } else {
                            onPerimeter = true; // Edge cells
                        }
                    }
                }

                if (onPerimeter) {
                    perimeter.push_back({x, y});
                }
            }
        }
    }

    return perimeter;
}

int FireSpreadModel::getBurnedCellCount() const {
    int count = 0;
    for (const auto& cell : grid) {
        if (cell.burnStatus == 2) {
            count++;
        }
    }
    return count;
}

int FireSpreadModel::getBurningCellCount() const {
    int count = 0;
    for (const auto& cell : grid) {
        if (cell.burnStatus == 1) {
            count++;
        }
    }
    return count;
}
