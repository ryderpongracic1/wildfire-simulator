"""
Wildfire Simulator Flask API
Provides REST endpoints for running simulations and retrieving results
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor
import subprocess
import json
import os
import tempfile
from datetime import datetime
import threading

app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432'),
    'database': os.environ.get('DB_NAME', 'wildfire_db'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'postgres')
}

# Paths
SIMULATOR_BIN = os.environ.get('SIMULATOR_BIN', './cpp/build/wildfire_simulator')
DATA_DIR = os.environ.get('DATA_DIR', './data')
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', './output')

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)


def run_simulation_async(config, run_id):
    """Run simulation in background thread"""
    try:
        # Update status to running
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE run_id = %s",
            (run_id,)
        )
        conn.commit()
        cur.close()
        conn.close()

        # Write config file
        config_file = os.path.join(OUTPUT_DIR, f'config_{run_id}.json')
        with open(config_file, 'w') as f:
            json.dump(config, f)

        # Run simulator in simulator container using docker exec
        # Both containers share /app/output volume, so config_file path works
        result = subprocess.run(
            ['docker', 'exec', 'wildfire_simulator', SIMULATOR_BIN, config_file],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Parse output and update database
            process_simulation_results(run_id, config)

            # Update status to completed
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE simulation_runs SET status = 'completed' WHERE run_id = %s",
                (run_id,)
            )
            conn.commit()
            cur.close()
            conn.close()
        else:
            # Update status to failed
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """UPDATE simulation_runs
                   SET status = 'failed', error_message = %s
                   WHERE run_id = %s""",
                (result.stderr, run_id)
            )
            conn.commit()
            cur.close()
            conn.close()

    except Exception as e:
        # Update status to failed
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """UPDATE simulation_runs
                   SET status = 'failed', error_message = %s
                   WHERE run_id = %s""",
                (str(e), run_id)
            )
            conn.commit()
            cur.close()
            conn.close()
        except:
            pass


def process_simulation_results(run_id, config):
    """Process simulation output and store in database"""
    # Read final state file
    final_file = os.path.join(OUTPUT_DIR, f'final_state_{run_id}.json')
    if not os.path.exists(final_file):
        return

    with open(final_file, 'r') as f:
        final_state = json.load(f)

    # Read benchmark file
    bench_file = os.path.join(OUTPUT_DIR, f'benchmark_{run_id}.json')
    benchmark = {}
    if os.path.exists(bench_file):
        with open(bench_file, 'r') as f:
            benchmark = json.load(f)

    # Update simulation_runs with results
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE simulation_runs SET
            final_burned_cells = %s,
            final_burned_area_hectares = %s,
            simulation_time_minutes = %s,
            wall_time_seconds = %s,
            threads_used = %s
        WHERE run_id = %s
    """, (
        benchmark.get('cells_burned', 0),
        benchmark.get('cells_burned', 0) * config['cell_size']**2 / 10000.0,
        benchmark.get('simulated_time_minutes', 0),
        benchmark.get('wall_time_seconds', 0),
        benchmark.get('threads', 1),
        run_id
    ))

    # Store snapshots
    snapshot_files = [f for f in os.listdir(OUTPUT_DIR)
                     if f.startswith(f'snapshot_{run_id}_')]

    for snapshot_file in snapshot_files:
        with open(os.path.join(OUTPUT_DIR, snapshot_file), 'r') as f:
            snapshot = json.load(f)

        # Create polygon from perimeter points
        if snapshot['perimeter']['features']:
            points = []
            for feature in snapshot['perimeter']['features']:
                coords = feature['geometry']['coordinates']
                points.append(f"{coords[0]} {coords[1]}")

            if points:
                # Close the polygon
                points.append(points[0])
                polygon_wkt = f"POLYGON(({', '.join(points)}))"

                cur.execute("""
                    INSERT INTO simulation_snapshots
                    (run_id, simulation_time, step_number, burned_perimeter,
                     burned_cells, burning_cells, burned_area_hectares)
                    VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)
                    ON CONFLICT (run_id, step_number) DO NOTHING
                """, (
                    run_id,
                    snapshot['simulation_time'],
                    int(snapshot_file.split('_')[-1].replace('.json', '')),
                    polygon_wkt,
                    snapshot['burned_cells'],
                    snapshot['burning_cells'],
                    snapshot['burned_cells'] * config['cell_size']**2 / 10000.0
                ))

    # Store individual burned cells
    if 'grid_state' in final_state:
        for cell in final_state['grid_state']:
            cur.execute("""
                INSERT INTO burned_cells
                (run_id, grid_x, grid_y, location, ignition_time)
                VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
                ON CONFLICT (run_id, grid_x, grid_y) DO NOTHING
            """, (
                run_id,
                cell['x'],
                cell['y'],
                cell['geoX'],
                cell['geoY'],
                cell['ignition_time']
            ))

    conn.commit()
    cur.close()
    conn.close()


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/api/datasets', methods=['GET'])
def list_datasets():
    """List available fuel and elevation datasets"""
    datasets = []

    # Scan data directory for GeoTIFF files
    if os.path.exists(DATA_DIR):
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.tif') or filename.endswith('.tiff'):
                filepath = os.path.join(DATA_DIR, filename)
                dataset_type = 'fuel' if 'fuel' in filename.lower() else 'elevation'

                datasets.append({
                    'filename': filename,
                    'path': filepath,
                    'type': dataset_type,
                    'size': os.path.getsize(filepath)
                })

    return jsonify({'datasets': datasets})


