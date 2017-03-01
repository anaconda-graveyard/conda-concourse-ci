from collections import defaultdict
import os
import subprocess

from conda_build.conda_interface import Resolve
from conda_build.api import render
from conda_build.metadata import MetaData
import networkx as nx
import pytest

from .utils import make_recipe, graph_data_dir, default_worker


@pytest.fixture(scope='function')
def testing_workdir(tmpdir, request):
    """ Create a workdir in a safe temporary folder; cd into dir above before test, cd out after

    :param tmpdir: py.test fixture, will be injected
    :param request: py.test fixture-related, will be injected (see pytest docs)
    """

    saved_path = os.getcwd()

    tmpdir.chdir()
    # temporary folder for profiling output, if any
    tmpdir.mkdir('prof')

    def return_to_saved_path():
        if os.path.isdir(os.path.join(saved_path, 'prof')):
            profdir = tmpdir.join('prof')
            files = profdir.listdir('*.prof') if profdir.isdir() else []

            for f in files:
                f.rename(os.path.join(saved_path, 'prof', f.basename))
        os.chdir(saved_path)

    request.addfinalizer(return_to_saved_path)

    return str(tmpdir)


@pytest.fixture(scope='function')
def testing_git_repo(testing_workdir, request):
    subprocess.check_call(['git', 'init'])
    with open('sample_file', 'w') as f:
        f.write('weee')
    subprocess.check_call(['git', 'add', 'sample_file'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 1'])
    os.makedirs('not_a_recipe')
    with open(os.path.join('not_a_recipe', 'testfile'), 'w') as f:
        f.write('weee')
    make_recipe('test_dir_1')
    subprocess.check_call(['git', 'add', 'test_dir_1'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 2'])
    make_recipe('test_dir_2', ['test_dir_1'])
    subprocess.check_call(['git', 'add', 'test_dir_2'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 3'])
    make_recipe('test_dir_3', ['test_dir_2'])
    subprocess.check_call(['git', 'add', 'test_dir_3'])
    subprocess.check_call(['git', 'commit', '-m', 'commit 4'])
    return testing_workdir


@pytest.fixture(scope='function')
def testing_graph(request):
    g = nx.DiGraph()
    a = render(os.path.join(graph_data_dir, 'a'))[0][0]
    g.add_node('build-a-hbf21a9e_0-linux', meta=a, env={}, worker=default_worker)
    g.add_node('test-a-hbf21a9e_0-linux', meta=a, env={}, worker=default_worker)
    g.add_edge('test-a-hbf21a9e_0-linux', 'build-a-hbf21a9e_0-linux')
    g.add_node('upload-a-hbf21a9e_0-linux', meta=a, env={}, worker=default_worker)
    g.add_edge('upload-a-hbf21a9e_0-linux', 'test-a-hbf21a9e_0-linux')
    b = render(os.path.join(graph_data_dir, 'b'))[0][0]
    g.add_node('build-b-hd248202_0-linux', meta=b, env={}, worker=default_worker)
    g.add_edge('build-b-hd248202_0-linux', 'build-a-hbf21a9e_0-linux')
    g.add_node('test-b-hd248202_0-linux', meta=b, env={}, worker=default_worker)
    g.add_edge('test-b-hd248202_0-linux', 'build-b-hd248202_0-linux')
    g.add_node('upload-b-hd248202_0-linux', meta=b, env={}, worker=default_worker)
    g.add_edge('upload-b-hd248202_0-linux', 'test-b-hd248202_0-linux')
    c = render(os.path.join(graph_data_dir, 'c'))[0][0]
    g.add_node('test-c-h4598f22_0-linux', meta=c, env={}, worker=default_worker)
    g.add_edge('test-c-h4598f22_0-linux', 'test-b-hd248202_0-linux')
    return g


@pytest.fixture(scope='function')
def testing_conda_resolve(request):
    index = {
        "a": {
            "build": "h68c14d1_0",
            "build_number": 0,
            "date": "2015-10-28",
            "depends": [],
            "license": "LGPL",
            "md5": "7268f7dcc075e615af758d1243ed4f1d",
            "name": "a",
            "requires": [],
            "size": 303694,
            "version": "920"
        },
        "b": {
            "build": "h68c14d1_0",
            "build_number": 0,
            "date": "2015-10-28",
            "depends": [],
            "license": "LGPL",
            "md5": "7268f7dcc075e615af758d1243ed4f1d",
            "name": "b",
            "requires": [],
            "size": 303694,
            "version": "920"
        },
        "c": {
            "build": "h68c14d1_0",
            "build_number": 0,
            "date": "2015-10-28",
            "depends": [],
            "license": "LGPL",
            "md5": "7268f7dcc075e615af758d1243ed4f1d",
            "name": "c",
            "requires": [],
            "size": 303694,
            "version": "920"
        },
        "d": {
            "build": "h68c14d1_0",
            "build_number": 0,
            "date": "2015-10-28",
            "depends": [],
            "license": "LGPL",
            "md5": "7268f7dcc075e615af758d1243ed4f1d",
            "name": "d",
            "requires": [],
            "size": 303694,
            "version": "920"
        }
    }
    return Resolve(index)


@pytest.fixture(scope='function')
def testing_metadata(request):
    d = defaultdict(dict)
    d['package']['name'] = request.function.__name__
    d['package']['version'] = '1.0'
    d['build']['number'] = '1'
    d['build']['entry_points'] = []
    # MetaData does the auto stuff if the build string is None
    d['build']['string'] = None
    d['requirements']['build'] = ['build_requirement']
    d['requirements']['run'] = ['run_requirement  1.0']
    d['test']['requires'] = ['test_requirement']
    d['test']['commands'] = ['echo "A-OK"', 'exit 0']
    d['about']['home'] = "sweet home"
    d['about']['license'] = "contract in blood"
    d['about']['summary'] = "a test package"

    return MetaData.fromdict(d)
