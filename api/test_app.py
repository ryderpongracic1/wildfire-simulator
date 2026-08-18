"""
Unit tests for api/validation.py.

Runs with pytest or standalone:

    python3 -m pytest api/test_app.py
    python3 api/test_app.py

Imports only the validation module, so no Flask, psycopg2, or database is
needed.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validation import (  # noqa: E402
    ValidationError,
    resolve_dataset_path,
    scan_datasets,
    validate_simulation_request,
)


class DataDirTestCase(unittest.TestCase):
    """Builds a data directory with a fuel file, an elevation file, and traps.

    Layout:
        <data>/fuel.tif
        <data>/elevation.tif
        <data>/nested/fuel.tif
        <data>/escape        -> symlink to <outside>
        <outside>/secret.tif
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.root, 'data')
        self.outside_dir = os.path.join(self.root, 'outside')
        os.makedirs(os.path.join(self.data_dir, 'nested'))
        os.makedirs(self.outside_dir)

        for path in (
            os.path.join(self.data_dir, 'fuel.tif'),
            os.path.join(self.data_dir, 'elevation.tif'),
            os.path.join(self.data_dir, 'nested', 'fuel.tif'),
            os.path.join(self.outside_dir, 'secret.tif'),
        ):
            with open(path, 'w') as f:
                f.write('x')

        os.symlink(self.outside_dir, os.path.join(self.data_dir, 'escape'))

    def tearDown(self):
        shutil.rmtree(self.root)

    def valid_request(self, **overrides):
        body = {
            'fuel_data_file': 'fuel.tif',
            'elevation_data_file': 'elevation.tif',
            'ignition_point': {'x': 10, 'y': 20},
            'wind': {'speed': 15, 'direction': 270},
            'fuel_moisture': 8.0,
            'simulation_steps': 60,
        }
        body.update(overrides)
        return body


class TestResolveDatasetPath(DataDirTestCase):

    def test_relative_path_resolves_inside_data_dir(self):
        resolved = resolve_dataset_path('fuel.tif', self.data_dir)
        self.assertEqual(resolved, os.path.realpath(
            os.path.join(self.data_dir, 'fuel.tif')))

    def test_nested_relative_path_allowed(self):
        resolved = resolve_dataset_path('nested/fuel.tif', self.data_dir)
        self.assertTrue(resolved.endswith(os.path.join('nested', 'fuel.tif')))

    def test_absolute_path_inside_data_dir_allowed(self):
        absolute = os.path.join(self.data_dir, 'fuel.tif')
        self.assertEqual(resolve_dataset_path(absolute, self.data_dir),
                         os.path.realpath(absolute))

    def test_absolute_path_outside_data_dir_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path(os.path.join(self.outside_dir, 'secret.tif'),
                                 self.data_dir)

    def test_absolute_system_path_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('/etc/passwd', self.data_dir)

    def test_dot_dot_traversal_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('../outside/secret.tif', self.data_dir)

    def test_deep_dot_dot_traversal_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('nested/../../outside/secret.tif', self.data_dir)

    def test_symlink_escaping_data_dir_rejected(self):
        # The path is lexically inside data_dir; realpath is not.
        with self.assertRaises(ValidationError):
            resolve_dataset_path('escape/secret.tif', self.data_dir)

    def test_sibling_directory_with_shared_prefix_rejected(self):
        # data_dir is <root>/data; <root>/data_evil must not pass a naive
        # startswith check.
        evil_dir = self.data_dir + '_evil'
        os.makedirs(evil_dir)
        evil_file = os.path.join(evil_dir, 'fuel.tif')
        with open(evil_file, 'w') as f:
            f.write('x')
        with self.assertRaises(ValidationError):
            resolve_dataset_path(evil_file, self.data_dir)

    def test_missing_file_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('does_not_exist.tif', self.data_dir)

    def test_path_relative_to_cwd_allowed(self):
        # GET /api/datasets returns os.path.join(DATA_DIR, name), which is
        # relative when DATA_DIR is relative ('./data/fuel.tif'); the frontend
        # posts that value straight back.
        cwd = os.getcwd()
        try:
            os.chdir(self.root)
            resolved = resolve_dataset_path('./data/fuel.tif', 'data')
            self.assertEqual(
                resolved,
                os.path.realpath(os.path.join(self.data_dir, 'fuel.tif')))
        finally:
            os.chdir(cwd)

    def test_cwd_relative_path_outside_data_dir_rejected(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.root)
            with self.assertRaises(ValidationError):
                resolve_dataset_path('./outside/secret.tif', 'data')
        finally:
            os.chdir(cwd)

    def test_directory_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('nested', self.data_dir)

    def test_data_dir_itself_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_dataset_path('.', self.data_dir)

    def test_empty_and_non_string_rejected(self):
        for bad in ('', '   ', None, 42, ['fuel.tif']):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    resolve_dataset_path(bad, self.data_dir)


