// Wildfire Simulator Frontend Application

const API_BASE = 'http://localhost:5001/api';

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

// Initialize map
function initMap() {
    // Center on Ventura area where demo data is from
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

// Load available datasets
async function loadDatasets() {
    try {
        const response = await fetch(`${API_BASE}/datasets`);
        const data = await response.json();

        const fuelSelect = document.getElementById('fuelFile');
        const elevationSelect = document.getElementById('elevationFile');

        data.datasets.forEach(dataset => {
            const option = document.createElement('option');
            option.value = dataset.path;

            // For fuel files, only show Anderson 13 compatible files
            if (dataset.type === 'fuel') {
                // Check if file is Anderson 13 compatible
                const isAnderson13 = dataset.filename.includes('anderson13');

                if (isAnderson13) {
                    option.textContent = `✓ ${dataset.filename} (${formatBytes(dataset.size)})`;
                    fuelSelect.appendChild(option.cloneNode(true));
                    // Auto-select first Anderson 13 file
                    if (fuelSelect.options.length === 2) { // First real option after placeholder
                        fuelSelect.value = dataset.path;
                    }
                }
                // Don't show non-Anderson13 fuel files in dropdown
            } else {
                option.textContent = `${dataset.filename} (${formatBytes(dataset.size)})`;
                elevationSelect.appendChild(option.cloneNode(true));
                // Auto-select matching Ventura elevation file
                if (dataset.filename.includes('demo_elevation_ventura')) {
                    elevationSelect.value = dataset.path;
                }
            }
        });

        // Show warning if no compatible fuel files found
        if (fuelSelect.options.length === 1) {
            const option = document.createElement('option');
            option.textContent = 'No compatible fuel files found';
            option.disabled = true;
            fuelSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Error loading datasets:', error);
    }
}

// Format bytes to human readable
function formatBytes(bytes) {
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
        }

        // Set ignition point marker and center map on first perimeter
        if (snapshots.length > 0 && snapshots[0].perimeter) {
            // Center map on the fire perimeter
            const firstPerimeter = snapshots[0].perimeter;
            if (firstPerimeter.coordinates && firstPerimeter.coordinates[0].length > 0) {
                // Get center of perimeter
                const coords = firstPerimeter.coordinates[0];
                const centerX = coords.reduce((sum, c) => sum + c[0], 0) / coords.length;
                const centerY = coords.reduce((sum, c) => sum + c[1], 0) / coords.length;
                const [lon, lat] = proj4('EPSG:5070', 'EPSG:4326', [centerX, centerY]);
                map.setView([lat, lon], 13);
            }
        }

        // Set ignition point marker
        if (currentSimulation.ignition_grid_x !== null && snapshots.length > 0 && snapshots[0].perimeter) {
            if (ignitionMarker) {
                map.removeLayer(ignitionMarker);
            }

            // Estimate ignition point from first perimeter center
            const firstPerimeter = snapshots[0].perimeter;
            if (firstPerimeter.coordinates && firstPerimeter.coordinates[0].length > 0) {
                const coords = firstPerimeter.coordinates[0];
                const centerX = coords.reduce((sum, c) => sum + c[0], 0) / coords.length;
                const centerY = coords.reduce((sum, c) => sum + c[1], 0) / coords.length;
                const [lon, lat] = proj4('EPSG:5070', 'EPSG:4326', [centerX, centerY]);

                    ignitionMarker = L.marker([lat, lon], {
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

                map.setView([lat, lon], 13);
            }
        }

    } catch (error) {
        console.error('Error loading simulation:', error);
    }
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
    if (snapshot.perimeter) {
        try {
            const geojson = snapshot.perimeter; // Already an object, no need to parse

            if (geojson.type === 'Polygon' && geojson.coordinates) {
                // Transform coordinates from Albers (EPSG:5070) to WGS84 (EPSG:4326)
                const coords = geojson.coordinates[0].map(coord => {
                    const [x, y] = coord;
                    const [lon, lat] = proj4('EPSG:5070', 'EPSG:4326', [x, y]);
                    return [lat, lon]; // Leaflet uses [lat, lon] format
                });

                L.polygon(coords, {
                    color: '#ffaa00',
                    fillColor: '#cc0000',
                    fillOpacity: 0.5,
                    weight: 3
                }).addTo(perimeterLayer);
            }
        } catch (e) {
            console.error('Error parsing perimeter:', e);
        }
    }

    // Update slider
    document.getElementById('timeSlider').value = index;

    // Update stats
    document.getElementById('statBurned').textContent = snapshot.burned_cells || 0;
    document.getElementById('statArea').textContent =
        `${(snapshot.burned_area_hectares || 0).toFixed(1)} ha`;
    document.getElementById('statSimTime').textContent =
        `${simTime.toFixed(1)} min`;
}

// Update statistics panel
function updateStats() {
    if (!currentSimulation) return;

    document.getElementById('statStatus').textContent = currentSimulation.status;

    if (currentSimulation.final_burned_cells) {
        document.getElementById('statBurned').textContent = currentSimulation.final_burned_cells;
    }

    if (currentSimulation.final_burned_area_hectares) {
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
        alert('Please select both fuel and elevation data files');
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
        const button = document.getElementById('runSimBtn');
        button.disabled = true;
        button.textContent = 'Running...';

        const response = await fetch(`${API_BASE}/simulations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (response.ok) {
            alert(`Simulation started! Run ID: ${result.run_id}`);

            // Poll for completion
            pollSimulation(result.run_id);
        } else {
            alert(`Error: ${result.error}`);
            button.disabled = false;
            button.textContent = 'Run Simulation';
        }
    } catch (error) {
        console.error('Error running simulation:', error);
        alert('Error starting simulation');
        document.getElementById('runSimBtn').disabled = false;
        document.getElementById('runSimBtn').textContent = 'Run Simulation';
    }
}

// Poll simulation status
async function pollSimulation(runId) {
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/simulations/${runId}`);
            const sim = await response.json();

            if (sim.status === 'completed' || sim.status === 'failed') {
                clearInterval(interval);
                document.getElementById('runSimBtn').disabled = false;
                document.getElementById('runSimBtn').textContent = 'Run Simulation';

                loadSimulations();

                if (sim.status === 'completed') {
                    loadSimulation(runId);
                    alert('Simulation completed!');
                } else {
                    alert('Simulation failed: ' + (sim.error_message || 'Unknown error'));
                }
            }
        } catch (error) {
            console.error('Error polling simulation:', error);
        }
    }, 2000);
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
                loadDatasets();
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

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    initMap();
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
