// Unit tests for the frontend CRS heuristic and perimeter geometry helpers.
//
//   node frontend/crs_test.js
//
// No browser, no Leaflet, no proj4: app.js exports these as pure functions and
// the EPSG:5070 -> WGS84 projection is injected, so the test asserts on the
// branch decision rather than on proj4's arithmetic.

const assert = require('assert');
const {
    looksLikeWgs84,
    ringToLatLngs,
    latLngsCentroid,
    projectPerimeter
} = require('./app.js');

let passed = 0;
function test(name, fn) {
    fn();
    passed++;
    console.log(`  ok  ${name}`);
}

// A sentinel projector: any coordinate that reaches it was classified as
// EPSG:5070 metres. Returns [lon, lat] like proj4 does.
let transformCalls = 0;
const spyTransform = (x, y) => {
    transformCalls++;
    return [-96 + x / 100000, 23 + y / 100000];
};

// The repo's sample data extent (data/sample/generate_test_data.py):
// lon -120.5404..-120.4596, lat 38.4593..38.5407, EPSG:4326.
const sampleRing4326 = [
    [-120.5404, 38.4593],
    [-120.4596, 38.4593],
    [-120.4596, 38.5407],
    [-120.5404, 38.5407],
    [-120.5404, 38.4593]
];

// A LANDFIRE-native ring: NAD83 Conus Albers metres.
const ring5070 = [
    [-2100000, 1900000],
    [-2099000, 1900000],
    [-2099000, 1901000],
    [-2100000, 1901000],
    [-2100000, 1900000]
];

console.log('CRS heuristic');

test('degree-domain ring is recognised as WGS84', () => {
    assert.strictEqual(looksLikeWgs84(sampleRing4326), true);
});

test('Albers metre ring is not recognised as WGS84', () => {
    assert.strictEqual(looksLikeWgs84(ring5070), false);
});

test('a single out-of-domain vertex disqualifies the whole ring', () => {
    const mixed = sampleRing4326.concat([[-2100000, 1900000]]);
    assert.strictEqual(looksLikeWgs84(mixed), false);
});

test('latitude beyond 90 disqualifies the ring', () => {
    assert.strictEqual(looksLikeWgs84([[-120.5, 91]]), false);
});

test('longitude beyond 180 disqualifies the ring', () => {
    assert.strictEqual(looksLikeWgs84([[181, 38.5]]), false);
});

test('empty, non-array and non-finite inputs are not WGS84', () => {
    assert.strictEqual(looksLikeWgs84([]), false);
    assert.strictEqual(looksLikeWgs84(null), false);
    assert.strictEqual(looksLikeWgs84(undefined), false);
    assert.strictEqual(looksLikeWgs84([[NaN, 0]]), false);
    assert.strictEqual(looksLikeWgs84([[0]]), false);
});

console.log('ring projection');

test('WGS84 ring is only axis-swapped to [lat, lon], never projected', () => {
    transformCalls = 0;
    const latLngs = ringToLatLngs(sampleRing4326, spyTransform);
    assert.strictEqual(transformCalls, 0, 'proj4 must not be called for degrees');
    assert.deepStrictEqual(latLngs[0], [38.4593, -120.5404]);
    assert.strictEqual(latLngs.length, sampleRing4326.length);
    // The regression this guards: feeding degrees to the Albers inverse
    // collapsed every fire onto the projection origin near lat 23, lon -96.
    latLngs.forEach(([lat, lon]) => {
        assert.ok(lat > 38 && lat < 39, `latitude ${lat} left the sample extent`);
        assert.ok(lon > -121 && lon < -120, `longitude ${lon} left the sample extent`);
    });
});

test('Albers ring is projected exactly once per vertex', () => {
    transformCalls = 0;
    const latLngs = ringToLatLngs(ring5070, spyTransform);
    assert.strictEqual(transformCalls, ring5070.length);
    assert.deepStrictEqual(latLngs[0], [23 + 1900000 / 100000, -96 + -2100000 / 100000]);
});

test('non-array ring yields no points', () => {
    assert.deepStrictEqual(ringToLatLngs(null, spyTransform), []);
});

console.log('centroid');

test('centroid averages [lat, lon] pairs', () => {
    assert.deepStrictEqual(latLngsCentroid([[0, 0], [10, 20]]), [5, 10]);
});

test('centroid of nothing is null', () => {
    assert.strictEqual(latLngsCentroid([]), null);
    assert.strictEqual(latLngsCentroid(null), null);
});

console.log('perimeter geometry');

test('Polygon perimeter in degrees keeps its own extent', () => {
    transformCalls = 0;
    const { rings, center } = projectPerimeter(
        { type: 'Polygon', coordinates: [sampleRing4326] },
        spyTransform
    );
    assert.strictEqual(transformCalls, 0);
    assert.strictEqual(rings.length, 1);
    assert.ok(center[0] > 38.45 && center[0] < 38.55, `centroid lat ${center[0]}`);
    assert.ok(center[1] > -120.55 && center[1] < -120.45, `centroid lon ${center[1]}`);
});

test('Polygon perimeter in Albers metres is projected', () => {
    transformCalls = 0;
    const { rings } = projectPerimeter(
        { type: 'Polygon', coordinates: [ring5070] },
        spyTransform
    );
    assert.strictEqual(transformCalls, ring5070.length);
    assert.strictEqual(rings.length, 1);
});

test('MultiPolygon yields one ring per polygon', () => {
    const { rings, center } = projectPerimeter(
        {
            type: 'MultiPolygon',
            coordinates: [[sampleRing4326], [sampleRing4326]]
        },
        spyTransform
    );
    assert.strictEqual(rings.length, 2);
    assert.ok(center !== null);
});

test('missing, empty and unsupported geometries yield nothing', () => {
    assert.deepStrictEqual(projectPerimeter(null, spyTransform), { rings: [], center: null });
    assert.deepStrictEqual(projectPerimeter({ type: 'Polygon' }, spyTransform),
        { rings: [], center: null });
    assert.deepStrictEqual(projectPerimeter({ type: 'Polygon', coordinates: [[]] }, spyTransform),
        { rings: [], center: null });
    assert.deepStrictEqual(projectPerimeter({ type: 'Point', coordinates: [1, 2] }, spyTransform),
        { rings: [], center: null });
});

console.log(`\n${passed} test groups passed`);
