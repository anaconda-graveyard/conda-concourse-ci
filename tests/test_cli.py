import logging
import os

import pytest
from pytest_mock import mocker

from conda_concourse_ci import cli

from .utils import test_config_dir, testing_workdir, graph_data_dir


def test_argparse_input():
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises(SystemExit):
        cli.main()


def test_submit(mocker):
    mocker.patch.object(cli.execute, 'submit')
    args = ['submit', 'frank']
    cli.main(args)
    cli.execute.submit.assert_called_once()


def test_submit_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['submit']
        cli.main(args)


def test_bootstrap(mocker):
    mocker.patch.object(cli.execute, 'bootstrap')
    args = ['bootstrap', 'frank']
    cli.main(args)
    cli.execute.bootstrap.assert_called_once()


def test_bootstrap_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['bootstrap']
        cli.main(args)


def test_examine(mocker):
    mocker.patch.object(cli.execute, 'compute_builds')
    args = ['examine', 'frank']
    cli.main(args)
    cli.execute.compute_builds.assert_called_once()


def test_examine_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['examine']
        cli.main(args)


def test_consolidate(mocker):
    mocker.patch.object(cli.execute, 'consolidate_packages')
    args = ['consolidate', 'linux-64']
    cli.main(args)
    cli.execute.consolidate_packages.assert_called_once()


def test_consolidate_without_subdir_raises():
    with pytest.raises(SystemExit):
        args = ['consolidate']
        cli.main(args)


# not sure what the right syntax for this is yet.  TODO.
@pytest.mark.xfail
def test_logger_sets_debug_level(mocker):
    mocker.patch.object(cli.execute, 'submit')
    cli.main(['--debug', 'submit', 'frank'])
    assert logging.getLogger().isEnabledFor(logging.DEBUG)


def test_bad_command_raises():
    with pytest.raises(SystemExit):
        cli.main([''])
