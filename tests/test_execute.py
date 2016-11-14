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
    n_platforms = len(test_platforms) + len(build_platforms)
    # minimum args means build and test provided folders.  Two tasks.
    assert len(task_graph.nodes()) == n_platforms


def test_get_plan_text(mocker, testing_graph):
    plan = execute.graph_to_plan_text(testing_graph, '1.0.0')
    reference = execute._plan_boilerplate()
    reference = reference + "\n" + yaml.dump({
        'jobs': [
            {'name': 'execute',
             'public': True,
             'plan': [
                 {'get': 's3-archive', 'trigger': 'true',
                  'params': {'version': '{{version}}'}},
                 {'task': 'extract_archive',
                  'config': {
                      'inputs': [{'name': 's3-archive'}, ],
                      'outputs': [{'name': 'extracted-archive'}, ],
                      'image_resource': {
                          'type': 'docker-image',
                          'source': {'repository': 'msarahan/conda-concourse-ci'},
                          },
                      'platform': 'linux',
                      'run': {
                          'path': 'tar',
                          'args': ['-xvf', 's3-archive/tasks-and-recipes-1.0.0.tar.bz2',
                                   '-C', 'extracted-archive'],
                      }}},
                 {'aggregate': [{'task': 'build-b-0-linux',
                                 'file': 'extracted-archive/output/build-b-0-linux.yml'}]},
                 {'aggregate': [{'task': 'test-b-0-linux',
                                 'file': 'extracted-archive/output/test-b-0-linux.yml'}]}
             ]
            }
        ]
    })
    reference = reference.replace('"{{version}}"', '{{version}}').replace("'{{version}}'", '{{version}}')
    assert plan == reference


def test_get_task_dict(mocker, testing_graph):
    execute.get_task_dict(testing_graph, 'build-b-0-linux')
