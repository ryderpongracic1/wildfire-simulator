# 🔥 Wildfire Spread Simulator

A high-performance wildfire spread simulation system that models fire behavior using real geospatial data, physics-based equations, and parallel computing. Simulate hours of wildfire spread in seconds.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![C++](https://img.shields.io/badge/C%2B%2B-17-blue.svg)
![Python](https://img.shields.io/badge/Python-3.9%2B-green.svg)

## 🌟 Features

- **⚡ High-Performance Computing**: C++ simulation engine with a copy-free, OpenMP-parallel propagation step
- **🌍 Real Geospatial Data**: Processes LANDFIRE fuel models and USGS elevation data (GeoTIFF format)
- **🔬 Physics-Based Modeling**: Implements Rothermel fire spread equations with cellular automaton approach
- **🎮 Interactive Visualization**: Web-based interface with real-time fire spread animation
- **📊 Spatial Database**: PostgreSQL/PostGIS for efficient spatial queries and time-series analysis
- **🐳 Docker Ready**: Complete containerized environment for easy deployment
- **🌐 REST API**: Flask-based API for simulation control and data retrieval

## 📸 Demo

The simulator provides:
- Real-time fire perimeter visualization
- Time-slider to review fire progression
- Statistical analysis (burned area, spread rate, etc.)
- Interactive map with terrain layers

## 🏗️ Architecture

```
┌─────────────────────┐
│   Web Frontend      │  ← Leaflet.js + Time-slider
│   (JavaScript)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Flask REST API    │  ← Python 3.9+
│   (Python)          │
└──────────┬──────────┘
           │
           ├─────────────────────┐
           ▼                     ▼
┌─────────────────────┐   ┌──────────────────┐
│  C++ Simulator      │   │  PostgreSQL      │
│  • OpenMP Parallel  │   │  • PostGIS       │
│  • GDAL I/O         │   │  • Spatial Data  │
│  • Rothermel Model  │   └──────────────────┘
└─────────────────────┘
```

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/wildfire-simulator.git
cd wildfire-simulator

# Download sample data (required for demo)
# See "Data Acquisition" section below

# Start all services
docker-compose up --build

# Access the web interface
open http://localhost:8080
```

### Manual Installation

#### Prerequisites

- **C++17** compiler (GCC 9+ or Clang 10+)
- **CMake** 3.15+
- **GDAL** 3.0+ with development headers
- **OpenMP** (usually comes with compiler)
- **PostgreSQL** 14+ with PostGIS 3.1+
- **Python** 3.9+

#### Build Steps

```bash
# 1. Install system dependencies
# Ubuntu/Debian:
sudo apt-get install -y build-essential cmake libgdal-dev libomp-dev \
    postgresql-14 postgresql-14-postgis-3 python3-pip

# macOS:
brew install cmake gdal libomp postgresql postgis python@3.11

# 2. Build C++ simulator
cd cpp
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
cd ../..

# 3. Setup database
createdb wildfire_db
psql wildfire_db -c "CREATE EXTENSION postgis;"
psql wildfire_db < database/schema.sql

# 4. Install Python dependencies
pip install -r api/requirements.txt

# 5. Run the services
# Terminal 1 - API
cd api
python app.py

# Terminal 2 - Frontend
cd frontend
python -m http.server 8080
```

## 📊 Data Acquisition

The simulator requires two types of geospatial data:

### 1. Fuel Model Data (LANDFIRE)

Download from [LANDFIRE](https://landfire.gov/viewer/):
- Product: **Fire Behavior Fuel Models 13 (FBFM13)** or **Anderson 13**
- Format: GeoTIFF
- Resolution: 30m (recommended)

### 2. Elevation Data (USGS)

Download from [USGS National Map](https://apps.nationalmap.gov/downloader/):
- Dataset: **1/3 arc-second DEM** (10m) or **1 arc-second DEM** (30m)
- Format: GeoTIFF

### Sample Data for Testing

Generate synthetic test data:

```bash
cd data/sample
python generate_test_data.py
```

This creates small test datasets you can use to try the simulator without downloading real data.

## 🎮 Usage

### Web Interface

1. Navigate to `http://localhost:8080`
2. Select fuel and elevation datasets
3. Configure simulation parameters:
   - **Ignition Point**: Grid coordinates (x, y)
   - **Wind Speed**: 0-100 mph
   - **Wind Direction**: 0-360° (0=North, 90=East, 180=South, 270=West)
   - **Fuel Moisture**: 0-100% (lower = faster spread)
   - **Simulation Steps**: Number of time steps to simulate
4. Click "Run Simulation"
5. Use the time slider to watch fire spread

### Command-Line Interface

Create a configuration file `config.json`:

```json
{
    "run_id": 1,
    "fuel_data_file": "data/sample/test_fuel_model.tif",
    "elevation_data_file": "data/sample/test_elevation.tif",
    "ignition_point": {"x": 150, "y": 150},
    "wind": {"speed": 15, "direction": 270},
    "fuel_moisture": 8.0,
    "simulation_steps": 120,
    "time_step": 1.0,
    "output_dir": "output",
    "cell_size": 30.0
}
```

Run the simulator:

```bash
./cpp/build/wildfire_simulator config.json
```

### Python API Client

```python
import requests

API_BASE = "http://localhost:5000/api"

# Start a simulation
config = {
    "fuel_data_file": "data/sample/test_fuel_model.tif",
    "elevation_data_file": "data/sample/test_elevation.tif",
    "ignition_point": {"x": 100, "y": 100},
    "wind": {"speed": 15, "direction": 270},
    "fuel_moisture": 8.0,
    "simulation_steps": 60
}

response = requests.post(f"{API_BASE}/simulations", json=config)
run_id = response.json()["run_id"]

# Check status
status = requests.get(f"{API_BASE}/simulations/{run_id}").json()
print(f"Status: {status['status']}")
```

## 🔧 Technologies Used

### Core Simulation Engine
- **C++17**: High-performance computation
- **OpenMP**: Parallel processing across CPU cores
- **GDAL/OGR**: Geospatial data I/O (reading GeoTIFF files)
- **nlohmann/json**: JSON configuration parsing
- **CMake**: Build system

### Backend API
- **Python 3.9+**: Application runtime
- **Flask**: REST API framework
- **Flask-CORS**: Cross-origin request handling
- **psycopg2**: PostgreSQL database adapter
- **Gunicorn**: Production WSGI server

### Database
- **PostgreSQL 14+**: Relational database
- **PostGIS 3.1+**: Spatial database extension

### Frontend
- **HTML5/CSS3**: User interface
- **JavaScript (ES6+)**: Application logic
- **Leaflet.js**: Interactive map visualization
- **Proj4js**: Coordinate system transformations

### DevOps
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration
- **Nginx**: Web server (in Docker setup)

## ⚡ Performance

Measured on a 4-core Linux x86-64 box (GCC 11, `-O3 -march=native`), grid 500×500
cells, 120 time steps (2 hours simulated), grass fuel, 15 mph wind:

| Configuration | Wall Time | Notes |
|---------------|-----------|-------|
| 1 thread      | 0.33s     | ~21,800× faster than real time |
| 2–4 threads   | 0.20s     | scaling is modest — the step is memory-bound |

The propagation step does no full-grid copies: a parallel read-only sweep
collects ignitions into per-thread lists, then front-limited waves expand only
around newly ignited cells. Reproduce with:

```bash
g++ -O3 -march=native -fopenmp -Icpp/include \
    cpp/tests/model_test.cpp cpp/src/FireSpreadModel.cpp -o model_test && ./model_test
```

## 📡 API Endpoints

### Core Endpoints

- `GET /api/health` - Health check
- `GET /api/datasets` - List available fuel/elevation datasets
- `POST /api/simulations` - Create and start new simulation
- `GET /api/simulations` - List all simulations
- `GET /api/simulations/{id}` - Get simulation details
- `GET /api/simulations/{id}/progress` - Get time-series snapshots
- `GET /api/simulations/{id}/cells` - Get burned cell data
- `GET /api/simulations/{id}/statistics` - Get simulation statistics
- `POST /api/upload` - Upload custom GeoTIFF data

See [API Documentation](docs/API.md) for detailed request/response schemas.

## 🔬 Fire Physics Model

The simulator implements the **Rothermel fire spread model** on a cellular
automaton using **deterministic time-of-arrival propagation**: a cell ignites
when the fire front from any ignited neighbor reaches it, where the arrival
time is the neighbor's ignition time plus distance divided by the directional
Rothermel rate of spread. Sub-cell-per-step rates take multiple steps to cross
a cell; faster rates cross several cells in one step. Identical inputs always
produce identical fires.

Factors shaping the spread rate:

1. **Fuel Type**: 13 standard fuel models (Anderson classification)
   - Grass (1-3): Fast spread, low intensity
   - Brush/Chaparral (4-7): High intensity
   - Timber (8-10): Moderate spread
   - Slash (11-13): Extreme intensity

2. **Wind**: Accelerates fire in downwind direction
   - Uses vector components (speed × sin/cos of direction)
   - Exponential effect on spread rate

3. **Slope**: Uphill fire spread is significantly faster
   - Calculated from elevation DEM
   - Preheats upslope fuels

4. **Fuel Moisture**: Inhibits ignition and spread
   - Higher moisture = slower spread
   - Critical thresholds vary by fuel type

## 🗂️ Project Structure

```
wildfire-simulator/
├── cpp/                    # C++ simulation engine
│   ├── include/           # Header files
│   │   ├── FireSpreadModel.h
│   │   └── GeoDataLoader.h
│   ├── src/               # Source files
│   │   ├── main.cpp
│   │   ├── FireSpreadModel.cpp
│   │   └── GeoDataLoader.cpp
│   └── CMakeLists.txt
├── api/                    # Flask REST API
│   ├── app.py
│   └── requirements.txt
├── frontend/              # Web interface
│   ├── index.html
│   └── app.js
├── database/              # Database schema
│   └── schema.sql
├── data/                  # Geospatial data (not in repo)
│   └── sample/           # Sample test data
├── docker/                # Docker configuration
├── output/                # Simulation results
├── scripts/               # Utility scripts
└── docs/                  # Documentation
```

## 🧪 Tests

The model core has a physics regression suite (`cpp/tests/model_test.cpp`, no
GDAL or database dependency). It pins the properties that matter: wind
elongates the fire downwind, uphill spread beats downhill, moisture damps and
extinction moisture stops spread, fuel types differ, non-burnable cells block
fire, results are deterministic, and halving the time step barely changes
total spread.

```bash
cd cpp && mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release .. && make model_test && ctest
```

## 🐛 Troubleshooting

### Common Issues

**GDAL not found during build:**
```bash
# Ubuntu
sudo apt-get install libgdal-dev gdal-bin
# macOS
brew install gdal
```

**Database connection errors:**
```bash
# Check PostgreSQL is running
pg_isready
# Test connection
psql wildfire_db -c "SELECT PostGIS_Version();"
```

**OpenMP not found:**
```bash
# Ubuntu
sudo apt-get install libomp-dev
# macOS
brew install libomp
```
On macOS the CMake configure step probes `brew --prefix libomp` (and the
conventional `/opt/homebrew/opt/libomp`, `/usr/local/opt/libomp`) and retries
detection, since AppleClang finds neither on its own. Look for
`Retrying OpenMP with Homebrew libomp at ...` followed by
`✓ OpenMP enabled`. If you still get `⚠ OpenMP not found`, `brew install libomp`
and re-run `cmake`.

**Postgres container runs emulated on Apple Silicon:**
Compose uses `imresamu/postgis:15-3.5`, which publishes both `linux/amd64` and
`linux/arm64` — the official `postgis/postgis` images are amd64-only at every
tag, so they run under qemu on an M-series Mac. To go back to the official
image, uncomment the `postgis/postgis:15-3.3` line in `docker-compose.yml`; it
works, just slower. Switching images means a Postgres data directory built by
one and read by the other, so `docker compose down -v` if the database refuses
to start.

## 📚 Scientific References

1. Rothermel, R.C. (1972). "A Mathematical Model for Predicting Fire Spread in Wildland Fuels". USDA Forest Service Research Paper INT-115.
2. Albini, F.A. (1976). "Computer-Based Models of Wildland Fire Behavior". USDA Forest Service.
3. Anderson, H.E. (1982). "Aids to Determining Fuel Models for Estimating Fire Behavior". USDA Forest Service General Technical Report INT-122.

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 🙏 Acknowledgments

- **LANDFIRE Program** for providing fuel model datasets
- **USGS** for elevation data
- **OpenMP** community for parallel computing support
- **GDAL/OGR** contributors for geospatial data handling

## 📬 Contact

For questions or feedback, please open an issue on GitHub.

---

**Built with** ❤️ **for wildfire research and education**
