import unittest
import ConfigParser
import os
import datetime
import log_analyzer

FIXTURE_DIR = './tests/fixtures'


class TestLoadConfig(unittest.TestCase):
    NOT_EXSISTS_CONFIG = 'this_path_is_not_exists.ini'
    NO_SECTION_CONFIG = 'no_section.ini'
    NO_APP_SECTION_CONFIG = 'no_app_section.ini'
    SAMPLE_CONFIG = 'stage.ini'

    def test_load_config_by_invalid_path(self):
        invalid_path = os.path.join(FIXTURE_DIR, self.NOT_EXSISTS_CONFIG)
        with self.assertRaises(Exception) as err:
            log_analyzer.load_config(invalid_path, {})
        self.assertEqual(
            'Config not found by path: %s' % invalid_path,
            str(err.exception.message)
        )

    def test_load_config_no_section(self):
        with self.assertRaises(ConfigParser.MissingSectionHeaderError):
            log_analyzer.load_config(
                os.path.join(FIXTURE_DIR, self.NO_SECTION_CONFIG),
                {}
            )

    def test_load_config_no_app_section(self):
        with self.assertRaises(ConfigParser.NoSectionError):
            log_analyzer.load_config(
                os.path.join(FIXTURE_DIR, self.NO_APP_SECTION_CONFIG),
                {}
            )

    def test_load_config_keys_is_upper(self):
        cfg = log_analyzer.load_config(
            os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG),
            {}
        )
        self.assertIn('FOO', cfg)

    def test_load_config_none_value_allowed(self):
        cfg = log_analyzer.load_config(
            os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG),
            {}
        )
        self.assertEqual(cfg['FOOBAR'], None)

    def test_load_config_override_default(self):
        cfg = log_analyzer.load_config(
            os.path.join(FIXTURE_DIR, self.SAMPLE_CONFIG),
            {'FOO': 'foo'}
        )
        self.assertEqual(cfg.get('FOO'), 'bar')


class TestGetLatestLogFile(unittest.TestCase):
    TEST_LOG_DIR = 'tests_log'

    def setUp(self):
        os.mkdir(self.TEST_LOG_DIR)

    def tearDown(self):
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

    def test_rows_has_keys(self):
        logfile = log_analyzer.LogFile(
            path=os.path.join(FIXTURE_DIR, self.SAMPLE_LOGFILE),
            date=datetime.date(2020, 01, 01),
            ext='.log-20200101'
        )
        rows = log_analyzer.calculate(logfile, 100)
        keys = (
            'count',
            'count_perc',
            'time_sum',
            'time_perc',
            'time_avg',
            'time_max',
            'time_med'
        )
        row = rows.pop()
        for key in keys:
            self.assertIn(key, row, 'logrow has key "%s"' % key)

    def test_failed_if_errors_to_high(self):
        logfile = log_analyzer.LogFile(
            path=os.path.join(FIXTURE_DIR, self.SAMPLE_LOGFILE),
            date=datetime.date(2020, 01, 01),
            ext='.log-20200101'
        )
        with self.assertRaises(Exception) as err:
            log_analyzer.calculate(logfile, -1)
        self.assertEqual(
            'Error percentage limit allowed = -1. Current = 0',
            str(err.exception.message)
        )


if __name__ == '__main__':
    unittest.main()
