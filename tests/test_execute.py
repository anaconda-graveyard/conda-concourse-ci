import glob
import os
import subprocess

from conda_concourse_ci import execute
import conda_concourse_ci
from conda_concourse_ci.utils import HashableDict

from conda_build import api
from conda_build.conda_interface import subdir
from conda_build.utils import package_has_file, copy_into
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
                                node='build-b-linux', base_name="frank",
                                recipe_archive_version="1.0.0")
    # download the recipe tarball
    assert job['plan'][0]['get'] == 's3-archive'

    # extract the recipe tarball
    assert job['plan'][1]['config']['inputs'] == [{'name': 's3-archive'}]
    assert job['plan'][1]['config']['run']['path'] == 'tar'
    assert job['plan'][1]['config']['run']['args'][-3] == 's3-archive/recipes-frank-1.0.0.tar.bz2'

    # get upstream dependency
    assert job['plan'][2]['get'] == 's3-frank-linux-a-1.0-hbf21a9e_0'
    assert job['plan'][2]['passed'] == ['test-a-linux']

    assert job['plan'][3]['get'] == 's3-frank-linux-a-1.0-hbf21a9e_0'
    assert job['plan'][3]['passed'] == ['test-a-linux']

    # run the build
    assert job['plan'][-2]['config']['platform'] == 'linux'
    assert job['plan'][-2]['config']['inputs'] == [{'name': 'extracted-archive'},
                                                   {'name': 'packages'}]
    assert job['plan'][-2]['config']['outputs'] == [{'name': 'build-b-linux'}]
    assert job['plan'][-2]['config']['run']['args'][-1] == 'extracted-archive/b'

    # upload the built package to temporary s3 storage
    # no hash because we haven't built a, and b is thus not finalizable
    assert job['plan'][-1]['put'] == "s3-frank-linux-b-1.0-hd248202_0"
    assert job['plan'][-1]['params']['file'] == os.path.join('build-b-linux', subdir, "*.tar.bz2")


def test_get_test_recipe_job(testing_graph):
    """Test something that already exists.  Note that this is not building any dependencies."""
    job = execute.get_test_recipe_job(base_path=graph_data_dir, graph=testing_graph,
                                      node='test-b-linux', base_name="frank",
                                      recipe_archive_version="1.0.0")
    # download the recipe tarball
    assert job['plan'][0]['get'] == 's3-archive'

    # extract the recipe tarball
    assert job['plan'][1]['config']['inputs'] == [{'name': 's3-archive'}]
    assert job['plan'][1]['config']['run']['path'] == 'tar'
    assert job['plan'][1]['config']['run']['args'][-3] == 's3-archive/recipes-frank-1.0.0.tar.bz2'

    # run the test
    assert job['plan'][-1]['config']['platform'] == 'linux'
    assert job['plan'][-1]['config']['inputs'] == [{'name': 'extracted-archive'},
                                                   {'name': 'packages'}]
    assert job['plan'][-1]['config']['run']['args'][-1] == 'b'
    assert job['plan'][-1]['config']['run']['dir'] == 'extracted-archive'


def test_get_test_package_job(testing_graph):
    job = execute.get_test_package_job(graph=testing_graph, node='test-b-linux',
                                       base_name="frank")
    # download the package tarball
    assert job['plan'][0]['get'] == 's3-frank-linux-b-1.0-hd248202_0'
    assert job['plan'][0]['passed'] == ['build-b-linux']

    # run the test
    assert job['plan'][-1]['config']['platform'] == 'linux'
    assert job['plan'][-1]['config']['inputs'] == [{'name': 's3-frank-linux-b-1.0-hd248202_0'},
                                                   {'name': 'packages'}]
    output_pkg = api.get_output_file_paths(testing_graph.node['test-b-linux']['meta'])[0]
    output_pkg = os.path.basename(output_pkg)
    assert job['plan'][-1]['config']['run']['args'][-1] == os.path.join(
        "packages", subdir, output_pkg)


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
    assert plan_dict['resources'][0]['source']['regexp'] in (
        'recipes-test-1.0.0.tar.bz(.*)',
        os.path.join("s3-test-linux-a-1.0-hbf21a9e_0", 'linux-64', "a-1.0-hbf21a9e_0.tar.bz(.*)"),
        os.path.join("s3-test-linux-b-1.0-hd248202_0", 'linux-64', "b-1.0-hd248202_0.tar.bz(.*)"))


def test_get_upload_job(mocker, testing_graph):
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    types, resources, job = execute.get_upload_job(testing_graph, 'build-b-linux',
                                                   os.path.join(test_config_dir, 'uploads.d'),
                                                   config_vars)
    assert len(types) == 1
    assert len(resources) == 1
    # get config; get package; anaconda; 3 for scp; 1 command;
    assert len(job['plan']) == 7


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
    mocker.patch.object(execute, '_upload_to_s3')
    mocker.patch.object(execute, '_remove_bucket_folder')
    mocker.patch.object(execute, 'subprocess')
    execute.submit(os.path.join(test_config_dir, 'plan_director.yml'), "test", "test-pipeline", '.',
                   test_data_dir)