@app.route('/api/simulations', methods=['POST'])
def create_simulation():
    """Create and run a new simulation"""
    data = request.json

    # Validate input
    required_fields = ['fuel_data_file', 'elevation_data_file', 'ignition_point',
                      'wind', 'fuel_moisture', 'simulation_steps']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    try:
        # Create simulation run record
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO simulation_runs
            (ignition_grid_x, ignition_grid_y, wind_speed, wind_direction,
             fuel_moisture, time_step, total_steps, fuel_data_file,
             elevation_data_file, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING run_id
        """, (
            data['ignition_point']['x'],
            data['ignition_point']['y'],
            data['wind']['speed'],
            data['wind']['direction'],
            data['fuel_moisture'],
            data.get('time_step', 1.0),
            data['simulation_steps'],
            data['fuel_data_file'],
            data['elevation_data_file']
        ))

        run_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Prepare config for simulator
        config = {
            'run_id': run_id,
            'fuel_data_file': data['fuel_data_file'],
            'elevation_data_file': data['elevation_data_file'],
            'ignition_point': data['ignition_point'],
            'wind': data['wind'],
            'fuel_moisture': data['fuel_moisture'],
            'simulation_steps': data['simulation_steps'],
            'time_step': data.get('time_step', 1.0),
            'output_dir': OUTPUT_DIR,
            'cell_size': 30.0  # Default LANDFIRE resolution
        }

        # Start simulation in background thread
        thread = threading.Thread(target=run_simulation_async, args=(config, run_id))
        thread.daemon = True
        thread.start()

        return jsonify({
            'run_id': run_id,
            'status': 'pending',
            'message': 'Simulation started'
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations', methods=['GET'])
def list_simulations():
    """List all simulations"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT * FROM recent_simulations
        """)

        simulations = cur.fetchall()
        cur.close()
        conn.close()

        # Convert to JSON-serializable format
        for sim in simulations:
            if sim['created_at']:
                sim['created_at'] = sim['created_at'].isoformat()

        return jsonify({'simulations': simulations})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations/<int:run_id>', methods=['GET'])
def get_simulation(run_id):
    """Get simulation details"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT * FROM simulation_runs WHERE run_id = %s
        """, (run_id,))

        simulation = cur.fetchone()

        if not simulation:
            return jsonify({'error': 'Simulation not found'}), 404

        # Convert datetime to ISO format
        if simulation['created_at']:
            simulation['created_at'] = simulation['created_at'].isoformat()

        cur.close()
        conn.close()

        return jsonify(simulation)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations/<int:run_id>/progress', methods=['GET'])
def get_simulation_progress(run_id):
    """Get simulation progress snapshots"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT * FROM get_simulation_progress(%s)
        """, (run_id,))

        snapshots = cur.fetchall()
        cur.close()
        conn.close()

        # Parse GeoJSON strings
        for snapshot in snapshots:
            if snapshot['perimeter_geojson']:
                snapshot['perimeter'] = json.loads(snapshot['perimeter_geojson'])
                del snapshot['perimeter_geojson']

        return jsonify({'snapshots': snapshots})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations/<int:run_id>/cells', methods=['GET'])
def get_burned_cells(run_id):
    """Get burned cells for a simulation"""
    # Optional bounding box filter
    minx = request.args.get('minx', type=float)
    miny = request.args.get('miny', type=float)
    maxx = request.args.get('maxx', type=float)
    maxy = request.args.get('maxy', type=float)

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if minx and miny and maxx and maxy:
            cur.execute("""
                SELECT * FROM get_burned_cells_in_area(%s, %s, %s, %s, %s)
            """, (run_id, minx, miny, maxx, maxy))
        else:
            cur.execute("""
                SELECT grid_x, grid_y, ignition_time, fuel_type, elevation,
                       ST_AsGeoJSON(location) as location_geojson
                FROM burned_cells
                WHERE run_id = %s
                LIMIT 10000
            """, (run_id,))

        cells = cur.fetchall()
        cur.close()
        conn.close()

        # Parse GeoJSON
        for cell in cells:
            if cell['location_geojson']:
                cell['location'] = json.loads(cell['location_geojson'])
                del cell['location_geojson']

        return jsonify({'cells': cells})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations/<int:run_id>/statistics', methods=['GET'])
def get_simulation_statistics(run_id):
    """Get simulation statistics"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT * FROM calculate_spread_statistics(%s)
        """, (run_id,))

        stats = cur.fetchone()
        cur.close()
        conn.close()

        return jsonify(stats if stats else {})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Upload custom fuel and elevation data files"""
    try:
        if 'fuel' not in request.files and 'elevation' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        uploaded_files = []

        # Process fuel file
        if 'fuel' in request.files:
            fuel_file = request.files['fuel']
            if fuel_file.filename == '':
                return jsonify({'error': 'Empty fuel filename'}), 400

            if not fuel_file.filename.lower().endswith(('.tif', '.tiff')):
                return jsonify({'error': 'Fuel file must be a GeoTIFF (.tif)'}), 400

            filename = secure_filename(fuel_file.filename)
            # Add timestamp to avoid conflicts
            name, ext = os.path.splitext(filename)
            filename = f"{name}_uploaded{ext}"

            filepath = os.path.join(DATA_DIR, filename)
            fuel_file.save(filepath)
            uploaded_files.append({'type': 'fuel', 'filename': filename, 'path': filepath})

        # Process elevation file
        if 'elevation' in request.files:
            elev_file = request.files['elevation']
            if elev_file.filename == '':
                return jsonify({'error': 'Empty elevation filename'}), 400

            if not elev_file.filename.lower().endswith(('.tif', '.tiff')):
                return jsonify({'error': 'Elevation file must be a GeoTIFF (.tif)'}), 400

            filename = secure_filename(elev_file.filename)
            # Add timestamp to avoid conflicts
            name, ext = os.path.splitext(filename)
            filename = f"{name}_uploaded{ext}"

            filepath = os.path.join(DATA_DIR, filename)
            elev_file.save(filepath)
            uploaded_files.append({'type': 'elevation', 'filename': filename, 'path': filepath})

        return jsonify({
            'message': 'Files uploaded successfully',
            'files': uploaded_files
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
