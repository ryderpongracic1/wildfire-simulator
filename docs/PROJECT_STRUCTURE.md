# Project Structure

```
wildfire-simulator/
│
├── cpp/                          # C++ Simulation Engine
│   ├── include/                  # Header files
│   │   ├── FireSpreadModel.h    # Core fire spread simulation
│   │   └── GeoDataLoader.h      # GDAL GeoTIFF data loader
│   ├── src/                      # Source files
│   │   ├── FireSpreadModel.cpp  # Fire spread implementation
│   │   ├── GeoDataLoader.cpp    # Data loading implementation
│   │   └── main.cpp             # Entry point and CLI
│   ├── build/                    # Build artifacts (generated)
│   └── CMakeLists.txt           # CMake build configuration
│
├── api/                          # Python Flask REST API
│   ├── app.py                   # Flask application and endpoints
│   └── requirements.txt         # Python dependencies
│
├── frontend/                     # Web Visualization Interface
│   ├── index.html               # Main HTML page
│   └── app.js                   # JavaScript application logic
│
├── database/                     # PostgreSQL/PostGIS Database
│   └── schema.sql               # Database schema and functions
│
├── docker/                       # Docker Configuration
│   ├── Dockerfile.simulator     # C++ simulator container
│   ├── Dockerfile.api           # Flask API container
│   └── nginx.conf               # Nginx configuration for frontend
│
├── data/                         # Geospatial Data
│   └── sample/                  # Sample/test data
│       ├── generate_test_data.py      # Test data generator
│       ├── config_test.json           # Test configuration
│       ├── config_high_wind.json      # High wind scenario
│       └── config_benchmark.json      # Benchmark configuration
│
├── output/                       # Simulation Output (generated)
│   ├── snapshot_*.json          # Simulation snapshots
│   ├── final_state_*.json       # Final simulation states
│   └── benchmark_*.json         # Performance benchmarks
│
├── scripts/                      # Utility Scripts
│   ├── quick_start.sh           # Quick start guide
│   └── run_benchmark.sh         # Performance benchmarking
│
├── docs/                         # Documentation
│   └── PROJECT_STRUCTURE.md     # This file
│
├── docker-compose.yml           # Docker Compose configuration
├── README.md                    # Main documentation
├── LICENSE                      # MIT License
└── .gitignore                   # Git ignore rules
```

## Component Descriptions

### C++ Simulation Engine (`cpp/`)

The core of the wildfire simulator, implementing:

- **FireSpreadModel**: Rothermel fire spread equations with cellular automaton
  - Fuel model properties (Anderson 13 fuel models)
  - Wind and slope effects on spread rate
  - OpenMP parallelization for grid processing
  - Ignition probability calculations

- **GeoDataLoader**: GDAL-based geospatial data I/O
  - GeoTIFF raster reading
  - Geographic coordinate transformations
  - Subset extraction

- **main.cpp**: Command-line interface
  - JSON configuration parsing
  - Simulation execution
  - Results export (JSON/GeoJSON)
  - Performance benchmarking

**Key Technologies**:
- C++17
- OpenMP for parallelization
- GDAL 3.0+ for geospatial I/O
- nlohmann/json for JSON parsing

### Flask API (`api/`)

RESTful API for simulation control and data access:

**Endpoints**:
- `POST /api/simulations` - Create and run simulation
- `GET /api/simulations` - List all simulations
- `GET /api/simulations/{id}` - Get simulation details
- `GET /api/simulations/{id}/progress` - Get snapshots
- `GET /api/simulations/{id}/cells` - Get burned cells
- `GET /api/simulations/{id}/statistics` - Get statistics
- `GET /api/datasets` - List available data files

**Features**:
- Asynchronous simulation execution
- PostgreSQL/PostGIS integration
- GeoJSON output for web visualization
- CORS support for web frontend

### Web Frontend (`frontend/`)

Interactive visualization interface:

**Features**:
- Leaflet.js map with terrain layers
- Time-slider for animation playback
- Real-time simulation monitoring
- Parameter configuration forms
- Simulation history and selection
- Performance metrics display

**Technologies**:
- Vanilla JavaScript (no framework dependencies)
- Leaflet.js 1.9+ for mapping
- Responsive CSS design

### Database (`database/`)

PostgreSQL with PostGIS extension:

**Tables**:
- `simulation_runs` - Simulation metadata and parameters
- `simulation_snapshots` - Time-series fire perimeter data
- `burned_cells` - Individual cell burn information

**Functions**:
- `get_simulation_progress()` - Retrieve snapshots
- `get_burned_cells_in_area()` - Spatial queries
- `calculate_spread_statistics()` - Analytics

**Features**:
- Spatial indexing (GIST)
- GeoJSON output
- Time-series queries
- Fire spread statistics

### Docker Configuration (`docker/`)

Complete containerized deployment:

**Services**:
1. **database** - PostgreSQL 15 + PostGIS 3.3
2. **simulator** - C++ engine build environment
3. **api** - Flask API server
4. **frontend** - Nginx web server

**Networks**:
- All services on shared network
- External ports: 5432 (DB), 5000 (API), 8080 (Web)

### Data Files (`data/`)

Geospatial input data:

**Required Format**:
- GeoTIFF (.tif) raster files
- Projection: WGS84 (EPSG:4326) or UTM
- Resolution: 30m (LANDFIRE standard)

**Types**:
- Fuel model rasters (integer 0-13)
- Elevation/DEM rasters (float, meters)

**Sample Data**:
- Test data generator for quick testing
- Example configurations for different scenarios

### Output Files (`output/`)

Simulation results:

**File Types**:
- `snapshot_{run_id}_step_{n}.json` - Intermediate states
- `final_state_{run_id}.json` - Final simulation state
- `benchmark_{run_id}.json` - Performance metrics

**Format**:
- JSON with embedded GeoJSON
- Grid state arrays
- Perimeter coordinates
- Timestamped progression

## Data Flow

```
┌─────────────┐
│  GeoTIFF    │
│  Data Files │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  C++ Simulator      │
│  (GDAL → Grid)      │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Fire Spread Model  │
│  (OpenMP Parallel)  │
└──────┬──────────────┘
       │
       ├──────────────┐
       │              │
       ▼              ▼
┌──────────┐   ┌────────────┐
│   JSON   │   │ PostgreSQL │
│  Output  │   │  /PostGIS  │
└────┬─────┘   └──────┬─────┘
     │                │
     └────────┬───────┘
              │
              ▼
       ┌──────────────┐
       │  Flask API   │
       │  (GeoJSON)   │
       └──────┬───────┘
              │
              ▼
       ┌──────────────┐
       │ Web Frontend │
       │  (Leaflet)   │
       └──────────────┘
```

## Build Process

1. **CMake Configuration**: Detects dependencies (OpenMP, GDAL)
2. **C++ Compilation**: Optimized release build with `-O3 -march=native`
3. **Docker Build**: Multi-stage builds for each service
4. **Database Init**: Schema loaded on first container start

## Performance Characteristics

- **Grid Size**: Scales to millions of cells
- **Parallelization**: Near-linear speedup to 8-12 threads
- **Memory**: ~4 bytes per cell (fuel + state)
- **I/O**: Bottleneck is GeoTIFF reading (GDAL)
- **Database**: Spatial indexing enables fast queries

## Extension Points

1. **New Fuel Models**: Add to `initializeFuelProperties()`
2. **Fire Behavior**: Modify Rothermel calculations
3. **Visualization**: Extend Leaflet layers
4. **API Endpoints**: Add routes in Flask
5. **Database Analytics**: New SQL functions