def test_bootstrap(mocker, testing_workdir):
    execute.bootstrap('frank')
    assert os.path.isfile('plan_director.yml')
    assert os.path.isdir('config-frank')
    assert os.path.isfile('config-frank/config.yml')
    assert os.path.isdir('config-frank/uploads.d')
    assert os.path.isdir('config-frank/build_platforms.d')
    assert os.path.isdir('config-frank/test_platforms.d')


def test_consolidate_packages(testing_workdir, testing_metadata):
    del testing_metadata.meta['requirements']
    del testing_metadata.meta['test']
    testing_metadata.config.croot = testing_workdir
    testing_metadata.config.anaconda_upload = False
    api.build(testing_metadata)
    pkgs = glob.glob(os.path.join(testing_workdir, subdir, '*.tar.bz2'))
    assert len(pkgs) > 0
    execute.consolidate_packages(testing_workdir, subdir)
    for pkg in pkgs:
        assert os.path.isfile(os.path.join(testing_workdir, 'packages', subdir,
                                           os.path.basename(pkg)))
    assert os.path.isfile(os.path.join(testing_workdir, 'packages', subdir, 'repodata.json'))
    assert os.path.isfile(os.path.join(testing_workdir, 'packages', subdir, 'repodata.json.bz2'))


def test_get_current_git_rev(testing_workdir):
    subprocess.check_call('git clone https://github.com/conda/conda_build_test_recipe'.split())
    git_repo = 'conda_build_test_recipe'
    assert execute._get_current_git_rev(git_repo) == '7e3525f4'
    with execute.checkout_git_rev('1.21.0', git_repo):
        assert execute._get_current_git_rev(git_repo) == '29bb0bd2'
        assert execute._get_current_git_rev(git_repo, True) == 'HEAD'


def test_archive_recipes(testing_workdir, monkeypatch):
    os.makedirs(os.path.join(testing_workdir, 'recipes', 'abc'))
    with open(os.path.join('recipes', 'abc', 'meta.yaml'), 'w') as f:
        f.write('wee')
    copy_into(os.path.join(test_data_dir, 'conda_forge_style_recipe'), testing_workdir)
    os.makedirs('output')
    # ensures that we test removal of any existing file
    with open(os.path.join('output', 'recipes-steve-1.0.tar.bz2'), 'w') as f:
        f.write('dummy')
    monkeypatch.chdir(os.path.join(testing_workdir, 'recipes'))
    execute._archive_recipes('../output', '.', 'steve', '1.0')
    package_path = os.path.join('../output', 'recipes-steve-1.0.tar.bz2')
    assert os.path.isfile(package_path)


def test_compute_builds(testing_workdir, monkeypatch):
    monkeypatch.chdir(test_data_dir)
    execute.compute_builds('.', 'config-name', 'master',
                           folders=['python_test', 'conda_forge_style_recipe'],
                           matrix_base_dir=os.path.join(test_data_dir, 'linux-config-test'))
    assert os.path.isdir('../output')
    files = os.listdir('../output')
    assert 'plan.yml' in files
    assert 'recipes-config-name-1.0.0.tar.bz2' in files
    tar = '../output/recipes-config-name-1.0.0.tar.bz2'

    # for debugging on remote servers
    from tarfile import TarFile
    f = TarFile.open(tar)
    flist = f.getnames()
    f.extractall()
    os.listdir('.')
    f.close()

    assert package_has_file(tar, os.path.join('build-frank-centos5-64', 'meta.yaml'))
    assert package_has_file(tar, os.path.join('build-frank-centos5-64/', 'conda_build_config.yaml'))
    assert package_has_file(tar, os.path.join('build-dummy_conda_forge_test-centos5-64',
                                              'meta.yaml')), flist
    cfg = package_has_file(tar, os.path.join('build-dummy_conda_forge_test-centos5-64/',
                                              'conda_build_config.yaml')), flist
    assert cfg is not None
    if hasattr(cfg, 'decode'):
        cfg = cfg.decode()
    assert "HashableDict" not in cfg


def test_compute_builds_intradependencies(testing_workdir, monkeypatch):
    """When we build stuff, and upstream dependencies are part of the batch, but they're
    also already installable, then we do extra work to make sure that we order our build
    so that downstream builds depend on upstream builds (and don't directly use the
    already-available packages.)"""
    monkeypatch.chdir(os.path.join(test_data_dir, 'intradependencies'))
    execute.compute_builds('.', 'config-name', 'master',
                           folders=['zlib', 'uses_zlib'],
                           matrix_base_dir=os.path.join(test_data_dir, 'linux-config-test'))
    assert os.path.isdir('../output')
    files = os.listdir('../output')
    assert 'plan.yml' in files
    with open('../output/plan.yml') as f:
        plan = yaml.load(f)

    uses_zlib_job = [job for job in plan['jobs'] if job['name'] == 'build-uses_zlib-centos5-64'][0]
    assert any(task.get('get') == 's3-test-centos5-64-zlib-1.2.8-he64c481_0'
               for task in uses_zlib_job['plan'])
