"""
Wildfire Simulator Flask API
Provides REST endpoints for running simulations and retrieving results
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import logging
import signal
import subprocess
import json
import os

from validation import ValidationError, scan_datasets, validate_simulation_request

app = Flask(__name__)
CORS(app)

logger = logging.getLogger(__name__)

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

# Simulation execution limits.
# The simulator is CPU-bound and OpenMP-parallel, so running more simulations
# at once than the host can feed is a net loss: they contend for the same
# cores. Requests beyond SIM_MAX_WORKERS queue in the executor and stay
# 'pending' until a worker picks them up, which is already what 'pending'
# means to this API.
SIM_MAX_WORKERS = max(1, int(os.environ.get('SIM_MAX_WORKERS', '2')))
SIM_TIMEOUT_SECONDS = float(os.environ.get('SIM_TIMEOUT_SECONDS', '3600'))

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Module-level singleton: one bounded pool per process, instead of one
# unbounded thread per request. Note that pool threads are non-daemon, so an
# in-flight simulation delays interpreter exit; under docker the SIGTERM ->
# SIGKILL grace period bounds that wait.
simulation_executor = ThreadPoolExecutor(
    max_workers=SIM_MAX_WORKERS,
    thread_name_prefix='simulation',
)


def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(**DB_CONFIG)


def _set_status(run_id, status, error=None):
    """Set a run's status, and optionally its error message.

    Database failures are logged and swallowed: this is called from the
    failure paths of a background worker, where raising would replace the
    original error with a less useful one.
    """
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                if error is None:
                    cur.execute(
                        "UPDATE simulation_runs SET status = %s WHERE run_id = %s",
                        (status, run_id)
                    )
                else:
                    cur.execute(
                        """UPDATE simulation_runs
                           SET status = %s, error_message = %s
                           WHERE run_id = %s""",
                        (status, error, run_id)
                    )
            conn.commit()
    except Exception:
        logger.exception('Failed to set status %s for run %s', status, run_id)


def _kill_process_tree(proc):
    """Kill the simulator and anything it spawned.

    The child is started in its own session (start_new_session=True), so one
    killpg reaches descendants. Killing only the direct child can leave
    orphaned processes burning CPU past the timeout.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (AttributeError, OSError):
        # No process groups (non-POSIX) or the child already exited.
        proc.kill()