class TestValidateSimulationRequest(DataDirTestCase):

    def test_valid_request_is_normalized(self):
        params = validate_simulation_request(self.valid_request(), self.data_dir)
        self.assertEqual(params['ignition_point'], {'x': 10, 'y': 20})
        self.assertEqual(params['wind'], {'speed': 15.0, 'direction': 270.0})
        self.assertEqual(params['simulation_steps'], 60)
        self.assertEqual(params['time_step'], 1.0)  # default
        self.assertTrue(os.path.isabs(params['fuel_data_file']))
        self.assertTrue(os.path.isabs(params['elevation_data_file']))

    def test_explicit_time_step_kept(self):
        params = validate_simulation_request(
            self.valid_request(time_step=0.5), self.data_dir)
        self.assertEqual(params['time_step'], 0.5)

    def test_non_dict_body_rejected(self):
        for bad in (None, [], 'fuel.tif', 7):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(bad, self.data_dir)

    def test_each_required_field_is_required(self):
        for field in ('fuel_data_file', 'elevation_data_file', 'ignition_point',
                      'wind', 'fuel_moisture', 'simulation_steps'):
            body = self.valid_request()
            del body[field]
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as ctx:
                    validate_simulation_request(body, self.data_dir)
                self.assertIn(field, str(ctx.exception))

    def test_simulation_steps_bounds(self):
        for bad in (0, -1, 100001):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(simulation_steps=bad), self.data_dir)
        for good in (1, 100000):
            with self.subTest(value=good):
                params = validate_simulation_request(
                    self.valid_request(simulation_steps=good), self.data_dir)
                self.assertEqual(params['simulation_steps'], good)

    def test_simulation_steps_must_be_integral(self):
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(simulation_steps=1.5), self.data_dir)

    def test_time_step_must_be_positive(self):
        for bad in (0, -1.0):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(time_step=bad), self.data_dir)

    def test_wind_speed_bounds(self):
        for bad in (-0.1, 200.1):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(wind={'speed': bad, 'direction': 0}),
                        self.data_dir)
        for good in (0, 200):
            with self.subTest(value=good):
                validate_simulation_request(
                    self.valid_request(wind={'speed': good, 'direction': 0}),
                    self.data_dir)

    def test_wind_direction_bounds(self):
        for bad in (-1, 361):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(wind={'speed': 5, 'direction': bad}),
                        self.data_dir)

    def test_wind_must_be_object_with_speed_and_direction(self):
        for bad in (5, None, {'speed': 5}, {'direction': 90}):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(wind=bad), self.data_dir)

    def test_fuel_moisture_bounds(self):
        for bad in (-0.1, 100.1):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(fuel_moisture=bad), self.data_dir)
        for good in (0, 100):
            with self.subTest(value=good):
                validate_simulation_request(
                    self.valid_request(fuel_moisture=good), self.data_dir)

    def test_ignition_point_must_be_object_with_x_and_y(self):
        for bad in (5, None, {'x': 1}, {'y': 1}, [1, 2]):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(ignition_point=bad), self.data_dir)

    def test_negative_ignition_point_rejected(self):
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(ignition_point={'x': -1, 'y': 0}),
                self.data_dir)

    def test_non_numeric_values_rejected(self):
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(fuel_moisture='wet'), self.data_dir)
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(simulation_steps='sixty'), self.data_dir)

    def test_booleans_rejected_as_numbers(self):
        # bool is an int subclass; True must not pass as a step count.
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(simulation_steps=True), self.data_dir)

    def test_non_finite_values_rejected(self):
        for bad in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    validate_simulation_request(
                        self.valid_request(fuel_moisture=bad), self.data_dir)

    def test_path_escape_in_request_rejected(self):
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(fuel_data_file='/etc/passwd'), self.data_dir)
        with self.assertRaises(ValidationError):
            validate_simulation_request(
                self.valid_request(
                    elevation_data_file='../outside/secret.tif'),
                self.data_dir)


