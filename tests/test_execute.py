import os
import subprocess

from conda_concourse_ci import execute
import conda_concourse_ci
from conda_concourse_ci.utils import HashableDict

from conda_build import api
from conda_build.conda_interface import subdir
from conda_build.utils import package_has_file
import networkx as nx
import pytest
import yaml

from .utils import test_data_dir, graph_data_dir, default_worker, test_config_dir


def test_collect_tasks(mocker, testing_conda_resolve, testing_graph):
    mocker.patch.object(execute, 'Resolve')
    mocker.patch.object(execute, 'get_build_index')
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


def test_get_build_task(testing_graph):
    # ensure that our channels make it into the args
    meta = testing_graph.node['build-b-linux']['meta']
    meta.config.channel_urls = ['conda_build_test']
    task = execute.get_build_task(base_path=graph_data_dir, graph=testing_graph,
                                node='build-b-linux', base_name="frank",
                                commit_id='abc123')
    assert task['config']['platform'] == 'linux'
    assert task['config']['inputs'] == [{'name': 'rsync-recipes'}, {'name': 'rsync-artifacts'}]
    assert task['config']['run']['args'][-1] == ('rsync-recipes/abc123/build-b-linux')
    assert 'conda_build_test' in task['config']['run']['args']


def test_get_test_recipe_task(testing_graph):
    """Test something that already exists.  Note that this is not building any dependencies."""
    meta = testing_graph.node['test-b-linux']['meta']
    meta.config.channel_urls = ['conda_build_test']
    task = execute.get_test_recipe_task(base_path=graph_data_dir, graph=testing_graph,
                                        node='test-b-linux', base_name="frank",
                                        commit_id='abc123')
    # run the test
    assert task['config']['platform'] == 'linux'
    assert task['config']['inputs'] == [{'name': 'rsync-recipes'}]
    assert task['config']['run']['args'][-1] == 'b'
    assert task['config']['run']['dir'] == os.path.join('rsync-recipes', 'abc123')
    assert 'conda_build_test' in task['config']['run']['args']


def test_graph_to_plan_with_jobs(mocker, testing_graph):
    # stub out uploads, since it depends on config file stuff and we want to manipulate it
    get_upload = mocker.patch.object(execute, "get_upload_tasks")
    get_upload.return_value = []

    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    plan_dict = execute.graph_to_plan_with_jobs(graph_data_dir, testing_graph, 'abc123',
                                                test_config_dir, config_vars)
    # rsync-recipes and rsync-artifacts are the only resource.  For each job, we change the 'passed' condition
    assert len(plan_dict['resources']) == 2
    # a, b, c
    assert len(plan_dict['jobs']) == 3


def test_unknown_job_type():
    graph = nx.DiGraph()
    metadata_tuples = api.render(os.path.join(graph_data_dir, 'a'))
    graph.add_node("invalid-somepkg-0-linux", meta=metadata_tuples[0][0], worker=default_worker)
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    with pytest.raises(NotImplementedError):
        execute.graph_to_plan_with_jobs('', graph, '1.0.0', test_config_dir, config_vars)


def test_resource_to_dict():
    resource = HashableDict(source=HashableDict(options=set(('a', 'b'))))
    out = execute._resource_to_dict(resource)
    assert type(out['source']['options']) == list
    assert type(out['source']) == dict


def test_submit(mocker):
    mocker.patch.object(execute, 'subprocess')
    pipeline_file = os.path.join(test_config_dir, 'plan_director.yml')
    execute.submit(pipeline_file, base_name="test", pipeline_name="test-pipeline",
                   src_dir='.', config_root_dir=os.path.join(test_data_dir, 'config-test'))


def test_bootstrap(mocker, testing_workdir):
    execute.bootstrap('frank')
    assert os.path.isfile('plan_director.yml')
    assert os.path.isdir('frank')
    assert os.path.isfile('frank/config.yml')
    assert os.path.isdir('frank/uploads.d')
    assert os.path.isdir('frank/build_platforms.d')
    assert os.path.isdir('frank/test_platforms.d')


def test_get_current_git_rev(testing_workdir):
    subprocess.check_call('git clone https://github.com/conda/conda_build_test_recipe'.split())
    git_repo = 'conda_build_test_recipe'
    assert execute._get_current_git_rev(git_repo) == '7e3525f4'
    with execute.checkout_git_rev('1.21.0', git_repo):
        assert execute._get_current_git_rev(git_repo) == '29bb0bd2'
        assert execute._get_current_git_rev(git_repo, True) == 'HEAD'


def test_compute_builds(testing_workdir, mocker, monkeypatch):
    monkeypatch.chdir(test_data_dir)
    output = os.path.join(testing_workdir, 'output')
    # neutralize git checkout so we're really testing the HEAD commit
    mocker.patch.object(execute, 'checkout_git_rev')
    execute.compute_builds('.', 'config-name', 'master',
                           folders=['python_test', 'conda_forge_style_recipe'],
                           matrix_base_dir=os.path.join(test_data_dir, 'linux-config-test'),
                           output_dir=output)
    assert os.path.isdir(output)
    files = os.listdir(output)
    assert 'plan.yml' in files

    assert os.path.isfile(os.path.join(output, 'build-frank-centos5-64', 'meta.yaml'))
    assert os.path.isfile(os.path.join(output, 'build-frank-centos5-64/', 'conda_build_config.yaml'))
    assert os.path.isfile(os.path.join(output, 'build-dummy_conda_forge_test-centos5-64',
                                              'meta.yaml'))
    with open(os.path.join(output, 'build-dummy_conda_forge_test-centos5-64/', 'conda_build_config.yaml')) as f:
        cfg = f.read()

    assert cfg is not None
    if hasattr(cfg, 'decode'):
        cfg = cfg.decode()
    assert "HashableDict" not in cfg


def test_compute_builds_intradependencies(testing_workdir, monkeypatch, mocker):
    """When we build stuff, and upstream dependencies are part of the batch, but they're
    also already installable, then we do extra work to make sure that we order our build
    so that downstream builds depend on upstream builds (and don't directly use the
    already-available packages.)"""
    monkeypatch.chdir(os.path.join(test_data_dir, 'intradependencies'))
    # neutralize git checkout so we're really testing the HEAD commit
    mocker.patch.object(execute, 'checkout_git_rev')
    output_dir = os.path.join(testing_workdir, 'output')
    execute.compute_builds('.', 'config-name', 'master',
                           folders=['zlib', 'uses_zlib'],
                           matrix_base_dir=os.path.join(test_data_dir, 'linux-config-test'),
                           output_dir=output_dir)
    assert os.path.isdir(output_dir)
    files = os.listdir(output_dir)
    assert 'plan.yml' in files
    with open(os.path.join(output_dir, 'plan.yml')) as f:
        plan = yaml.load(f)

    uses_zlib_job = [job for job in plan['jobs'] if job['name'] == 'uses_zlib-linux-64'][0]
    assert any(task.get('passed') == ['zlib-linux-64']
               for task in uses_zlib_job['plan'])


def test_compute_builds_dies_when_no_folders_and_no_git(testing_workdir, mocker, capfd):
    changed = mocker.patch.object(execute, 'git_changed_recipes')
    changed.return_value = None
    output_dir = os.path.join(testing_workdir, 'output')
    execute.compute_builds('.', 'config-name', 'master',
                           folders=None,
                           matrix_base_dir=os.path.join(test_data_dir, 'linux-config-test'),
                           output_dir=output_dir)
    out, err = capfd.readouterr()
    assert "No folders specified to build" in out
