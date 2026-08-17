// Wildfire Simulator Frontend Application

// ---------------------------------------------------------------------------
// API base resolution
// ---------------------------------------------------------------------------
// Default is the RELATIVE path '/api', which is correct for every deployment
// that serves the frontend and proxies the API from the same origin — that
// includes the nginx container in docker-compose (see docker/nginx.conf, which
// proxies /api/ -> api:5000).
//
// Overrides, in priority order, for running the frontend off a bare static
// server (e.g. `python -m http.server 8080`) where nothing proxies /api:
//   1. ?api=<base>            e.g. http://localhost:8080/?api=http://localhost:5001/api
//   2. window.API_BASE = ...  set by an inline <script> before app.js loads
//   3. automatic fallback: if the initial GET <base>/api/health probe fails,
//      retry against DEV_API_FALLBACK below and use it if that responds.
const DEFAULT_API_BASE = '/api';
const DEV_API_FALLBACK = 'http://localhost:5001/api';

let API_BASE = DEFAULT_API_BASE;

function configuredApiBase() {
    try {
        const fromQuery = new URLSearchParams(window.location.search).get('api');
        if (fromQuery) return fromQuery.replace(/\/+$/, '');
    } catch (e) {
        // window.location unavailable (non-browser host) - fall through
    }
    if (typeof window !== 'undefined' && window.API_BASE) {
        return String(window.API_BASE).replace(/\/+$/, '');
    }
    return null;
}

async function probeHealth(base) {
    try {
        const response = await fetch(`${base}/health`, { method: 'GET' });
        return response.ok;
    } catch (e) {
        return false;
    }
}

// Picks the API base once at startup. Explicit overrides are trusted without a
// probe; the default is probed so manual (unproxied) mode degrades gracefully.
async function resolveApiBase() {
    const explicit = configuredApiBase();
    if (explicit) {
        API_BASE = explicit;
        return API_BASE;
    }

    if (await probeHealth(DEFAULT_API_BASE)) {
        API_BASE = DEFAULT_API_BASE;
        return API_BASE;
    }

    if (await probeHealth(DEV_API_FALLBACK)) {
        API_BASE = DEV_API_FALLBACK;
        console.info(
            `No API at ${DEFAULT_API_BASE} - falling back to ${DEV_API_FALLBACK}. ` +
            'Pass ?api=<base> to pin an explicit API base.'
        );
        return API_BASE;
    }

    API_BASE = DEFAULT_API_BASE;
    setSimStatus(
        'Cannot reach the API. Start the stack (docker compose up) or pass ?api=&lt;base&gt;.',
        'error'
    );
    return API_BASE;
}

// Global state
let map;
let currentSimulation = null;
let snapshots = [];
let currentSnapshotIndex = 0;
let isPlaying = false;
let playInterval = null;
let fireLayer = null;
let perimeterLayer = null;
let ignitionMarker = null;

// Stop polling a run after this long; a queued run waiting on the API's
// bounded worker pool would otherwise poll every 2s forever.
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_DURATION_MS = 10 * 60 * 1000;

// ---------------------------------------------------------------------------
// Coordinate handling (F1)
// ---------------------------------------------------------------------------
// Snapshot perimeters come back as GeoJSON in whatever CRS the source raster
// used: the API stores the simulator's geo coordinates verbatim and labels them
// SRID 4326 without reprojecting. LANDFIRE rasters are natively EPSG:5070
// (NAD83 Conus Albers, metres); this repo's own sample data
// (data/sample/generate_test_data.py) is EPSG:4326 degrees. The JSON carries no
// CRS tag, so we discriminate by magnitude: anything inside the degree domain
// is treated as already-WGS84, everything else as Albers metres.
//
// PROPER FIX (API-side follow-up, not done here): have the C++ exporter write
// the raster's CRS into the snapshot JSON and the API carry it through to the
// client, so this heuristic can be replaced with the real answer.
const WGS84_MAX_LON = 180;
const WGS84_MAX_LAT = 90;

