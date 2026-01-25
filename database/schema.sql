-- Wildfire Simulator Database Schema
-- Requires PostgreSQL with PostGIS extension

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Simulation runs table
-- Stores metadata about each simulation run
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Simulation parameters
    ignition_point GEOMETRY(POINT, 4326),
    ignition_grid_x INTEGER,
    ignition_grid_y INTEGER,

    wind_speed DOUBLE PRECISION,
    wind_direction DOUBLE PRECISION,
    fuel_moisture DOUBLE PRECISION,

    -- Grid information
    grid_width INTEGER,
    grid_height INTEGER,
    cell_size DOUBLE PRECISION,

    -- Geographic bounds (WGS84)
    bounds_minx DOUBLE PRECISION,
    bounds_miny DOUBLE PRECISION,
    bounds_maxx DOUBLE PRECISION,
    bounds_maxy DOUBLE PRECISION,

    -- Simulation settings
    time_step DOUBLE PRECISION,
    total_steps INTEGER,

    -- Results
    final_burned_cells INTEGER,
    final_burned_area_hectares DOUBLE PRECISION,
    simulation_time_minutes DOUBLE PRECISION,
    wall_time_seconds DOUBLE PRECISION,
    threads_used INTEGER,

    -- Data files used
    fuel_data_file TEXT,
    elevation_data_file TEXT,

    -- Status
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    error_message TEXT
);

-- Create spatial index on ignition point
CREATE INDEX IF NOT EXISTS idx_simulation_runs_ignition
    ON simulation_runs USING GIST(ignition_point);

-- Create index on created_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_simulation_runs_created
    ON simulation_runs(created_at DESC);


-- Simulation snapshots table
-- Stores fire spread progression at different time steps
CREATE TABLE IF NOT EXISTS simulation_snapshots (
    snapshot_id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES simulation_runs(run_id) ON DELETE CASCADE,

    -- Time information
    simulation_time DOUBLE PRECISION,
    step_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Burned perimeter as polygon
    burned_perimeter GEOMETRY(POLYGON, 4326),

    -- Statistics at this snapshot
    burned_cells INTEGER,
    burning_cells INTEGER,
    burned_area_hectares DOUBLE PRECISION,

    UNIQUE(run_id, step_number)
);

-- Create spatial index on burned perimeter
CREATE INDEX IF NOT EXISTS idx_snapshots_perimeter
    ON simulation_snapshots USING GIST(burned_perimeter);

-- Create index for efficient time-series queries
CREATE INDEX IF NOT EXISTS idx_snapshots_run_time
    ON simulation_snapshots(run_id, simulation_time);


-- Individual burned cells table
-- Stores detailed information about each burned cell
CREATE TABLE IF NOT EXISTS burned_cells (
    cell_id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES simulation_runs(run_id) ON DELETE CASCADE,

    -- Grid coordinates
    grid_x INTEGER,
    grid_y INTEGER,

    -- Geographic location
    location GEOMETRY(POINT, 4326),

    -- Burn information
    ignition_time DOUBLE PRECISION,
    fuel_type INTEGER,
    elevation DOUBLE PRECISION,
    slope_angle DOUBLE PRECISION,
    slope_aspect DOUBLE PRECISION,

    UNIQUE(run_id, grid_x, grid_y)
);

-- Create spatial index on cell locations
CREATE INDEX IF NOT EXISTS idx_burned_cells_location
    ON burned_cells USING GIST(location);

-- Create index for grid-based queries
CREATE INDEX IF NOT EXISTS idx_burned_cells_grid
    ON burned_cells(run_id, grid_x, grid_y);

-- Create index for time-based queries
CREATE INDEX IF NOT EXISTS idx_burned_cells_time
    ON burned_cells(run_id, ignition_time);


-- View for recent simulations with summary stats
CREATE OR REPLACE VIEW recent_simulations AS
SELECT
    sr.run_id,
    sr.created_at,
    sr.status,
    sr.wind_speed,
    sr.wind_direction,
    sr.fuel_moisture,
    sr.final_burned_cells,
    sr.final_burned_area_hectares,
    sr.simulation_time_minutes,
    sr.wall_time_seconds,
    sr.threads_used,
    CASE
        WHEN sr.wall_time_seconds > 0
        THEN (sr.simulation_time_minutes * 60.0 / sr.wall_time_seconds)
        ELSE 0
    END AS speedup_vs_realtime,
    ST_AsGeoJSON(sr.ignition_point) as ignition_geojson,
    COUNT(ss.snapshot_id) as snapshot_count
