#include "FireSpreadModel.h"
#include "GeoDataLoader.h"
#include <iostream>
#include <fstream>
#include <chrono>
#include <filesystem>
#ifndef NO_OPENMP
#include <omp.h>
#endif
#include <nlohmann/json.hpp>

using json = nlohmann::json;

/**
 * Benchmark helper
 */
class Timer {
private:
    std::chrono::high_resolution_clock::time_point start;
public:
    Timer() : start(std::chrono::high_resolution_clock::now()) {}

    double elapsed() const {
        auto end = std::chrono::high_resolution_clock::now();
        return std::chrono::duration<double>(end - start).count();
    }
};

/**
 * Export simulation state to JSON
 */
void exportStateToJSON(const FireSpreadModel& model, const GeoBounds& bounds,
                      const std::string& filename, int runId) {
    json output;

    output["run_id"] = runId;
    output["simulation_time"] = model.getSimulationTime();
    output["burned_cells"] = model.getBurnedCellCount();
    output["burning_cells"] = model.getBurningCellCount();
    output["width"] = model.getWidth();
    output["height"] = model.getHeight();
    output["cell_size"] = model.getCellSize();

    // Geographic bounds
    output["bounds"]["minX"] = bounds.minX;
    output["bounds"]["maxX"] = bounds.maxX;
    output["bounds"]["minY"] = bounds.minY;
    output["bounds"]["maxY"] = bounds.maxY;

    // Burned perimeter as GeoJSON
    auto perimeter = model.getBurnedPerimeter();
    json perimeterFeatures = json::array();

    for (const auto& point : perimeter) {
        double geoX, geoY;
        GeoDataLoader::gridToGeo(point.first, point.second, bounds, geoX, geoY);

        json feature;
        feature["type"] = "Feature";
        feature["geometry"]["type"] = "Point";
        feature["geometry"]["coordinates"] = {geoX, geoY};
        feature["properties"]["grid_x"] = point.first;
        feature["properties"]["grid_y"] = point.second;

        perimeterFeatures.push_back(feature);
    }

    output["perimeter"]["type"] = "FeatureCollection";
    output["perimeter"]["features"] = perimeterFeatures;

    // Export full grid state
    const auto& grid = model.getGrid();
    json gridData = json::array();

    for (int y = 0; y < model.getHeight(); ++y) {
        for (int x = 0; x < model.getWidth(); ++x) {
            int idx = y * model.getWidth() + x;
            const auto& cell = grid[idx];

            if (cell.burnStatus > 0) {
                double geoX, geoY;
                GeoDataLoader::gridToGeo(x, y, bounds, geoX, geoY);

                json cellData;
                cellData["x"] = x;
                cellData["y"] = y;
                cellData["geoX"] = geoX;
                cellData["geoY"] = geoY;
                cellData["status"] = cell.burnStatus;
                cellData["ignition_time"] = cell.ignitionTime;

                gridData.push_back(cellData);
            }
        }
    }

    output["grid_state"] = gridData;

    // Write to file
    std::ofstream file(filename);
    if (!file.is_open()) {
        std::cerr << "Error: could not open output file " << filename << std::endl;
        return;
    }
    file << output.dump(2);
    file.close();
    if (!file) {
        std::cerr << "Error: write to " << filename << " failed" << std::endl;
        return;
    }

    std::cout << "Exported state to " << filename << std::endl;
}

/**
 * Run simulation with benchmarking
 */