// True when every coordinate in the ring is a plausible lon/lat degree pair.
// Pure function - unit tested in frontend/crs_test.js.
function looksLikeWgs84(ring) {
    if (!Array.isArray(ring) || ring.length === 0) return false;
    return ring.every(coord =>
        Array.isArray(coord) &&
        coord.length >= 2 &&
        Number.isFinite(coord[0]) &&
        Number.isFinite(coord[1]) &&
        Math.abs(coord[0]) <= WGS84_MAX_LON &&
        Math.abs(coord[1]) <= WGS84_MAX_LAT
    );
}

// Default projector: EPSG:5070 (metres) -> [lon, lat]. Injected as a parameter
// everywhere below so the geometry code stays testable without proj4/Leaflet.
function albersToLonLat(x, y) {
    return proj4('EPSG:5070', 'EPSG:4326', [x, y]);
}

// Converts one GeoJSON ring ([[x, y], ...]) to Leaflet [lat, lon] pairs,
// skipping the projection when the ring is already in degrees.
// Pure function - unit tested in frontend/crs_test.js.
function ringToLatLngs(ring, transform = albersToLonLat) {
    if (!Array.isArray(ring)) return [];
    const alreadyWgs84 = looksLikeWgs84(ring);
    return ring.map(coord => {
        const x = coord[0];
        const y = coord[1];
        if (alreadyWgs84) return [y, x];
        const projected = transform(x, y);
        return [projected[1], projected[0]];
    });
}

// Mean of a list of [lat, lon] pairs, or null when the list is empty.
// Pure function - unit tested in frontend/crs_test.js.
function latLngsCentroid(latLngs) {
    if (!Array.isArray(latLngs) || latLngs.length === 0) return null;
    const sum = latLngs.reduce(
        (acc, p) => [acc[0] + p[0], acc[1] + p[1]],
        [0, 0]
    );
    return [sum[0] / latLngs.length, sum[1] / latLngs.length];
}

// Single entry point for perimeter geometry: accepts the snapshot's GeoJSON
// (Polygon, or MultiPolygon should a PostGIS version return one) and yields
// Leaflet-ready rings plus their centroid. Replaces three copies of the
// transform-and-average logic that used to live in loadSimulation and
// displaySnapshot.
// Pure function - unit tested in frontend/crs_test.js.
function projectPerimeter(geojson, transform = albersToLonLat) {
    const empty = { rings: [], center: null };
    if (!geojson || !geojson.coordinates) return empty;

    let outerRings;
    if (geojson.type === 'Polygon') {
        outerRings = [geojson.coordinates[0]];
    } else if (geojson.type === 'MultiPolygon') {
        outerRings = geojson.coordinates.map(polygon => polygon[0]);
    } else {
        return empty;
    }

    const rings = outerRings
        .filter(ring => Array.isArray(ring) && ring.length > 0)
        .map(ring => ringToLatLngs(ring, transform))
        .filter(ring => ring.length > 0);

    if (rings.length === 0) return empty;

    // Centroid over every vertex of every ring.
    const allPoints = rings.reduce((acc, ring) => acc.concat(ring), []);
    return { rings, center: latLngsCentroid(allPoints) };
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------
function initMap() {
    // Opening view; replaced by the fire's own centroid once a run is loaded.
    map = L.map('map').setView([34.27, -119.29], 11);

    // Add base layer - OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18
    }).addTo(map);

    // Add terrain layer option
    const terrainLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenTopoMap contributors',
        maxZoom: 17
    });

    const baseLayers = {
        "Street Map": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }),
        "Terrain": terrainLayer
    };

    L.control.layers(baseLayers).addTo(map);

    // Initialize fire visualization layers
    fireLayer = L.layerGroup().addTo(map);
    perimeterLayer = L.layerGroup().addTo(map);

    // Add legend
    addLegend();
}

