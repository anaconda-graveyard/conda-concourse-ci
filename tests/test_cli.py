import os
from conda_concourse_ci import cli

import pytest
from pytest_mock import mocker

from .utils import test_config_dir, testing_workdir, graph_data_dir


def test_argparse_input(mocker):
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises(SystemExit):
        cli.main()


