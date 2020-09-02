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

LOGFILE_NAME_REGEXP = re.compile(r'nginx-access-ui\.log-(\d{8})((\.gz)?)$')
LOGFILE_DATETIME_FORMAT = '%Y%m%d'

LogFile = namedtuple('LogFile', ['path', 'date', 'ext'])
LogFileRow = namedtuple('LogFileRow', ['url', 'duration'])


def load_config(path, default_config):
    if not os.path.isfile(path):
        raise Exception('Config not found by path: %s' % path)
    parser = ConfigParser.ConfigParser(allow_no_value=True)
    try:
        parser.read(path)
    except (ConfigParser.MissingSectionHeaderError, ConfigParser.ParsingError):
        raise
    try:
        keys = parser.options('log_analyzer')
    except ConfigParser.NoSectionError as err:
        err.message = '%s in config file %s' % (err.message, path)
        raise
    tmp = {}
    for key in keys:
        tmp[key.upper()] = parser.get('log_analyzer', key)
    _cfg = default_config.copy()
    _cfg.update(tmp)
    return _cfg


def get_latest_logfile(log_dir, logfile_regexp, logfile_datetime_format):
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
    return gzip.open if logfile.ext == '.gz' else io.open


def logfile_generator(logfile, opener):
    # TODO: encoding='utf_8'
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
    arr = map(float, arr)
    size = len(arr)
    if size == 1:
        return arr[0]
    arr.sort()
    if size % 2 == 0:
        return (float(arr[size / 2 - 1]) + float(arr[size / 2])) / 2
    else:
        return arr[(size - 1) / 2]


def calculate(logfile, error_limit_perc_allowed):
    opener = get_logfile_opener(logfile)
    gen_rows = logfile_generator(logfile, opener)

    rows_count = 0
    error_count = 0
    total_duration = 0.0

    rows_by_url = dict()

    for url, duration in gen_rows:
        if url is None or duration is None:
            error_count += 1
            continue
        rows_count += 1
        total_duration += float(duration)

        if url not in rows_by_url:
            rows_by_url[url] = dict(count=0, durations=[], url=url)

        rows_by_url[url]['count'] += 1
        rows_by_url[url]['durations'].append(duration)

    errors_count_percentage = float(error_count) * 100 / rows_count
    if errors_count_percentage > error_limit_perc_allowed:
        msg = 'Error percentage limit allowed = %2f. Current = %.2f' % \
              (error_limit_perc_allowed, errors_count_percentage)
        logging.error(msg)
        raise Exception(msg)

    for url, data in rows_by_url.iteritems():
        data['count_perc'] = 100 * float(data['count']) / rows_count
        data['time_sum'] = sum(data['durations'])
        data['time_perc'] = 100 * data['time_sum'] / total_duration
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
    name = 'report-%s.html' % logfile.date.strftime('%Y.%m.%d')
    return os.path.join(cfg.get('REPORT_DIR'), name)


def render_report(src_path, template_path, rows):
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
    arg_parser.add_argument('--config', default='configs/default.ini', type=str)
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

