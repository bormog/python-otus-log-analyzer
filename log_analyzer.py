# -*- coding: utf-8 -*-

import ConfigParser
import argparse
import datetime
import gzip
import io
import json
import logging
import os
import re
import sys
from collections import namedtuple
from string import Template

config = {
    'LOG_DIR': './log',

    'REPORT_DIR': './reports',
    'REPORT_SIZE': 1000,
    'REPORT_TEMPLATE': './reports/report.html',
    'REWRITE_REPORT': 0,

    'ERROR_LIMIT_PERCENTAGE': 25.0,

    'LOGFILE': 'log_analyzer.log',
}

DEFAULT_INI_CONFIG_PATH = './configs/default.ini'

LOGFILE_NAME_REGEXP = re.compile(r'nginx-access-ui\.log-(\d{8})((\.gz)?)$')
LOGFILE_DATETIME_FORMAT = '%Y%m%d'

LogFile = namedtuple('LogFile', ['path', 'date', 'ext'])
LogFileRow = namedtuple('LogFileRow', ['url', 'duration'])


def load_config(path, default_config):
    """
    Load ini config by path, merge with default config and return dict

    :param path: path to ini file
    :type path: str
    :param default_config: key-value dict
    :type default_config: dict
    :return key-value: dict
    :rtype: dict
    """
    if not os.path.isfile(path):
        raise Exception('Config not found by path: %s' % path)
    parser = ConfigParser.ConfigParser(allow_no_value=True)
    try:
        parser.read(path)
    except (ConfigParser.MissingSectionHeaderError, ConfigParser.ParsingError):
        raise
    try:
        items = parser.items('log_analyzer')
    except ConfigParser.NoSectionError as err:
        err.message = '%s in config file %s' % (err.message, path)
        raise

    items = {k.upper(): v for k, v in items}
    _cfg = default_config.copy()
    _cfg.update(items)
    return _cfg


def get_latest_logfile(log_dir, logfile_regexp, logfile_datetime_format):
    """
    Find latest log file by regexp and datetime in filename. Return namedtuple LogFile

    :param log_dir: path to dir with nginx logs
    :type log_dir: str

    :param logfile_regexp: compiled regexp for find logs
    :type logfile_regexp: _sre.SRE_Pattern

    :param logfile_datetime_format: datetime format of nginx logs
    :type logfile_datetime_format: str

    :return: LogFile
    :rtype: namedtupe
    """
    max_datetime = None
    latest_logfile = None

    for filename in os.listdir(log_dir):
        if not os.path.isfile(os.path.join(log_dir, filename)):
            continue
        matches = re.search(logfile_regexp, filename)
        if not matches:
            continue
        datetime_str = matches.group(1)
        try:
            logfile_datetime = datetime.datetime.strptime(datetime_str, logfile_datetime_format)
        except ValueError:
            logging.exception('Cant parse datetime %s from logfile %s',
                              datetime_str,
                              filename
                              )
        else:
            if max_datetime is None or logfile_datetime > max_datetime:
                max_datetime = logfile_datetime
                latest_logfile = filename

    if not latest_logfile:
        return

    _, ext = os.path.splitext(latest_logfile)

    return LogFile(
        path=os.path.join(log_dir, latest_logfile),
        date=max_datetime,
        ext=ext
    )


def get_logfile_opener(logfile):
    """
    Check extension and return way to open file

    :param logfile: namedtuple LogFile
    :type logfile: LogFile
    :return: gzip.open or io.open
    :rtype: callable
    """
    return gzip.open if logfile.ext == '.gz' else io.open


def logfile_generator(logfile, opener):
    """
    Open ngninx log with opener and yield LogFileRow

    :param logfile: namedtuple LogFile
    :type logfile: LogFile
    :param opener: gzip.open or io.open
    :return: callable
    :rtype: generator
    """
    # TODO: encoding='utf_8, but python 2.7 does not support in gzip.open'
    with opener(logfile.path, 'r') as rows:
        for row in rows:
            parts = row.strip().split()
            try:
                url = str(parts[6])
                duration = float(parts[-1])
            except (IndexError, ValueError):
                logging.error('Cant get parts from row "%s"', row.strip())
                url = None
                duration = None
            finally:
                yield LogFileRow(url, duration)


def median(arr):
    """
    Calculate median

    :param arr: list of numbers
    :type arr: list
    :return: median
    :rtype: float
    """
    arr = map(float, arr)
    size = len(arr)
    if size == 1:
        return arr[0]
    arr.sort()
    if size % 2 == 0:
        return (float(arr[size / 2 - 1]) + float(arr[size / 2])) / 2
    else:
        return arr[(size - 1) / 2]


