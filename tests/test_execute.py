import os

from conda_concourse_ci import execute
import conda_concourse_ci
from conda_concourse_ci.utils import HashableDict

from conda_build import api
import networkx as nx
import pytest
from pytest_mock import mocker
import yaml

from .utils import (testing_graph, test_data_dir, testing_conda_resolve, testing_metadata,
                    graph_data_dir, default_worker, test_config_dir)


def test_collect_tasks(mocker, testing_conda_resolve, testing_graph):
    mocker.patch.object(execute, 'Resolve')
    mocker.patch.object(execute, 'get_index')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    execute.Resolve.return_value = testing_conda_resolve
    conda_concourse_ci.compute_build_graph._installable.return_value = True
    task_graph = execute.collect_tasks(graph_data_dir, folders=['a'],
                                       matrix_base_dir=test_config_dir)
    test_platforms = os.listdir(os.path.join(test_config_dir, 'test_platforms.d'))
    build_platforms = os.listdir(os.path.join(test_config_dir, 'build_platforms.d'))
    # one build, one test per platform, uploads only for builds.
    n_platforms = len(test_platforms) + 2 * len(build_platforms)
    # minimum args means build and test provided folders.  Two tasks.
    assert len(task_graph.nodes()) == n_platforms


boilerplate_test_vars = {'base-name': 'steve',
                         'aws-bucket': '123',
                         'aws-key-id': 'abc',
                         'aws-secret-key': 'weee',
                         'aws-region-name': 'frank'}


# def test_get_plan_text(mocker, testing_graph):
#     plan = execute.encode_plan_as_text(testing_graph, [], '1.0.0', boilerplate_test_vars)
#     reference = execute._plan_boilerplate(boilerplate_test_vars)

#     reference = reference + "\n" + yaml.dump({
#         'jobs': [
#             {'name': 'execute',
#              'public': True,
#              'plan': [
#                  {'get': 's3-archive', 'trigger': 'true',
#                   'params': {'version': '1.0.0'}},
#                  execute._extract_task('steve', '1.0.0'),
#                  execute._ls_task,
#              ]
#             }
#         ]
#     }, default_flow_style=False)
#     assert plan == reference


def test_get_build_job(testing_graph):
    job = execute.get_build_job(base_path=graph_data_dir, graph=testing_graph,
                                node='build-b-0-linux', base_name="frank",
                                recipe_archive_version="1.0.0")
    # download the recipe tarball
    assert job['plan'][0]['params']['version'] == '1.0.0'
    assert job['plan'][0]['get'] == 's3-archive'
    assert job['plan'][0]['passed'] == ['build-a-0-linux']

    # extract the recipe tarball
    assert job['plan'][1]['config']['inputs'] == [{'name': 's3-archive'}]
    assert job['plan'][1]['config']['run']['path'] == 'tar'
    assert job['plan'][1]['config']['run']['args'][-3] == 's3-archive/recipes-frank-1.0.0.tar.bz2'

    # run the build
    assert job['plan'][2]['config']['platform'] == 'linux'
    assert job['plan'][2]['config']['inputs'] == [{'name': 'extracted-archive'}]
    assert job['plan'][2]['config']['outputs'] == [{'name': 'build-b-0-linux'}]
    assert job['plan'][2]['config']['run']['args'][-1] == os.path.join('recipe-repo-source', 'b')

    # upload the built package to temporary s3 storage
    assert job['plan'][3]['put'] == "s3-frank-linux-b"
    assert job['plan'][3]['params']['from'] == "build-b-0-linux/*.tar.bz2"


def test_get_test_recipe_job(testing_graph):
    job = execute.get_test_recipe_job(base_path=graph_data_dir, graph=testing_graph,
                                      node='test-b-0-linux', base_name="frank",
                                      recipe_archive_version="1.0.0")
    # download the recipe tarball
    assert job['plan'][0]['params']['version'] == '1.0.0'
    assert job['plan'][0]['get'] == 's3-archive'
    assert job['plan'][0]['passed'] == ['build-b-0-linux']

    # extract the recipe tarball
    assert job['plan'][1]['config']['inputs'] == [{'name': 's3-archive'}]
    assert job['plan'][1]['config']['run']['path'] == 'tar'
    assert job['plan'][1]['config']['run']['args'][-3] == 's3-archive/recipes-frank-1.0.0.tar.bz2'

    # run the test
    assert job['plan'][2]['config']['platform'] == 'linux'
    assert job['plan'][2]['config']['inputs'] == [{'name': 'extracted-archive'}]
    assert job['plan'][2]['config']['run']['args'][-1] == os.path.join('recipe-repo-source', 'b')


def test_get_test_package_job(testing_graph):
    job = execute.get_test_package_job(graph=testing_graph, node='test-b-0-linux',
                                       base_name="frank")
    # download the package tarball
    assert job['plan'][0]['params']['version'] == '1.0-0'
    assert job['plan'][0]['get'] == 's3-frank-linux-b'
    assert job['plan'][0]['passed'] == ['build-b-0-linux']

    # run the test
    assert job['plan'][1]['config']['platform'] == 'linux'
    assert job['plan'][1]['config']['inputs'] == [{'name': 's3-frank-linux-b'}]
    output_pkg = api.get_output_file_path(testing_graph.node['test-b-0-linux']['meta'])
    output_pkg = os.path.basename(output_pkg)
    assert job['plan'][1]['config']['run']['args'][-1] == os.path.join('s3-frank-linux-b',
                                                                       output_pkg)


def test_graph_to_plan_with_jobs(mocker, testing_graph):
    # stub out uploads, since it depends on config file stuff and we want to manipulate it
    mocker.patch.object(execute, "get_upload_job")
    execute.get_upload_job.return_value = [], [], {}

    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    plan_dict = execute.graph_to_plan_with_jobs(graph_data_dir, testing_graph, '1.0.0',
                                                test_config_dir, config_vars)
    # s3-archive, a, b
    assert len(plan_dict['resources']) == 3
    # build a, test a, upload a, build b, test b, upload b, test c
    assert len(plan_dict['jobs']) == 7


def test_get_upload_job(mocker, testing_graph):
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    types, resources, job = execute.get_upload_job(testing_graph, 'build-b-0-linux',
                                                   os.path.join(test_config_dir, 'uploads.d'),
                                                   config_vars)
    assert len(types) == 1
    assert len(resources) == 1
    # get config; get package; anaconda; 3 for scp; 1 command;
    assert len(job['plan']) == 7


def test_unknown_job_type():
    graph = nx.DiGraph()
    meta, _, _ = api.render(os.path.join(graph_data_dir, 'a'))
    graph.add_node("invalid-somepkg-0-linux", meta=meta, worker=default_worker)
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    with pytest.raises(NotImplementedError):
        execute.graph_to_plan_with_jobs('', graph, '1.0.0', test_data_dir, config_vars)


def test_resource_to_dict():
    resource = HashableDict(source=HashableDict(options=set(('a', 'b'))))
    out = execute._resource_to_dict(resource)
    assert type(out['source']['options']) == list
    assert type(out['source']) == dict
