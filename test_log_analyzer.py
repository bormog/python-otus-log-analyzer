import unittest
import configparser
import os
import datetime
import log_analyzer
import logging

FIXTURE_DIR = './tests/fixtures'


class TestLoadConfig(unittest.TestCase):
    NOT_EXSISTS_CONFIG = 'this_path_is_not_exists.ini'
    NO_SECTION_CONFIG = 'no_section.ini'
    NO_APP_SECTION_CONFIG = 'no_app_section.ini'
    SAMPLE_CONFIG = 'stage.ini'

    def test_load_config_by_invalid_path(self):
        ini_invalid_path = os.path.join(FIXTURE_DIR, self.NOT_EXSISTS_CONFIG)
        with self.assertRaises(Exception) as err:
            log_analyzer.load_config(ini_invalid_path, {})
        self.assertEqual(
            'Config not found by path: %s' % ini_invalid_path,
            str(err.exception)
        )

    def test_load_config_no_section(self):
        ini_no_section_path = os.path.join(FIXTURE_DIR, self.NO_SECTION_CONFIG)
        with self.assertRaises(configparser.MissingSectionHeaderError):
            log_analyzer.load_config(ini_no_section_path, {})

    def test_load_config_no_app_section(self):
        ini_no_app_section_path = os.path.join(FIXTURE_DIR, self.NO_APP_SECTION_CONFIG)
        with self.assertRaises(configparser.NoSectionError):
            log_analyzer.load_config(ini_no_app_section_path, {})

    def test_load_config_keys_is_upper(self):
        ini_sample_path = os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG)
        cfg = log_analyzer.load_config(ini_sample_path, {})
        self.assertIn('FOO', cfg)
        self.assertIn('FOOBAR', cfg)

    def test_load_config_none_value_allowed(self):
        ini_sample_path = os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG)
        cfg = log_analyzer.load_config(ini_sample_path, {})
        self.assertEqual(cfg['FOOBAR'], '')

    def test_load_config_override_default(self):
        ini_sample_path = os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG)
        cfg = log_analyzer.load_config(
            ini_sample_path,
            default_config={'FOO': 'foo', 'FOOBAR': 100500}
        )
        self.assertEqual(cfg.get('FOO'), 'bar')
        self.assertEqual(cfg.get('FOOBAR'), '')


class TestGetLatestLogFile(unittest.TestCase):
    TEST_LOG_DIR = 'tests_log'

    def setUp(self):
        logging.disable(logging.CRITICAL)
        os.mkdir(self.TEST_LOG_DIR)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        for filename in os.listdir(self.TEST_LOG_DIR):
            os.remove(os.path.join(self.TEST_LOG_DIR, filename))
        os.rmdir(self.TEST_LOG_DIR)

    def _generate_logs(self, filenames):
        for filename in filenames:
            open(os.path.join(self.TEST_LOG_DIR, filename), 'w').close()

    def _get_logfile(self):
        logfile = log_analyzer.get_latest_logfile(
            self.TEST_LOG_DIR,
            log_analyzer.LOGFILE_NAME_REGEXP,
            log_analyzer.LOGFILE_DATETIME_FORMAT
        )
        return logfile

    def test_get_latest_logfile_not_found(self):
        logfile = self._get_logfile()
        self.assertEqual(logfile, None)

    def test_get_latest_logfile_is_namedtuple(self):
        filenames = ['nginx-access-ui.log-20200101.gz']
        self._generate_logs(filenames)
        logfile = self._get_logfile()
        self.assertIsInstance(logfile, log_analyzer.LogFile)

    def test_get_latest_logfile_is_last(self):
        filenames = (
            'nginx-access-ui.log-20200101.gz',
            'nginx-access-ui.log-20200102.gz',
            'nginx-access-ui.log-20200103.gz'
        )
        self._generate_logs(filenames)
        logfile = self._get_logfile()
        self.assertEqual(
            logfile.date.strftime(log_analyzer.LOGFILE_DATETIME_FORMAT),
            '20200103'
        )

    def test_get_latest_logfile_dateformat_valid(self):
        filenames = ['nginx-access-ui.log-01012020.gz']
        self._generate_logs(filenames)
        logfile = self._get_logfile()
        self.assertEqual(logfile, None)

    def test_get_latest_logfile_plain_allowed(self):
        filenames = ['nginx-access-ui.log-20200101']
        self._generate_logs(filenames)
        logfile = self._get_logfile()
        self.assertEqual(logfile.ext, '.log-20200101')

    def test_get_latest_logfile_not_gz_not_allowed(self):
        filenames = ['nginx-access-ui.log-20200101.bz2']
        self._generate_logs(filenames)
        logfile = self._get_logfile()
        self.assertEqual(logfile, None)


class TestCalculate(unittest.TestCase):
    SAMPLE_LOGFILE = 'nginx-access-ui.log-20200101'

    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_calculate_rows_has_keys(self):
        logfile = log_analyzer.LogFile(
            path=os.path.join(FIXTURE_DIR, self.SAMPLE_LOGFILE),
            date=datetime.date(2020, 1, 1),
            ext='.log-20200101'
        )
        grows = log_analyzer.logfile_generator(
            logfile,
            opener=log_analyzer.get_logfile_opener(logfile)
        )
        rows = log_analyzer.calculate(grows, 100)
        keys = (
            'count',
            'count_perc',
            'time_sum',
            'time_perc',
            'time_avg',
            'time_max',
            'time_med'
        )
        row = rows[0]
        for key in keys:
            self.assertIn(key, row, 'logrow has key "%s"' % key)

    def test_calculate_failed_if_errors_to_high(self):
        logfile = log_analyzer.LogFile(
            path=os.path.join(FIXTURE_DIR, self.SAMPLE_LOGFILE),
            date=datetime.date(2020, 1, 1),
            ext='.log-20200101'
        )
        grows = log_analyzer.logfile_generator(
            logfile,
            opener=log_analyzer.get_logfile_opener(logfile)
        )
        with self.assertRaises(Exception) as err:
            log_analyzer.calculate(grows, error_limit_perc_allowed=float('-inf'))
        self.assertEqual(
            'Error percentage limit allowed = -inf. Current = 0.00',
            str(err.exception)
        )

    def test_calculate_is_sorted(self):
        rows = [log_analyzer.LogFileRow(url=i, duration=i) for i in range(1, 6)]
        rows_by_url = log_analyzer.calculate(rows, 100)
        self.assertEqual(rows_by_url[0]['url'], 5)
        self.assertEqual(rows_by_url[-1]['url'], 1)


class TestPercentage(unittest.TestCase):

    def test_percentage_return_float(self):
        a = b = 1
        self.assertIsInstance(log_analyzer.percentage(a, b), float)

    def test_percentage_is_correct(self):
        cases = (
            [[1, 100], 1],
            [[100, 100], 100],
            [[55.5, 100], 55.5],
            [[55.5, 132], 42.04]
        )
        for (a, b), ret in cases:
            self.assertAlmostEqual(log_analyzer.percentage(a, b), ret, 1)


class TestMedian(unittest.TestCase):

    def test_median_is_correct(self):
        cases = (
            [[1],  1],
            [[1, 1], 1],
            [[3, 2, 1], 2],
            [[4, 3, 2, 1], 2.5]
        )
        for arr, ret in cases:
            self.assertAlmostEqual(log_analyzer.median(arr), ret)


if __name__ == '__main__':
    unittest.main()