def percentage(part, total):
    """
    Caluclate percenage part of total

    :param part: part of total
    :type part: int|float
    :param total: total
    :type total: int|float
    :return: percentage part of total
    :rtype: float
    """
    return 100 * float(part) / total


def calculate(logfile, error_limit_perc_allowed):
    """
    Group lines from nginx log by url and do calculate.
    Sort lines by time_sum from max to min

    :param logfile: namedtuple LogFile
    :type logfile: LogFile
    :param error_limit_perc_allowed: allowed error percentage
    :type error_limit_perc_allowed: float
    :return: list of dicts
    :rtype: list
    """
    opener = get_logfile_opener(logfile)
    gen_rows = logfile_generator(logfile, opener)

    rows_count = 0
    errors_count = 0
    total_duration = 0.0

    rows_by_url = dict()

    for url, duration in gen_rows:
        rows_count += 1

        if url is None or duration is None:
            errors_count += 1
            continue

        total_duration += float(duration)

        if url not in rows_by_url:
            rows_by_url[url] = dict(count=0, durations=[], url=url)

        rows_by_url[url]['count'] += 1
        rows_by_url[url]['durations'].append(duration)

    errors_percentage = percentage(errors_count, rows_count)
    if errors_percentage > error_limit_perc_allowed:
        msg = 'Error percentage limit allowed = %2f. Current = %.2f' % \
              (error_limit_perc_allowed, errors_percentage)
        logging.error(msg)
        raise Exception(msg)

    for url, data in rows_by_url.iteritems():
        data['count_perc'] = percentage(data['count'], rows_count)
        data['time_sum'] = sum(data['durations'])
        data['time_perc'] = percentage(data['time_sum'], total_duration)
        data['time_avg'] = data['time_sum'] / len(data['durations'])
        data['time_max'] = max(data['durations'])
        data['time_med'] = median(data['durations'])
        del data['durations']

    rows = sorted(
        rows_by_url.values(),
        key=lambda x: x['time_sum'],
        reverse=True
    )

    return rows


def get_report_path(logfile):
    """
    Generate filename and return path for html report

    :param logfile: namedtuple LogFile
    :type logfile: LogFile
    :return: path for html report
    :rtype: str
    """
    name = 'report-%s.html' % logfile.date.strftime('%Y.%m.%d')
    return os.path.join(cfg.get('REPORT_DIR'), name)


def render_report(src_path, template_path, rows):
    """
    Render rows in html file by template

    :param src_path: html report path
    :type src_path: str
    :param template_path: html template for report
    :type template_path: str
    :param rows: list of rows for report
    :type rows: list
    :return: None
    """
    with io.open(template_path, 'r', encoding='utf_8') as fr:
        template_content = fr.read()

    output = Template(template_content).safe_substitute(table_json=json.dumps(rows))

    with io.open(src_path, 'w', encoding='utf_8') as fw:
        fw.write(output)


def main(cfg):
    logging.info('Config = %s', repr(cfg))

    logging.info('Start find latest log file in dir %s' % cfg['LOG_DIR'])
    logfile = get_latest_logfile(log_dir=cfg['LOG_DIR'],
                                 logfile_regexp=LOGFILE_NAME_REGEXP,
                                 logfile_datetime_format=LOGFILE_DATETIME_FORMAT
                                 )
    logging.info('Latest logfile =  %s' % repr(logfile))
    if not logfile:
        logging.info('Latest logfile not found')
        return

    report_path = get_report_path(logfile)
    if not cfg['REWRITE_REPORT']:
        if os.path.isfile(report_path):
            logging.info('Report %s already exists' % report_path)
            return

    logging.info('Start calculating')
    rows = calculate(logfile, cfg['ERROR_LIMIT_PERCENTAGE'])
    logging.info('%d rows calculated' % len(rows))

    report_size = cfg['REPORT_SIZE']
    if report_size < len(rows):
        rows = rows[0:report_size]

    logging.info('Render report to %s from %s', report_path, cfg['REPORT_TEMPLATE'])
    render_report(report_path, cfg['REPORT_TEMPLATE'], rows)


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description='Parses logs from a given directory and builds a report')
    arg_parser.add_argument('--config', default=DEFAULT_INI_CONFIG_PATH, type=str)
    args = arg_parser.parse_args()

    try:
        cfg = load_config(args.config, default_config=config)
    except Exception as err:
        msg = 'An some unexpected error occurred: %s' % err.message
        sys.exit(msg)

    logging.basicConfig(
        format='[%(asctime)s] %(levelname).1s %(message)s',
        datefmt='%Y.%m.%d %H:%M:%S',
        filename=cfg.get('LOGFILE'),
        level=logging.INFO
    )
    try:
        main(cfg)
    except Exception as err:
        msg = 'An some unexpected error occurred: %s' % err.message
        sys.exit(msg)
