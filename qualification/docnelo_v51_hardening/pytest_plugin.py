"""Standalone qualification hooks; no application fixtures or service initialization."""
import os

import pytest


def pytest_addoption(parser):
    parser.addoption('--require-no-skips', action='store_true',
                     help='Fail a required qualification group if any case is skipped.')


def pytest_sessionfinish(session, exitstatus):
    if session.config.getoption('--require-no-skips'):
        reporter = session.config.pluginmanager.getplugin('terminalreporter')
        if reporter is not None and reporter.stats.get('skipped'):
            reporter.write_sep('=', 'Required qualification contains skipped tests')
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_collection_modifyitems(items):
    if os.name != 'posix':
        for item in items:
            if item.get_closest_marker('posix') is not None:
                item.add_marker(pytest.mark.skip(reason='Requires native POSIX; not qualified here'))
