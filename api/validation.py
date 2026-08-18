"""
Request validation and dataset discovery for the wildfire simulation API.

Deliberately free of Flask, psycopg2, and any I/O beyond the filesystem, so it
can be unit tested without the service or the database. Every validation
failure raises ValidationError, which callers turn into an HTTP 400.

Dataset discovery lives here next to resolve_dataset_path on purpose: the paths
scan_datasets advertises must be paths resolve_dataset_path accepts.
"""

import math
import os

# Bounds for the simulator's numeric inputs. These are sanity limits, not
# physics limits: their job is to stop a request from asking for an
# unbounded amount of work or feeding NaN into the model.
MAX_SIMULATION_STEPS = 100000
MAX_WIND_SPEED_MPH = 200.0
MAX_FUEL_MOISTURE_PERCENT = 100.0
# Grid coordinates are only truly bounded by the raster's dimensions, which are
# not known without opening the dataset. This is a sanity cap; an in-range but
# off-grid ignition point is the simulator's business.
MAX_GRID_COORDINATE = 100000

# File extensions GET /api/datasets advertises, matched case-insensitively.
DATASET_EXTENSIONS = frozenset(('.tif', '.tiff'))

REQUIRED_FIELDS = (
    'fuel_data_file',
    'elevation_data_file',
    'ignition_point',
    'wind',
    'fuel_moisture',
    'simulation_steps',
)


class ValidationError(ValueError):
    """A request field is missing, malformed, or out of range."""


def _require_number(value, name):
    """Coerce value to a finite float, or raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f'{name} must be a number')
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(f'{name} must be a finite number')
    return value


def _require_int(value, name):
    """Coerce value to an int, or raise. Rejects floats with a fraction."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f'{name} must be an integer')
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            raise ValidationError(f'{name} must be an integer')
    return int(value)


def _require_range(value, name, minimum, maximum):
    if value < minimum or value > maximum:
        raise ValidationError(
            f'{name} must be between {minimum} and {maximum} (got {value})')
    return value


def resolve_dataset_path(raw_path, data_dir):
    """Resolve a client-supplied dataset path inside data_dir.

    The path a client sends ends up in the simulator's config file, which the
    simulator opens directly. Without containment a client could name any
    file readable in the container.

    Accepted forms, all subject to the same containment check:
      - a path relative to data_dir ('fuel.tif', 'nested/fuel.tif')
      - an absolute path that lands inside data_dir
      - a path relative to the process working directory, which is what
        GET /api/datasets returns when DATA_DIR itself is relative
        (e.g. './data/fuel.tif')

    Symlinks are resolved before the check, so a symlink inside data_dir
    pointing outside it is rejected.

    Returns the resolved absolute path.
    """
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValidationError('dataset path must be a non-empty string')

    root = os.path.realpath(data_dir)

    if os.path.isabs(raw_path):
        candidates = [raw_path]
    else:
        candidates = [os.path.join(root, raw_path), os.path.abspath(raw_path)]

    contained = []
    for candidate in candidates:
        resolved = os.path.realpath(candidate)
        if resolved == root or not resolved.startswith(root + os.sep):
            continue
        contained.append(resolved)
        if os.path.isfile(resolved):
            return resolved

    if not contained:
        raise ValidationError(
            f'dataset path must resolve inside the data directory: {raw_path}')
    raise ValidationError(f'dataset file not found: {raw_path}')