FROM simulation_runs sr
LEFT JOIN simulation_snapshots ss ON sr.run_id = ss.run_id
GROUP BY sr.run_id
ORDER BY sr.created_at DESC
LIMIT 50;


-- Function to get simulation progress
CREATE OR REPLACE FUNCTION get_simulation_progress(p_run_id INTEGER)
RETURNS TABLE (
    step_number INTEGER,
    simulation_time DOUBLE PRECISION,
    burned_cells INTEGER,
    burning_cells INTEGER,
    perimeter_geojson TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ss.step_number,
        ss.simulation_time,
        ss.burned_cells,
        ss.burning_cells,
        ST_AsGeoJSON(ss.burned_perimeter)::TEXT
    FROM simulation_snapshots ss
    WHERE ss.run_id = p_run_id
    ORDER BY ss.step_number;
END;
$$ LANGUAGE plpgsql;


-- Function to get burned cells within a geographic area
CREATE OR REPLACE FUNCTION get_burned_cells_in_area(
    p_run_id INTEGER,
    p_minx DOUBLE PRECISION,
    p_miny DOUBLE PRECISION,
    p_maxx DOUBLE PRECISION,
    p_maxy DOUBLE PRECISION
)
RETURNS TABLE (
    grid_x INTEGER,
    grid_y INTEGER,
    ignition_time DOUBLE PRECISION,
    fuel_type INTEGER,
    elevation DOUBLE PRECISION,
    location_geojson TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        bc.grid_x,
        bc.grid_y,
        bc.ignition_time,
        bc.fuel_type,
        bc.elevation,
        ST_AsGeoJSON(bc.location)::TEXT
    FROM burned_cells bc
    WHERE bc.run_id = p_run_id
    AND ST_Intersects(
        bc.location,
        ST_MakeEnvelope(p_minx, p_miny, p_maxx, p_maxy, 4326)
    );
END;
$$ LANGUAGE plpgsql;


-- Function to calculate fire spread statistics
CREATE OR REPLACE FUNCTION calculate_spread_statistics(p_run_id INTEGER)
RETURNS TABLE (
    avg_spread_rate DOUBLE PRECISION,
    max_spread_rate DOUBLE PRECISION,
    total_area_hectares DOUBLE PRECISION,
    duration_hours DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    WITH spread_data AS (
        SELECT
            step_number,
            simulation_time,
            burned_cells,
            LAG(burned_cells) OVER (ORDER BY step_number) as prev_burned_cells,
            LAG(simulation_time) OVER (ORDER BY step_number) as prev_time
        FROM simulation_snapshots
        WHERE run_id = p_run_id
    ),
    spread_rates AS (
        SELECT
            CASE
                WHEN prev_time IS NOT NULL AND simulation_time > prev_time
                THEN (burned_cells - prev_burned_cells) / (simulation_time - prev_time)
                ELSE 0
            END as rate
        FROM spread_data
    )
    SELECT
        AVG(rate) as avg_spread_rate,
        MAX(rate) as max_spread_rate,
        sr.final_burned_area_hectares,
        sr.simulation_time_minutes / 60.0
    FROM spread_rates, simulation_runs sr
    WHERE sr.run_id = p_run_id
    GROUP BY sr.final_burned_area_hectares, sr.simulation_time_minutes;
END;
$$ LANGUAGE plpgsql;


-- Comments for documentation
COMMENT ON TABLE simulation_runs IS 'Stores metadata and parameters for each wildfire simulation run';
COMMENT ON TABLE simulation_snapshots IS 'Stores fire spread progression snapshots at different time steps';
COMMENT ON TABLE burned_cells IS 'Detailed information about individual burned cells';

COMMENT ON COLUMN simulation_runs.ignition_point IS 'Geographic location where fire started (WGS84)';
COMMENT ON COLUMN simulation_runs.wind_direction IS 'Wind direction in degrees from North (0-360)';
COMMENT ON COLUMN simulation_runs.cell_size IS 'Size of each grid cell in meters';
COMMENT ON COLUMN simulation_snapshots.burned_perimeter IS 'Polygon representing the fire perimeter at this snapshot';