class TestScanDatasets(DataDirTestCase):
    """GET /api/datasets used a flat os.listdir, so data/sample/*.tif was
    invisible and the endpoint answered {"datasets": []} on a fresh checkout."""

    def names(self, data_dir=None):
        return [d['filename'] for d in
                scan_datasets(self.data_dir if data_dir is None else data_dir)]

    def test_finds_both_top_level_and_nested_datasets(self):
        self.assertEqual(
            self.names(),
            ['elevation.tif', 'fuel.tif', os.path.join('nested', 'fuel.tif')])

    def test_every_advertised_path_is_accepted_by_resolve_dataset_path(self):
        # The contract between the two functions: what the endpoint hands out,
        # POST /api/simulations must take back.
        datasets = scan_datasets(self.data_dir)
        self.assertTrue(datasets)
        for dataset in datasets:
            with self.subTest(path=dataset['path']):
                self.assertEqual(
                    resolve_dataset_path(dataset['path'], self.data_dir),
                    os.path.realpath(
                        os.path.join(self.data_dir, dataset['filename'])))

    def test_relative_data_dir_yields_cwd_relative_paths_that_resolve(self):
        # DATA_DIR defaults to './data', so 'path' is relative too.
        cwd = os.getcwd()
        try:
            os.chdir(self.root)
            datasets = scan_datasets('data')
            self.assertEqual(
                [d['path'] for d in datasets],
                [os.path.join('data', 'elevation.tif'),
                 os.path.join('data', 'fuel.tif'),
                 os.path.join('data', 'nested', 'fuel.tif')])
            for dataset in datasets:
                resolve_dataset_path(dataset['path'], 'data')
        finally:
            os.chdir(cwd)

    def test_type_is_classified_from_the_file_name(self):
        by_name = {d['filename']: d['type'] for d in scan_datasets(self.data_dir)}
        self.assertEqual(by_name['fuel.tif'], 'fuel')
        self.assertEqual(by_name[os.path.join('nested', 'fuel.tif')], 'fuel')
        self.assertEqual(by_name['elevation.tif'], 'elevation')

    def test_directory_name_does_not_retype_the_files_inside_it(self):
        os.makedirs(os.path.join(self.data_dir, 'fuel_rasters'))
        target = os.path.join('fuel_rasters', 'elevation.tif')
        with open(os.path.join(self.data_dir, target), 'w') as f:
            f.write('x')
        by_name = {d['filename']: d['type'] for d in scan_datasets(self.data_dir)}
        self.assertEqual(by_name[target], 'elevation')

    def test_size_is_reported(self):
        sizes = {d['filename']: d['size'] for d in scan_datasets(self.data_dir)}
        self.assertEqual(sizes['fuel.tif'], 1)  # fixture writes a single byte

    def test_symlinked_directory_is_not_followed(self):
        # <data>/escape points at <outside>, which holds secret.tif. Advertising
        # it would hand out a path resolve_dataset_path rejects.
        self.assertNotIn(os.path.join('escape', 'secret.tif'), self.names())

    def test_hidden_directories_and_files_are_skipped(self):
        os.makedirs(os.path.join(self.data_dir, '.cache'))
        for path in (os.path.join(self.data_dir, '.cache', 'fuel.tif'),
                     os.path.join(self.data_dir, '.hidden_fuel.tif')):
            with open(path, 'w') as f:
                f.write('x')
        found = self.names()
        self.assertNotIn(os.path.join('.cache', 'fuel.tif'), found)
        self.assertNotIn('.hidden_fuel.tif', found)

    def test_non_geotiff_files_are_ignored(self):
        for name in ('notes.txt', 'config.json', 'fuel.tif.aux.xml'):
            with open(os.path.join(self.data_dir, name), 'w') as f:
                f.write('x')
        self.assertEqual(len(scan_datasets(self.data_dir)), 3)

    def test_tiff_and_uppercase_extensions_are_included(self):
        for name in ('fuel_big.tiff', 'ELEVATION_BIG.TIF'):
            with open(os.path.join(self.data_dir, name), 'w') as f:
                f.write('x')
        found = self.names()
        self.assertIn('fuel_big.tiff', found)
        self.assertIn('ELEVATION_BIG.TIF', found)

    def test_missing_data_dir_returns_empty_list(self):
        self.assertEqual(scan_datasets(os.path.join(self.root, 'no_such_dir')), [])

    def test_data_dir_that_is_a_file_returns_empty_list(self):
        self.assertEqual(
            scan_datasets(os.path.join(self.data_dir, 'fuel.tif')), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
