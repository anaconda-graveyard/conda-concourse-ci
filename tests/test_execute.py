import os

from conda_concourse_ci import execute
import conda_concourse_ci

import pytest
from pytest_mock import mocker
import yaml

from .utils import (testing_graph, test_data_dir, testing_conda_resolve, testing_metadata,
                    graph_data_dir)


def test_package_key(testing_metadata):
    assert (execute.package_key('build', testing_metadata, 'linux') ==
            'build-test_package_key-1-linux')


def test_collect_tasks(mocker, testing_conda_resolve, testing_graph):
    mocker.patch.object(execute, 'Resolve')
    mocker.patch.object(execute, 'get_index')
    mocker.patch.object(execute.subprocess, 'check_call')
    mocker.patch.object(execute.subprocess, 'check_output')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    execute.subprocess.check_output.return_value = 'abc'
    execute.Resolve.return_value = testing_conda_resolve
    conda_concourse_ci.compute_build_graph._installable.return_value = True
    task_graph = execute.collect_tasks(graph_data_dir, folders=['a'],
                                       matrix_base_dir=test_data_dir)
    test_platforms = os.listdir(os.path.join(test_data_dir, 'test_platforms.d'))
    build_platforms = os.listdir(os.path.join(test_data_dir, 'build_platforms.d'))
    n_platforms = len(test_platforms) + len(build_platforms)
    # minimum args means build and test provided folders.  Two tasks.
    assert len(task_graph.nodes()) == n_platforms


def test_get_plan_text(mocker, testing_graph):
    plan = execute.graph_to_plan_text(testing_graph)
    reference = execute._plan_boilerplate()
    reference = reference + "\n" + yaml.dump({
        'jobs': [
            {'name': 'execute',
             'public': True,
             'plan': [
                 {'get': 'recipe-repo-checkout'},
                 {'get': 's3-tasks'},
                 {'get': 's3-config'},
                 {'aggregate': [{'task': 'build-b-0-linux',
                                 'file': 's3-tasks/ci-tasks/build-b-0-linux.yml'}]},
                 {'aggregate': [{'task': 'test-b-0-linux',
                                 'file': 's3-tasks/ci-tasks/test-b-0-linux.yml'}]}
             ]
            }
        ]
    })
    assert plan == reference


def test_get_task_dict(mocker, testing_graph):
    execute.get_task_dict(testing_graph, 'build-b-0-linux')