void runSimulation(const json& config) {
    std::cout << "=== Wildfire Spread Simulator ===" << std::endl;
#ifndef NO_OPENMP
    std::cout << "Using " << omp_get_max_threads() << " OpenMP threads" << std::endl;
#else
    std::cout << "Running in serial mode (OpenMP not available)" << std::endl;
#endif

    // Load configuration
    std::string fuelFile = config["fuel_data_file"];
    std::string elevationFile = config["elevation_data_file"];
    int ignitionX = config["ignition_point"]["x"];
    int ignitionY = config["ignition_point"]["y"];
    double windSpeed = config["wind"]["speed"];
    double windDirection = config["wind"]["direction"];
    double fuelMoisture = config["fuel_moisture"];
    int simulationSteps = config["simulation_steps"];
    double timeStep = config["time_step"];
    int runId = config.value("run_id", 1);
    std::string outputDir = config.value("output_dir", "output");

    // Previously a missing output directory made every snapshot write fail
    // silently while still printing "Exported state to ...".
    std::error_code ec;
    std::filesystem::create_directories(outputDir, ec);
    if (ec) {
        std::cerr << "Error: could not create output directory " << outputDir
                  << ": " << ec.message() << std::endl;
        return;
    }

    std::cout << "\n--- Loading Geospatial Data ---" << std::endl;
    Timer loadTimer;

    // Load fuel data
    std::vector<int> fuelData;
    GeoBounds fuelBounds;

    try {
        GeoDataLoader::loadIntRaster(fuelFile, fuelData, fuelBounds);
        std::cout << "Loaded fuel data: " << fuelBounds.width << "x" << fuelBounds.height
                  << " cells" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Error loading fuel data: " << e.what() << std::endl;
        return;
    }

    // Load elevation data
    std::vector<double> elevationData;
    GeoBounds elevationBounds;

    try {
        GeoDataLoader::loadFloatRaster(elevationFile, elevationData, elevationBounds);
        std::cout << "Loaded elevation data: " << elevationBounds.width << "x"
                  << elevationBounds.height << " cells" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "Error loading elevation data: " << e.what() << std::endl;
        return;
    }

    // Verify dimensions match
    if (fuelBounds.width != elevationBounds.width ||
        fuelBounds.height != elevationBounds.height) {
        std::cerr << "Error: Fuel and elevation data dimensions don't match!" << std::endl;
        return;
    }

    std::cout << "Data loading time: " << loadTimer.elapsed() << " seconds" << std::endl;

    // Initialize fire spread model
    std::cout << "\n--- Initializing Fire Spread Model ---" << std::endl;
    // Use cell size from config (meters), not from GeoTIFF (degrees)
    double cellSize = config.value("cell_size", 30.0);
    std::cout << "Cell size: " << cellSize << " meters" << std::endl;

    FireSpreadModel model(fuelBounds.width, fuelBounds.height, cellSize);
    model.loadFuelData(fuelData);
    model.loadElevationData(elevationData);
    model.setWindParameters(windSpeed, windDirection);
    model.setFuelMoisture(fuelMoisture);
    model.setTimeStep(timeStep);

    std::cout << "Wind: " << windSpeed << " mph at " << windDirection << " degrees" << std::endl;
    std::cout << "Fuel moisture: " << fuelMoisture << "%" << std::endl;

    // Set ignition point
    model.igniteCell(ignitionX, ignitionY);
    std::cout << "Ignition point: (" << ignitionX << ", " << ignitionY << ")" << std::endl;

    // Run simulation
    std::cout << "\n--- Running Simulation ---" << std::endl;
    std::cout << "Steps: " << simulationSteps << ", Time step: " << timeStep << " min" << std::endl;

    Timer simTimer;
    int exportInterval = simulationSteps / 10; // Export 10 snapshots
    if (exportInterval == 0) exportInterval = 1;

    for (int step = 0; step < simulationSteps; ++step) {
        model.step();

        // Progress update
        if ((step + 1) % 10 == 0 || step == simulationSteps - 1) {
            std::cout << "Step " << (step + 1) << "/" << simulationSteps
                      << " - Time: " << model.getSimulationTime() << " min"
                      << " - Burning: " << model.getBurningCellCount()
                      << " - Burned: " << model.getBurnedCellCount() << std::endl;
        }

        // Export snapshots
        if ((step + 1) % exportInterval == 0 || step == simulationSteps - 1) {
            std::string filename = outputDir + "/snapshot_" +
                                 std::to_string(runId) + "_step_" +
                                 std::to_string(step + 1) + ".json";
            exportStateToJSON(model, fuelBounds, filename, runId);
        }
    }

    double simTime = simTimer.elapsed();

    // Results
    std::cout << "\n=== Simulation Complete ===" << std::endl;
    std::cout << "Total simulation time: " << simTime << " seconds" << std::endl;
    std::cout << "Simulated time: " << model.getSimulationTime() << " minutes ("
              << model.getSimulationTime() / 60.0 << " hours)" << std::endl;
    std::cout << "Performance: " << (model.getSimulationTime() * 60.0) / simTime
              << "x real-time" << std::endl;
    std::cout << "Final burned cells: " << model.getBurnedCellCount() << std::endl;
    std::cout << "Burned area: " << (model.getBurnedCellCount() * cellSize * cellSize / 10000.0)
              << " hectares" << std::endl;

    // Export final state
    std::string finalFile = outputDir + "/final_state_" + std::to_string(runId) + ".json";
    exportStateToJSON(model, fuelBounds, finalFile, runId);

    // Export benchmark results
    json benchmark;
    benchmark["run_id"] = runId;
#ifndef NO_OPENMP
    benchmark["threads"] = omp_get_max_threads();
#else
    benchmark["threads"] = 1;
#endif
    benchmark["grid_size"] = fuelBounds.width * fuelBounds.height;
    benchmark["simulation_steps"] = simulationSteps;
    benchmark["wall_time_seconds"] = simTime;
    benchmark["simulated_time_minutes"] = model.getSimulationTime();
    benchmark["speedup_vs_realtime"] = (model.getSimulationTime() * 60.0) / simTime;
    benchmark["cells_burned"] = model.getBurnedCellCount();

    std::string benchFile = outputDir + "/benchmark_" + std::to_string(runId) + ".json";
    std::ofstream benchOut(benchFile);
    benchOut << benchmark.dump(2);
    benchOut.close();

    std::cout << "Benchmark results saved to " << benchFile << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <config.json>" << std::endl;
        return 1;
    }

    // Load configuration
    std::string configFile = argv[1];
    std::ifstream configStream(configFile);

    if (!configStream.is_open()) {
        std::cerr << "Error: Could not open config file: " << configFile << std::endl;
        return 1;
    }

    json config;
    try {
        configStream >> config;
    } catch (const std::exception& e) {
        std::cerr << "Error parsing config file: " << e.what() << std::endl;
        return 1;
    }

    // Run simulation
    try {
        runSimulation(config);
    } catch (const std::exception& e) {
        std::cerr << "Simulation error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