// Add legend to map
function addLegend() {
    const legend = L.control({ position: 'topright' });

    legend.onAdd = function(map) {
        const div = L.DomUtil.create('div', 'legend');
        div.innerHTML = `
            <h4 style="margin: 0 0 10px 0;">Fire Status</h4>
            <div class="legend-item">
                <div class="legend-color" style="background: #ff4444;"></div>
                <span>Burning</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #cc0000;"></div>
                <span>Burned</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #ffaa00;"></div>
                <span>Perimeter</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #00ff00;"></div>
                <span>Ignition Point</span>
            </div>
        `;
        return div;
    };

    legend.addTo(map);
}

// ---------------------------------------------------------------------------
// Status line (replaces blocking alert() on the simulation happy path)
// ---------------------------------------------------------------------------
const STATUS_COLORS = {
    info: '#ff6b35',
    success: '#4CAF50',
    warning: '#ffb300',
    error: '#f44336'
};

function setSimStatus(message, kind = 'info') {
    const el = typeof document !== 'undefined'
        ? document.getElementById('simStatus')
        : null;
    if (!el) return;
    if (!message) {
        el.innerHTML = '';
        return;
    }
    el.innerHTML = `<span style="color: ${STATUS_COLORS[kind] || STATUS_COLORS.info};">${message}</span>`;
}

// ---------------------------------------------------------------------------
// Datasets (F2)
// ---------------------------------------------------------------------------
// Filenames are not a format check. Every fuel-type GeoTIFF is listed; the ✓
// marks names following the known-compatible convention, and everything else
// gets a neutral "verify" hint instead of being hidden.
const ANDERSON13_NAME_HINT = /anderson13/i;