def scan_datasets(data_dir):
    """Find the GeoTIFF datasets under data_dir, at any depth.

    A flat os.listdir missed the sample data entirely, which ships in
    data/sample/, so GET /api/datasets answered with an empty list on a fresh
    checkout and the frontend's dataset dropdowns had nothing to offer.

    Returns a list, sorted by 'filename', of:
        {'filename': path relative to data_dir ('sample/fuel.tif'),
         'path':     data_dir-rooted path, the value clients post back,
         'type':     'fuel' or 'elevation',
         'size':     bytes}

    'path' is os.path.join(data_dir, filename) -- the same construction the
    endpoint has always used for top-level files, just extended one level of
    nesting. It stays a path resolve_dataset_path accepts whether data_dir is
    absolute ('/app/data/sample/fuel.tif', an absolute path inside data_dir) or
    relative ('./data/sample/fuel.tif', a path relative to the working
    directory), which are two of the three forms it takes.

    Hidden directories and hidden files are skipped, and symlinked directories
    are not followed: a symlink out of data_dir would otherwise advertise a
    path that resolve_dataset_path then rejects.
    """
    if not os.path.isdir(data_dir):
        return []

    datasets = []
    for dirpath, dirnames, filenames in os.walk(data_dir):
        # In-place, so os.walk skips these subtrees (.git, .ipynb_checkpoints).
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        for filename in filenames:
            if filename.startswith('.'):
                continue
            if os.path.splitext(filename)[1].lower() not in DATASET_EXTENSIONS:
                continue

            relative = os.path.relpath(os.path.join(dirpath, filename), data_dir)
            try:
                size = os.path.getsize(os.path.join(dirpath, filename))
            except OSError:
                # Broken symlink, or the file went away mid-walk.
                continue

            datasets.append({
                'filename': relative,
                'path': os.path.join(data_dir, relative),
                # Heuristic on the file name only, as before: a directory named
                # 'fuel/' must not retype the elevation rasters inside it.
                'type': 'fuel' if 'fuel' in filename.lower() else 'elevation',
                'size': size,
            })

    datasets.sort(key=lambda dataset: dataset['filename'])
    return datasets


def validate_simulation_request(data, data_dir):
    """Validate a POST /api/simulations body.

    Returns a dict of normalized simulation parameters (paths resolved,
    numbers coerced). Raises ValidationError on any problem.
    """
    if not isinstance(data, dict):
        raise ValidationError('request body must be a JSON object')

    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValidationError(f'Missing required field: {field}')

    ignition = data['ignition_point']
    if not isinstance(ignition, dict) or 'x' not in ignition or 'y' not in ignition:
        raise ValidationError('ignition_point must be an object with x and y')
    ignition_x = _require_range(
        _require_int(ignition['x'], 'ignition_point.x'),
        'ignition_point.x', 0, MAX_GRID_COORDINATE)
    ignition_y = _require_range(
        _require_int(ignition['y'], 'ignition_point.y'),
        'ignition_point.y', 0, MAX_GRID_COORDINATE)

    wind = data['wind']
    if not isinstance(wind, dict) or 'speed' not in wind or 'direction' not in wind:
        raise ValidationError('wind must be an object with speed and direction')
    wind_speed = _require_range(
        _require_number(wind['speed'], 'wind.speed'),
        'wind.speed', 0.0, MAX_WIND_SPEED_MPH)
    wind_direction = _require_range(
        _require_number(wind['direction'], 'wind.direction'),
        'wind.direction', 0.0, 360.0)

    fuel_moisture = _require_range(
        _require_number(data['fuel_moisture'], 'fuel_moisture'),
        'fuel_moisture', 0.0, MAX_FUEL_MOISTURE_PERCENT)

    simulation_steps = _require_range(
        _require_int(data['simulation_steps'], 'simulation_steps'),
        'simulation_steps', 1, MAX_SIMULATION_STEPS)

    time_step = _require_number(data.get('time_step', 1.0), 'time_step')
    if time_step <= 0:
        raise ValidationError(f'time_step must be greater than 0 (got {time_step})')

    return {
        'fuel_data_file': resolve_dataset_path(data['fuel_data_file'], data_dir),
        'elevation_data_file': resolve_dataset_path(
            data['elevation_data_file'], data_dir),
        'ignition_point': {'x': ignition_x, 'y': ignition_y},
        'wind': {'speed': wind_speed, 'direction': wind_direction},
        'fuel_moisture': fuel_moisture,
        'simulation_steps': simulation_steps,
        'time_step': time_step,
    }