def run_simulation(config, run_id):
    """Run one simulation to completion on a pool worker.

    The simulator binary is built into this image (see docker/Dockerfile.api)
    and invoked directly. The previous implementation shelled out via
    'docker exec' into a sibling container, which required the host's docker
    socket to be mounted into the API container -- root on the host in
    exchange for a convenience.
    """
    try:
        _set_status(run_id, 'running')

        # Write config file
        config_file = os.path.join(OUTPUT_DIR, f'config_{run_id}.json')
        with open(config_file, 'w') as f:
            json.dump(config, f)

        try:
            proc = subprocess.Popen(
                [SIMULATOR_BIN, config_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as e:
            _set_status(run_id, 'failed',
                        f'Could not execute simulator at {SIMULATOR_BIN}: {e}')
            return

        try:
            _, stderr = proc.communicate(timeout=SIM_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            proc.communicate()
            _set_status(
                run_id, 'failed',
                f'Simulation exceeded the time limit of '
                f'{SIM_TIMEOUT_SECONDS:.0f}s and was terminated'
            )
            return

        if proc.returncode != 0:
            _set_status(run_id, 'failed',
                        stderr or f'Simulator exited {proc.returncode}')
            return

        # Parse output and update database
        process_simulation_results(run_id, config)
        _set_status(run_id, 'completed')

    except Exception as e:
        logger.exception('Simulation run %s failed', run_id)
        _set_status(run_id, 'failed', str(e))


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
    with closing(get_db_connection()) as conn:
        with conn.cursor() as cur:
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

                # Build the perimeter polygon as the convex hull of the
                # perimeter points. The perimeter cells arrive in row-scan
                # order, so joining them directly produced a self-intersecting
                # (invalid) ring; every ST_Area/ST_Intersects downstream
                # operated on garbage geometry.
                if snapshot['perimeter']['features']:
                    points = []
                    for feature in snapshot['perimeter']['features']:
                        coords = feature['geometry']['coordinates']
                        points.append(f"{coords[0]} {coords[1]}")

                    if len(points) >= 3:
                        multipoint_wkt = f"MULTIPOINT({', '.join(points)})"

                        cur.execute("""
                            INSERT INTO simulation_snapshots
                            (run_id, simulation_time, step_number,
                             burned_perimeter, burned_cells, burning_cells,
                             burned_area_hectares)
                            VALUES (%s, %s, %s,
                                    ST_CollectionExtract(
                                        ST_ConvexHull(
                                            ST_GeomFromText(%s, 4326)), 3),
                                    %s, %s, %s)
                            ON CONFLICT (run_id, step_number) DO NOTHING
                        """, (
                            run_id,
                            snapshot['simulation_time'],
                            int(snapshot_file.split('_')[-1].replace('.json', '')),
                            multipoint_wkt,
                            snapshot['burned_cells'],
                            snapshot['burning_cells'],
                            snapshot['burned_cells'] * config['cell_size']**2 / 10000.0
                        ))

            # Store individual burned cells in one batched statement.
            # The previous loop issued one INSERT round-trip per burned cell,
            # which dominated result-processing time for large fires.
            if 'grid_state' in final_state:
                rows = [
                    (run_id, cell['x'], cell['y'], cell['geoX'], cell['geoY'],
                     cell['ignition_time'])
                    for cell in final_state['grid_state']
                ]
                if rows:
                    execute_values(cur, """
                        INSERT INTO burned_cells
                        (run_id, grid_x, grid_y, location, ignition_time)
                        VALUES %s
                        ON CONFLICT (run_id, grid_x, grid_y) DO NOTHING
                    """, rows,
                        template=("(%s, %s, %s, "
                                  "ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)"),
                        page_size=1000)

        conn.commit()


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/api/datasets', methods=['GET'])
def list_datasets():
    """List available fuel and elevation datasets, at any depth under DATA_DIR"""
    return jsonify({'datasets': scan_datasets(DATA_DIR)})


@app.route('/api/simulations', methods=['POST'])
def create_simulation():
    """Create and queue a new simulation"""
    try:
        params = validate_simulation_request(request.get_json(silent=True), DATA_DIR)
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400

    try:
        # Create simulation run record
        with closing(get_db_connection()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO simulation_runs
                    (ignition_grid_x, ignition_grid_y, wind_speed, wind_direction,
                     fuel_moisture, time_step, total_steps, fuel_data_file,
                     elevation_data_file, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    RETURNING run_id
                """, (
                    params['ignition_point']['x'],
                    params['ignition_point']['y'],
                    params['wind']['speed'],
                    params['wind']['direction'],
                    params['fuel_moisture'],
                    params['time_step'],
                    params['simulation_steps'],
                    params['fuel_data_file'],
                    params['elevation_data_file']
                ))

                run_id = cur.fetchone()[0]
            conn.commit()

        # Prepare config for simulator
        config = dict(params)
        config['run_id'] = run_id
        config['output_dir'] = OUTPUT_DIR
        config['cell_size'] = 30.0  # Default LANDFIRE resolution

        # Queue the run on the bounded pool. Beyond SIM_MAX_WORKERS concurrent
        # runs this waits its turn, and the row stays 'pending' until a worker
        # picks it up.
        simulation_executor.submit(run_simulation, config, run_id)

        return jsonify({
            'run_id': run_id,
            'status': 'pending',
            'message': 'Simulation queued',
            'max_concurrent_simulations': SIM_MAX_WORKERS
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations', methods=['GET'])
def list_simulations():
    """List all simulations"""
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM recent_simulations
                """)

                simulations = cur.fetchall()

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
        with closing(get_db_connection()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM simulation_runs WHERE run_id = %s
                """, (run_id,))

                simulation = cur.fetchone()

        # The 404 path used to return before closing the connection.
        if not simulation:
            return jsonify({'error': 'Simulation not found'}), 404

        # Convert datetime to ISO format
        if simulation['created_at']:
            simulation['created_at'] = simulation['created_at'].isoformat()

        return jsonify(simulation)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulations/<int:run_id>/progress', methods=['GET'])
def get_simulation_progress(run_id):
    """Get simulation progress snapshots"""
    try:
        with closing(get_db_connection()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM get_simulation_progress(%s)
                """, (run_id,))

                snapshots = cur.fetchall()

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
        with closing(get_db_connection()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if all(v is not None for v in (minx, miny, maxx, maxy)):
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
        with closing(get_db_connection()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calculate_spread_statistics(%s)
                """, (run_id,))

                stats = cur.fetchone()

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
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug)
