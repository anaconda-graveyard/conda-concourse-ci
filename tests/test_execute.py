import os

from conda_concourse_ci import execute
import conda_concourse_ci

import pytest
from pytest_mock import mocker
import yaml

from .utils import (testing_graph, test_data_dir, testing_conda_resolve, testing_metadata,
                    graph_data_dir)


def test_collect_tasks(mocker, testing_conda_resolve, testing_graph):
    mocker.patch.object(execute, 'Resolve')
    mocker.patch.object(execute, 'get_index')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    execute.Resolve.return_value = testing_conda_resolve
    conda_concourse_ci.compute_build_graph._installable.return_value = True
    task_graph = execute.collect_tasks(graph_data_dir, folders=['a'],
                                       matrix_base_dir=test_data_dir)
    test_platforms = os.listdir(os.path.join(test_data_dir, 'test_platforms.d'))
    build_platforms = os.listdir(os.path.join(test_data_dir, 'build_platforms.d'))
    # one build, one test per platform, uploads only for builds.
    n_platforms = len(test_platforms) + 2 * len(build_platforms)
    # minimum args means build and test provided folders.  Two tasks.
    assert len(task_graph.nodes()) == n_platforms


boilerplate_test_vars = {'base-name': 'steve',
                         'aws-bucket': '123',
                         'aws-key-id': 'abc',
                         'aws-secret-key': 'weee',
                         'aws-region-name': 'frank'}


def test_get_plan_text(mocker, testing_graph):
    plan = execute.graph_to_plan_text(testing_graph, [], '1.0.0', boilerplate_test_vars)
    reference = execute._plan_boilerplate(boilerplate_test_vars)

    reference = reference + "\n" + yaml.dump({
        'jobs': [
            {'name': 'execute',
             'public': True,
             'plan': [
                 {'get': 's3-archive', 'trigger': 'true',
                  'params': {'version': '1.0.0'}},
                 execute._extract_task('steve', '1.0.0'),
                 execute._ls_task,
             ]
            }
        ]
    }, default_flow_style=False)
    assert plan == reference


def test_get_task_dict(mocker, testing_graph):
    execute.get_task_dict(test_data_dir, testing_graph, 'build-b-0-linux')
