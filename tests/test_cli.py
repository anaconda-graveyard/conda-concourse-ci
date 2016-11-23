import os
from conda_concourse_ci import cli

import pytest
from pytest_mock import mocker

from .utils import test_data_dir, testing_workdir, graph_data_dir


def test_default_args(mocker):
    try:
        os.makedirs('version')
    except:
        pass
    try:
        os.makedirs('config-out')
    except:
        pass
    try:
        os.makedirs('output')
    except:
        pass

    with open('version/version', 'w') as f:
        f.write("1.0.0")
    args = ['examine', graph_data_dir, 'anaconda', '--folders', 'a', '--matrix-base-dir',
            test_data_dir]
    mocker.patch.object(cli, 'collect_tasks')
    cli.collect_tasks.return_value = 'steve'
    mocker.patch.object(cli, 'graph_to_plan_with_tasks')
    cli.graph_to_plan_with_tasks.return_value = ("abc: weee")
    mocker.patch.object(cli, 'write_tasks')
    cli.main(args)
    # cli.collect_tasks.assert_called_with(graph_data_dir, folders=['a'], steps=0,
    #                                      test=False, max_downstream=5,
    #                                      matrix_base_dir=test_data_dir)
    # cli.graph_to_plan_and_tasks.assert_called_with(graph_data_dir, "steve", "1.0.0",
    #                                                matrix_base_dir=test_data_dir, public=True)
    # cli.write_tasks.assert_called_with({}, 'output')


def test_argparse_input(mocker):
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises(SystemExit):
        cli.main()