async function loadDatasets() {
    try {
        const response = await fetch(`${API_BASE}/datasets`);
        const data = await response.json();

        const fuelSelect = document.getElementById('fuelFile');
        const elevationSelect = document.getElementById('elevationFile');

        let firstKnownFuel = null;
        let firstFuel = null;
        let matchedElevation = null;
        let firstElevation = null;

        (data.datasets || []).forEach(dataset => {
            const option = document.createElement('option');
            option.value = dataset.path;
            const size = formatBytes(dataset.size);

            if (dataset.type === 'fuel') {
                const knownCompatibleName = ANDERSON13_NAME_HINT.test(dataset.filename);
                option.textContent = knownCompatibleName
                    ? `✓ ${dataset.filename} (${size})`
                    : `${dataset.filename} (${size}) - verify Anderson 13 values 0-13`;
                fuelSelect.appendChild(option);

                if (!firstFuel) firstFuel = dataset.path;
                if (knownCompatibleName && !firstKnownFuel) firstKnownFuel = dataset.path;
            } else {
                option.textContent = `${dataset.filename} (${size})`;
                elevationSelect.appendChild(option);

                if (!firstElevation) firstElevation = dataset.path;
                if (!matchedElevation && dataset.filename.includes('demo_elevation_ventura')) {
                    matchedElevation = dataset.path;
                }
            }
        });

        // Prefer a known-compatible fuel file, otherwise the first one offered.
        const fuelChoice = firstKnownFuel || firstFuel;
        if (fuelChoice) fuelSelect.value = fuelChoice;

        const elevationChoice = matchedElevation || firstElevation;
        if (elevationChoice) elevationSelect.value = elevationChoice;

        if (!fuelChoice) {
            const option = document.createElement('option');
            option.textContent = 'No fuel GeoTIFFs found in the data directory';
            option.disabled = true;
            fuelSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Error loading datasets:', error);
    }
}

// Format bytes to human readable
function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return 'unknown size';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Load simulations list
async function loadSimulations() {
    try {
        const response = await fetch(`${API_BASE}/simulations`);
        const data = await response.json();

        const listContainer = document.getElementById('simulationList');
        listContainer.innerHTML = '';

        if (data.simulations.length === 0) {
            listContainer.innerHTML = '<p style="text-align: center; color: #888;">No simulations yet</p>';
            return;
        }

        data.simulations.forEach(sim => {
            const item = document.createElement('div');
            item.className = 'simulation-item';
            if (currentSimulation && currentSimulation.run_id === sim.run_id) {
                item.classList.add('active');
            }

            const statusClass = `status-${sim.status}`;
            const speedup = sim.speedup_vs_realtime ?
                `${sim.speedup_vs_realtime.toFixed(1)}x` : '-';

            item.innerHTML = `
                <div style="margin-bottom: 5px;">
                    <strong>Run #${sim.run_id}</strong>
                    <span class="status-badge ${statusClass}">${sim.status}</span>
                </div>
                <div style="font-size: 12px; color: #b0b0b0;">
                    Wind: ${sim.wind_speed} mph @ ${sim.wind_direction}°<br>
                    Burned: ${sim.final_burned_cells || 0} cells (${(sim.final_burned_area_hectares || 0).toFixed(1)} ha)<br>
                    Performance: ${speedup} realtime
                </div>
            `;

            item.onclick = () => loadSimulation(sim.run_id);
            listContainer.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading simulations:', error);
    }
}

// Load specific simulation
async function loadSimulation(runId) {
    try {
        // Load simulation details
        const simResponse = await fetch(`${API_BASE}/simulations/${runId}`);
        currentSimulation = await simResponse.json();

        // Load progress snapshots
        const progressResponse = await fetch(`${API_BASE}/simulations/${runId}/progress`);
        const progressData = await progressResponse.json();
        snapshots = progressData.snapshots || [];

        // Update UI
        updateStats();
        loadSimulations(); // Refresh list to highlight current

        if (snapshots.length > 0) {
            // Setup time slider
            document.getElementById('timeControl').style.display = 'block';
            const slider = document.getElementById('timeSlider');
            slider.max = snapshots.length - 1;
            slider.value = 0;
            currentSnapshotIndex = 0;

            // Display first snapshot
            displaySnapshot(0);
        } else {
            document.getElementById('timeControl').style.display = 'none';
        }

        // Centre the map on the first perimeter and mark the ignition point.
        // Both used to recompute the same centroid independently.
        const firstPerimeter = snapshots.length > 0 ? snapshots[0].perimeter : null;
        const center = projectPerimeter(firstPerimeter).center;

        if (center) {
            map.setView(center, 13);

            if (ignitionMarker) {
                map.removeLayer(ignitionMarker);
                ignitionMarker = null;
            }

            if (currentSimulation.ignition_grid_x !== null &&
                currentSimulation.ignition_grid_x !== undefined) {
                // The first perimeter's centroid is an estimate of the ignition
                // point; the API does not export its geographic coordinates.
                ignitionMarker = L.marker(center, {
                    icon: L.icon({
                        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
                        iconSize: [25, 41],
                        iconAnchor: [12, 41],
                        popupAnchor: [1, -34],
                        shadowSize: [41, 41]
                    })
                }).addTo(map);

                ignitionMarker.bindPopup(`
                    <strong>Ignition Point</strong><br>
                    Grid: (${currentSimulation.ignition_grid_x}, ${currentSimulation.ignition_grid_y})<br>
                    Wind: ${currentSimulation.wind_speed} mph @ ${currentSimulation.wind_direction}°
                `);
            }
        }

    } catch (error) {
        console.error('Error loading simulation:', error);
    }
}

// Hectares per burned cell, derived from the run's own totals so no cell size
// is hardcoded here. get_simulation_progress does not return each snapshot's
// burned_area_hectares column (API-side follow-up), so per-step area is
// estimated from this ratio.
function hectaresPerCell() {
    if (!currentSimulation) return null;
    const cells = currentSimulation.final_burned_cells;
    const hectares = currentSimulation.final_burned_area_hectares;
    if (!cells || !hectares) return null;
    return hectares / cells;
}

// Display specific snapshot
function displaySnapshot(index) {
    if (index < 0 || index >= snapshots.length) return;

    currentSnapshotIndex = index;
    const snapshot = snapshots[index];

    // Update time display
    const simTime = snapshot.simulation_time || 0;
    document.getElementById('timeDisplay').textContent =
        `Time: ${simTime.toFixed(1)} minutes (${(simTime / 60).toFixed(2)} hours)`;

    // Clear existing layers
    fireLayer.clearLayers();
    perimeterLayer.clearLayers();

    // Draw burned perimeter
    try {
        const { rings } = projectPerimeter(snapshot.perimeter);
        rings.forEach(ring => {
            L.polygon(ring, {
                color: '#ffaa00',
                fillColor: '#cc0000',
                fillOpacity: 0.5,
                weight: 3
            }).addTo(perimeterLayer);
        });
    } catch (e) {
        console.error('Error rendering perimeter:', e);
    }

    // Update slider
    document.getElementById('timeSlider').value = index;

    // Update stats
    const burnedCells = snapshot.burned_cells || 0;
    document.getElementById('statBurned').textContent = burnedCells;

    let areaHectares = snapshot.burned_area_hectares;
    if (areaHectares === null || areaHectares === undefined) {
        const perCell = hectaresPerCell();
        areaHectares = perCell !== null ? burnedCells * perCell : 0;
    }
    document.getElementById('statArea').textContent = `${areaHectares.toFixed(1)} ha`;
    document.getElementById('statSimTime').textContent = `${simTime.toFixed(1)} min`;
}

// Update statistics panel
function updateStats() {
    if (!currentSimulation) return;

    document.getElementById('statStatus').textContent = currentSimulation.status;

    // Explicit null checks: a legitimate zero-cell result must still render.
    if (currentSimulation.final_burned_cells !== null &&
        currentSimulation.final_burned_cells !== undefined) {
        document.getElementById('statBurned').textContent = currentSimulation.final_burned_cells;
    }

    if (currentSimulation.final_burned_area_hectares !== null &&
        currentSimulation.final_burned_area_hectares !== undefined) {
        document.getElementById('statArea').textContent =
            `${currentSimulation.final_burned_area_hectares.toFixed(1)} ha`;
    }

    if (currentSimulation.simulation_time_minutes) {
        document.getElementById('statSimTime').textContent =
            `${currentSimulation.simulation_time_minutes.toFixed(1)} min`;
    }

    if (currentSimulation.wall_time_seconds && currentSimulation.simulation_time_minutes) {
        const speedup = (currentSimulation.simulation_time_minutes * 60) /
                       currentSimulation.wall_time_seconds;
        document.getElementById('statPerf').textContent = `${speedup.toFixed(1)}x realtime`;
    }
}

function setRunButton(enabled, label) {
    const button = document.getElementById('runSimBtn');
    if (!button) return;
    button.disabled = !enabled;
    button.textContent = label;
}

// Run new simulation
async function runSimulation() {
    const fuelFile = document.getElementById('fuelFile').value;
    const elevationFile = document.getElementById('elevationFile').value;
    const ignitionX = parseInt(document.getElementById('ignitionX').value);
    const ignitionY = parseInt(document.getElementById('ignitionY').value);
    const windSpeed = parseFloat(document.getElementById('windSpeed').value);
    const windDirection = parseFloat(document.getElementById('windDirection').value);
    const fuelMoisture = parseFloat(document.getElementById('fuelMoisture').value);
    const simSteps = parseInt(document.getElementById('simSteps').value);

    if (!fuelFile || !elevationFile) {
        setSimStatus('Select both a fuel and an elevation data file.', 'warning');
        return;
    }

    const config = {
        fuel_data_file: fuelFile,
        elevation_data_file: elevationFile,
        ignition_point: { x: ignitionX, y: ignitionY },
        wind: { speed: windSpeed, direction: windDirection },
        fuel_moisture: fuelMoisture,
        simulation_steps: simSteps,
        time_step: 1.0
    };

    try {
        setRunButton(false, 'Submitting...');
        setSimStatus('Submitting simulation...', 'info');

        const response = await fetch(`${API_BASE}/simulations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (response.ok) {
            setSimStatus(`Run #${result.run_id} queued.`, 'info');
            pollSimulation(result.run_id);
        } else {
            setSimStatus(`Error: ${result.error}`, 'error');
            setRunButton(true, 'Run Simulation');
        }
    } catch (error) {
        console.error('Error running simulation:', error);
        setSimStatus('Could not reach the API to start the simulation.', 'error');
        setRunButton(true, 'Run Simulation');
    }
}

// Poll simulation status until it finishes or the deadline passes.
async function pollSimulation(runId) {
    const startedAt = Date.now();

    const interval = setInterval(async () => {
        if (Date.now() - startedAt > POLL_MAX_DURATION_MS) {
            clearInterval(interval);
            setRunButton(true, 'Run Simulation');
            const minutes = Math.round(POLL_MAX_DURATION_MS / 60000);
            setSimStatus(
                `Stopped watching run #${runId} after ${minutes} minutes. ` +
                'It may still be queued or running - pick it from Recent Simulations to check.',
                'warning'
            );
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/simulations/${runId}`);
            const sim = await response.json();

            if (sim.status === 'pending') {
                setRunButton(false, 'Queued...');
                setSimStatus(`Run #${runId} is queued behind other simulations.`, 'info');
                return;
            }

            if (sim.status === 'running') {
                setRunButton(false, 'Running...');
                setSimStatus(`Run #${runId} is running...`, 'info');
                return;
            }

            if (sim.status === 'completed' || sim.status === 'failed') {
                clearInterval(interval);
                setRunButton(true, 'Run Simulation');
                loadSimulations();

                if (sim.status === 'failed') {
                    setSimStatus(
                        `Run #${runId} failed: ${sim.error_message || 'unknown error'}`,
                        'error'
                    );
                    return;
                }

                loadSimulation(runId);

                // A completed run that burned nothing is the classic
                // off-grid-ignition symptom: the simulator bounds-checks the
                // ignition cell and no-ops rather than failing.
                if (!sim.final_burned_cells) {
                    setSimStatus(
                        `Run #${runId} completed but burned 0 cells - the ignition point ` +
                        'may be outside the grid or on non-burnable fuel (fuel type 0).',
                        'warning'
                    );
                } else {
                    setSimStatus(
                        `Run #${runId} completed: ${sim.final_burned_cells} cells burned.`,
                        'success'
                    );
                }
            }
        } catch (error) {
            console.error('Error polling simulation:', error);
        }
    }, POLL_INTERVAL_MS);
}

// Playback controls
function play() {
    if (isPlaying) return;
    isPlaying = true;

    document.getElementById('playBtn').style.display = 'none';
    document.getElementById('pauseBtn').style.display = 'inline-block';

    playInterval = setInterval(() => {
        if (currentSnapshotIndex < snapshots.length - 1) {
            displaySnapshot(currentSnapshotIndex + 1);
        } else {
            pause();
        }
    }, 500); // 500ms between frames
}

function pause() {
    isPlaying = false;
    document.getElementById('playBtn').style.display = 'inline-block';
    document.getElementById('pauseBtn').style.display = 'none';

    if (playInterval) {
        clearInterval(playInterval);
        playInterval = null;
    }
}

function reset() {
    pause();
    displaySnapshot(0);
}

// Upload custom data files
async function uploadFiles() {
    const fuelFile = document.getElementById('uploadFuel').files[0];
    const elevationFile = document.getElementById('uploadElevation').files[0];
    const statusDiv = document.getElementById('uploadStatus');

    if (!fuelFile && !elevationFile) {
        statusDiv.innerHTML = '<span style="color: #f44336;">Please select at least one file to upload</span>';
        return;
    }

    const uploadBtn = document.getElementById('uploadBtn');
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';
    statusDiv.innerHTML = '<span style="color: #ff6b35;">Uploading files...</span>';

    try {
        const formData = new FormData();
        if (fuelFile) formData.append('fuel', fuelFile);
        if (elevationFile) formData.append('elevation', elevationFile);

        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            statusDiv.innerHTML = `<span style="color: #4CAF50;">✓ Files uploaded successfully!</span>`;
            // Clear file inputs
            document.getElementById('uploadFuel').value = '';
            document.getElementById('uploadElevation').value = '';
            // Reload datasets to show new files
            setTimeout(() => {
                refreshDatasets();
                statusDiv.innerHTML = '';
            }, 2000);
        } else {
            statusDiv.innerHTML = `<span style="color: #f44336;">Error: ${result.error}</span>`;
        }
    } catch (error) {
        console.error('Upload error:', error);
        statusDiv.innerHTML = '<span style="color: #f44336;">Upload failed. Please check file format.</span>';
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload Files';
    }
}

// Rebuild both dropdowns from scratch (loadDatasets appends).
function refreshDatasets() {
    const fuelSelect = document.getElementById('fuelFile');
    const elevationSelect = document.getElementById('elevationFile');
    fuelSelect.innerHTML = '<option value="">Select fuel data...</option>';
    elevationSelect.innerHTML = '<option value="">Select elevation data...</option>';
    return loadDatasets();
}

// Show format information
function showFormatInfo(e) {
    e.preventDefault();
    alert(`Anderson 13 Fuel Models

The simulator requires fuel data in Anderson 13 format with these fuel types:

0  = No fuel (non-burnable)
1  = Short grass (1 ft)
2  = Timber (grass and understory)
3  = Tall grass (2.5 ft)
4  = Chaparral (6 ft)
5  = Brush (2 ft)
6  = Dormant brush, hardwood slash
7  = Southern rough
8  = Closed timber litter
9  = Hardwood litter
10 = Timber (litter and understory)
11 = Light logging slash
12 = Medium logging slash
13 = Heavy logging slash

FILE REQUIREMENTS:
• Format: GeoTIFF (.tif)
• Projection: Any (NAD83 Albers recommended)
• Fuel values: 0-13 only
• Elevation: Meters above sea level
• Both files must have matching dimensions and resolution

If you have LANDFIRE FBFM40 data (values 101-204), use the conversion script:
    python scripts/remap_fbfm40_to_anderson13.py input.tif output.tif

See FUEL_DATA_CONVERSION.md for detailed instructions.`);
}

// Event listeners (skipped when this file is loaded outside a browser, e.g. by
// the node unit test for the CRS helpers).
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', async () => {
        initMap();

        await resolveApiBase();

        loadDatasets();
        loadSimulations();

        // Refresh simulations every 5 seconds
        setInterval(loadSimulations, 5000);

        document.getElementById('runSimBtn').onclick = runSimulation;
        document.getElementById('uploadBtn').onclick = uploadFiles;
        document.getElementById('showFormatInfo').onclick = showFormatInfo;
        document.getElementById('timeSlider').oninput = (e) => {
            pause();
            displaySnapshot(parseInt(e.target.value));
        };
        document.getElementById('playBtn').onclick = play;
        document.getElementById('pauseBtn').onclick = pause;
        document.getElementById('resetBtn').onclick = reset;
    });
}

// Exported for the node unit test (frontend/crs_test.js). Harmless in the
// browser, where `module` is undefined.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        looksLikeWgs84,
        ringToLatLngs,
        latLngsCentroid,
        projectPerimeter
    };
}
