from conda_concourse_ci import cli

import pytest
from pytest_mock import mocker

from .utils import test_data_dir, testing_workdir


def test_default_args(mocker):
    args = [test_data_dir]
    mocker.patch.object(cli, 'collect_tasks')
    cli.collect_tasks.return_value = 'steve'
    mocker.patch.object(cli, 'graph_to_plan_and_tasks')
    cli.graph_to_plan_and_tasks.return_value = ("steve", {})
    mocker.patch.object(cli, 'write_tasks')
    cli.build_cli(args)
    cli.collect_tasks.assert_called_with(test_data_dir, folders=[], steps=0,
                                         test=False, max_downstream=5)
    cli.graph_to_plan_and_tasks.assert_called_with("steve", True)
    cli.write_tasks.assert_called_with({'plan': 'steve'})


def test_argparse_input(mocker):
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises(SystemExit):
        cli.build_cli()
