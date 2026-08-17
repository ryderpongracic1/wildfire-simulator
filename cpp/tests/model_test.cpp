// Regression tests for FireSpreadModel physics behavior.
// No GDAL or database dependency: builds against the model core only.
//
// These tests pin the property that broke in the original implementation:
// the fire shape must RESPOND to wind, slope, fuel type, and moisture.
// (The original prob>0.3 threshold produced an identical square for every
// configuration.)
#include "FireSpreadModel.h"
#include <iostream>
#include <vector>
#include <cmath>
#include <cstdlib>

static int failures = 0;

#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::cerr << "FAIL: " << msg << "  [" << #cond << "]\n";        \
            ++failures;                                                      \
        } else {                                                             \
            std::cout << "ok:   " << msg << "\n";                           \
        }                                                                    \
    } while (0)

struct Shape {
    int cells = 0;
    int east = 0, west = 0, north = 0, south = 0; // reach from ignition point
};

static Shape run(int fuelType, double windSpeed, double windDir, double moisture,
                 bool slopeUpEast, int steps, int W = 201, int H = 201) {
    FireSpreadModel m(W, H, 30.0);
    std::vector<int> fuel(W * H, fuelType);
    std::vector<double> elev(W * H, 100.0);
    if (slopeUpEast) {
        for (int y = 0; y < H; ++y)
            for (int x = 0; x < W; ++x)
                elev[y * W + x] = 100.0 + x * 30.0 * 0.30; // 30% grade rising east
    }
    m.loadFuelData(fuel);
    m.loadElevationData(elev);
    m.setWindParameters(windSpeed, windDir);
    m.setFuelMoisture(moisture);
    m.setTimeStep(1.0);
    const int cx = W / 2, cy = H / 2;
    m.igniteCell(cx, cy);
    for (int i = 0; i < steps; ++i) m.step();

    Shape s;
    const auto& g = m.getGrid();
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x)
            if (g[y * W + x].burnStatus >= 1) {
                s.cells++;
                s.east  = std::max(s.east,  x - cx);
                s.west  = std::max(s.west,  cx - x);
                s.north = std::max(s.north, cy - y);
                s.south = std::max(s.south, y - cy);
            }
    return s;
}

int main() {
    // --- Fire spreads at all ---
    Shape base = run(/*grass*/1, 0, 0, 8.0, false, 60);
    CHECK(base.cells > 100, "fire spreads from ignition point");

    // --- Symmetry without forcing ---
    CHECK(base.east == base.west && base.north == base.south,
          "no wind + flat terrain gives a symmetric fire");

    // --- Wind elongates the fire downwind ---
    // In this codebase windDirection is the bearing the wind blows TOWARD;
    // 270 pushes the fire west.
    Shape windy = run(1, 15, 270, 8.0, false, 60);
    CHECK(windy.west > windy.east, "wind elongates the fire downwind");
    CHECK(windy.west > base.west,  "downwind reach exceeds the no-wind case");
    CHECK(windy.east <= base.east, "upwind reach does not exceed the no-wind case");

    // --- Slope: uphill faster than downhill ---
    Shape sloped = run(/*timber*/8, 0, 0, 8.0, true, 60);
    CHECK(sloped.east > sloped.west, "fire runs uphill faster than downhill");
    Shape flat8 = run(8, 0, 0, 8.0, false, 60);
    CHECK(sloped.east > flat8.east, "uphill reach exceeds flat-terrain reach");
    CHECK(sloped.west <= flat8.west, "downhill reach does not exceed flat-terrain reach");

    // --- Moisture damps spread ---
    Shape wet = run(8, 0, 0, 25.0, false, 60);
    CHECK(wet.cells < flat8.cells, "higher fuel moisture slows spread");

    // --- Moisture of extinction stops fire entirely ---
    Shape soaked = run(1, 0, 0, 50.0, false, 60); // grass extinction is 12%
    CHECK(soaked.cells <= 1, "moisture above extinction prevents all spread");

    // --- Fuel types differ ---
    Shape grass = run(1, 0, 0, 8.0, false, 60);
    Shape timber = run(8, 0, 0, 8.0, false, 60);
    CHECK(grass.cells != timber.cells, "different fuel types spread differently");

    // --- Non-burnable fuel blocks fire ---
    {
        const int W = 101, H = 101;
        FireSpreadModel m(W, H, 30.0);
        std::vector<int> fuel(W * H, 1);
        for (int y = 0; y < H; ++y) fuel[y * W + 70] = 0; // vertical firebreak at x=70
        std::vector<double> elev(W * H, 100.0);
        m.loadFuelData(fuel);
        m.loadElevationData(elev);
        m.setWindParameters(0, 0);
        m.setFuelMoisture(8.0);
        m.setTimeStep(1.0);
        m.igniteCell(50, 50);
        for (int i = 0; i < 80; ++i) m.step();
        bool crossed = false;
        const auto& g = m.getGrid();
        for (int y = 0; y < H; ++y)
            for (int x = 71; x < W; ++x)
                if (g[y * W + x].burnStatus >= 1) crossed = true;
        CHECK(!crossed, "a non-burnable firebreak stops the fire");
    }

    // --- Determinism: identical configs give identical results ---
    {
        Shape a = run(4, 15, 270, 8.0, true, 40, 101, 101);
        Shape b = run(4, 15, 270, 8.0, true, 40, 101, 101);
        CHECK(a.cells == b.cells && a.east == b.east && a.west == b.west,
              "identical configurations produce identical fires");
    }

    // --- Ignition times are monotonic with distance along the spread ---
    {
        const int W = 101, H = 3;
        FireSpreadModel m(W, H, 30.0);
        std::vector<int> fuel(W * H, 1);
        std::vector<double> elev(W * H, 100.0);
        m.loadFuelData(fuel);
        m.loadElevationData(elev);
        m.setWindParameters(0, 0);
        m.setFuelMoisture(8.0);
        m.setTimeStep(1.0);
        m.igniteCell(0, 1);
        for (int i = 0; i < 120; ++i) m.step();
        const auto& g = m.getGrid();
        bool monotonic = true;
        double prev = -1.0;
        for (int x = 0; x < W; ++x) {
            const auto& c = g[1 * W + x];
            if (c.burnStatus >= 1) {
                if (c.ignitionTime < prev) monotonic = false;
                prev = c.ignitionTime;
            }
        }
        CHECK(monotonic, "ignition times increase monotonically along a 1-D spread");
    }

    // --- Time-step invariance: dt=0.5 x 120 steps ~ dt=1.0 x 60 steps ---
    {
        auto runDt = [](double dt, int steps) {
            const int W = 151, H = 151;
            FireSpreadModel m(W, H, 30.0);
            std::vector<int> fuel(W * H, 1);
            std::vector<double> elev(W * H, 100.0);
            m.loadFuelData(fuel);
            m.loadElevationData(elev);
            m.setWindParameters(10, 270);
            m.setFuelMoisture(8.0);
            m.setTimeStep(dt);
            m.igniteCell(75, 75);
            for (int i = 0; i < steps; ++i) m.step();
            int cells = 0;
            for (const auto& c : m.getGrid()) if (c.burnStatus >= 1) cells++;
            return cells;
        };
        int coarse = runDt(1.0, 60);
        int fine   = runDt(0.5, 120);
        double ratio = double(fine) / double(coarse);
        CHECK(ratio > 0.9 && ratio < 1.1,
              "halving the time step barely changes total spread (time-step invariance)");
    }

    std::cout << (failures == 0 ? "\nALL TESTS PASSED\n" : "\nTESTS FAILED\n");
    return failures == 0 ? 0 : 1;
}
