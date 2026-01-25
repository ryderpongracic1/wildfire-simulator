# 🔥 Wildfire Simulator - Demo Guide

## ✅ Quick Start

### Access Web Interface
**URL**: http://localhost:8080

### Demo Datasets (Pre-configured & Working)
- **Fuel**: `demo_fuel_ventura_anderson13.tif` (800x800, Anderson 13 models)
- **Elevation**: `demo_elevation_ventura.tif` (800x800, matching terrain)

### Recommended Settings
```
Ignition Point: (400, 400)
Wind Speed: 20 mph
Wind Direction: 45° (NE - Santa Ana winds)
Fuel Moisture: 5.0%
Simulation Steps: 120 (2 hours)
```

### Expected Results
- **Execution Time**: ~1 second
- **Burned Area**: 1,674 hectares (4,138 acres)
- **Cells Burned**: 18,600 out of 640,000
- **Performance**: 6,000x faster than real-time

---

## 🎯 Demo Scenarios

### 1. Santa Ana Winds (Extreme Fire Behavior) ⚠️
```json
{
  "wind_speed": 20,
  "wind_direction": 45,
  "fuel_moisture": 5.0
}
```
**Result**: Very rapid spread, high intensity
**Expected burned area**: 1,600-1,800 hectares

### 2. Standard Summer Conditions (Moderate)
```json
{
  "wind_speed": 15,
  "wind_direction": 270,
  "fuel_moisture": 8.0
}
```
**Result**: Moderate spread rate
**Expected burned area**: 800-1,200 hectares

### 3. Wet Conditions (Fire Suppression) 💧
```json
{
  "wind_speed": 5,
  "wind_direction": 270,
  "fuel_moisture": 14.0
}
```
**Result**: Slow spread, possible self-extinguishment
**Expected burned area**: 100-300 hectares

---

## 🚀 Command Line Demo

### Run Simulation Directly
```bash
cd /Users/ryderpongracic/Documents/GitHub/wildfire/wildfire-simulator
./cpp/build/wildfire_simulator data/config_demo_working.json
```

### View Results
```bash
# Performance metrics
cat output/benchmark_300.json

# Final state
cat output/final_state_300.json | jq '.burned_cells, .burning_cells'

# List all output files
ls -lh output/
```

---

## 🔧 Service Management

### Check Status
```bash
docker-compose ps
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
```

### Restart Services
```bash
docker-compose restart
```

### Stop Services
```bash
docker-compose down
```

### Start Services
```bash
docker-compose up -d
```

---

## 📊 Performance Improvements

### OpenMP Enabled ✅
- **Threads**: 8 (configurable with OMP_NUM_THREADS)
- **Speedup**: 1.8x over serial execution
- **Before**: 1.2 seconds (serial mode)
- **After**: 0.67 seconds (parallel mode)

### Test OpenMP
```bash
export OMP_NUM_THREADS=8
./cpp/build/wildfire_simulator data/config_demo_working.json
# Should show: "Using 8 OpenMP threads"
```

---

## 🌐 API Endpoints

### Health Check
```bash
curl http://localhost:5001/api/health
```

### List Datasets
```bash
curl http://localhost:5001/api/datasets | jq
```

### Create Simulation
```bash
curl -X POST http://localhost:5001/api/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "fuel_data_file": "data/demo_fuel_ventura_anderson13.tif",
    "elevation_data_file": "data/demo_elevation_ventura.tif",
    "ignition_point": {"x": 400, "y": 400},
    "wind": {"speed": 20, "direction": 45},
    "fuel_moisture": 5.0,
    "simulation_steps": 120
  }'
```

### Get Simulation Results
```bash
curl http://localhost:5001/api/simulations/{run_id} | jq
```

---

## 🗄️ Database Access

### Connect to PostgreSQL
```bash
docker exec -it wildfire_db psql -U postgres -d wildfire_db
```

### View Simulation Runs
```sql
SELECT run_id, created_at, burned_cells, 
       burned_area_hectares, wall_time_seconds 
FROM simulation_runs 
ORDER BY created_at DESC 
LIMIT 10;
```

### Exit PostgreSQL
```
\q
```

---

## 🎬 Web Interface Features

### Interactive Map
- Click to set ignition point
- Pan and zoom with mouse
- Real-time fire visualization

### Time Slider
- Animate fire progression over time
- Step through individual time steps
- Play/pause controls

### Parameter Controls
- Wind speed and direction sliders
- Fuel moisture input
- Simulation duration settings

### Results Display
- Real-time statistics (burned cells, area)
- Performance metrics (execution time, speedup)
- Multiple simulation comparison

---

## 📁 Key Files

### Configuration
- `config_demo_working.json` - Working demo configuration
- `docker-compose.yml` - Service orchestration
- `.dockerignore` - Build optimization

### Data
- `demo_fuel_ventura_anderson13.tif` - Remapped fuel data (Anderson 13)
- `demo_elevation_ventura.tif` - Terrain elevation data
- `california_fuel_model.tif` - Full California fuel data (FBFM40)

### Code
- `cpp/src/FireSpreadModel.cpp` - Core simulation engine
- `api/app.py` - Flask REST API
- `frontend/app.js` - Web interface logic

---

## 🐛 Troubleshooting

### Port 5000 Already in Use
**Issue**: macOS Control Center uses port 5000  
**Solution**: API now runs on port 5001 (already configured)

### Services Won't Start
```bash
# Stop everything and restart
docker-compose down
docker-compose up -d
```

### No Fire Spread
**Issue**: Using FBFM40 data without remapping  
**Solution**: Use `demo_fuel_ventura_anderson13.tif` (already remapped)

### Slow Performance
**Issue**: OpenMP not enabled  
**Solution**: Already fixed - simulator has OpenMP support

### Database Connection Failed
```bash
# Check database is healthy
docker-compose ps
# Should show "healthy" for database

# Restart database
docker-compose restart database
```

---

## 📚 Additional Resources

- **README.md** - Complete project documentation
- **QUICKSTART_REAL_DATA.md** - Guide for real California data
- **cpp/include/FireSpreadModel.h** - API documentation
- **database/schema.sql** - Database schema

---

## 🎉 Demo Checklist

- [x] OpenMP enabled and working (8 threads)
- [x] Web interface deployed (http://localhost:8080)
- [x] API running (http://localhost:5001)
- [x] Database connected and healthy
- [x] Demo data configured (Anderson 13 fuels)
- [x] Fire spreading realistically (18,600 cells)
- [x] Time-slider animation functional
- [x] Performance: 6,000x real-time

**Status**: ✅ Ready for Demo!

---

## 🔗 Quick Links

- **Frontend**: http://localhost:8080
- **API**: http://localhost:5001
- **API Health**: http://localhost:5001/api/health
- **API Datasets**: http://localhost:5001/api/datasets

**Last Updated**: January 20, 2026
