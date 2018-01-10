from collections import defaultdict
import os
import subprocess

from conda_build.conda_interface import Resolve
from conda_build.api import render
from conda_build.metadata import MetaData
from conda_build import conda_interface
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
    """Initialize a new git directory with two submodules."""
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


@pytest.fixture(scope='function')
def testing_submodules_repo(testing_workdir, request):
    """Initialize a new git directory with two submodules."""
    subprocess.check_call(['git', 'init'])

    # adding a commit for a readme since git diff behaves weird if
    # submodules are the first ever commit
    subprocess.check_call(['touch', 'readme.txt'])
    with open('readme.txt', 'w') as readme:
        readme.write('stuff')

    subprocess.check_call(['git', 'add', '.'])
    subprocess.check_call(['git', 'commit', '-m', 'Added readme'])

    subprocess.check_call(['git', 'submodule', 'add',
                           'https://github.com/conda-forge/conda-feedstock.git'])
    subprocess.check_call(['git', 'submodule', 'add',
                           'https://github.com/conda-forge/conda-build-feedstock.git'])

    subprocess.check_call(['git', 'add', '.'])
    subprocess.check_call(['git', 'commit', '-m', 'Added conda and cb submodules'])

    # a second commit, for testing trips back in history
    subprocess.check_call(['git', 'submodule', 'add',
                           'https://github.com/conda-forge/conda-build-all-feedstock.git'])

    subprocess.check_call(['git', 'add', '.'])
    subprocess.check_call(['git', 'commit', '-m', 'Added cba submodule'])

    return testing_workdir


@pytest.fixture(scope="function")
def testing_submodule_commit(testing_submodules_repo):
    """Change submodule revisions and names then commit.

    The conda-feedstock is changed to a prior revision and the conda-build-feedstock
    is renamed to cb3-feedstock. These changes are then committed and tested to see
    if c3i recognizes the changes."""
    os.chdir('conda-feedstock')
    subprocess.check_call(['git', 'checkout', '4648194ca029603b90de22e16b59949b5f68d2d5'])
    os.chdir(testing_submodules_repo)

    subprocess.check_call(['git', 'mv', 'conda-build-feedstock', 'cb3-feedstock'])

    subprocess.check_call(['git', 'add', '.'])
    subprocess.check_call(['git', 'commit', '-m', 'Renamed submodules'])


@pytest.fixture(scope='function')
def testing_new_submodules(testing_submodules_repo):
    """Add new submodules and commit.

    The conda-env-feedstock and conda-verify repositories are added as submodules.
    The conda-env-feedstock repository contains a recipe while the docker-images
    repository does not. c3i should recognize the conda-env-feedstock submodule
    but not the docker-images submodule."""
    subprocess.check_call(['git', 'submodule', 'add',
                           'https://github.com/conda-forge/conda-env-feedstock.git'])

    subprocess.check_call(['git', 'submodule', 'add',
                           'https://github.com/ContinuumIO/docker-images.git'])

    subprocess.check_call(['git', 'add', '.'])
    subprocess.check_call(['git', 'commit', '-m', 'Added more submodules'])

    return testing_submodules_repo


@pytest.fixture(scope='function')
def testing_graph(request):
    g = nx.DiGraph()
    a = render(os.path.join(graph_data_dir, 'a'), finalize=False)[0][0]
    g.add_node('a-on-linux', meta=a, env={}, worker=default_worker)
    b = render(os.path.join(graph_data_dir, 'b'), finalize=False)[0][0]
    g.add_node('b-on-linux', meta=b, env={}, worker=default_worker)
    g.add_edge('b-on-linux', 'a-on-linux')
    # semi-detached recipe (test-only, does not have a build part)
    c = render(os.path.join(graph_data_dir, 'c'), finalize=False)[0][0]
    g.add_node('c3itest-c-on-linux', meta=c, env={}, worker=default_worker)
    g.add_edge('c3itest-c-on-linux', 'b-on-linux')
    return g


@pytest.fixture(scope='function')
def testing_conda_resolve(request):
    pkgs = ('a', 'b', 'c', 'd')
    if conda_interface.conda_43:
        index = {conda_interface.Dist(dist_name='-'.join((pkg, '920', 'h68c14d1_0')),
                                      channel=None,
                                      name=pkg,
                                      version='920',
                                      build_string='h68c14d1_0',
                                      build_number=0):
                 conda_interface.IndexRecord(arch='x86_64', build='h68c14d1_0',
                        build_number=0, depends=tuple(),
                        license='GNU Lesser General Public License (LGPL)',
                        md5='7268f7dcc075e615af758d1243ed4f1d', name=pkg,
                        platform=conda_interface.cc_platform, requires=tuple(), size=192170,
                        subdir=conda_interface.subdir,
                        version='920', fn=pkg + '-920-h68c14d1_0.tar.bz2', schannel='r',
                        channel='https://conda.anaconda.org/r/' + conda_interface.subdir,
                        priority=1,
                        url=('https://conda.anaconda.org/r/{}/pkg-920-h68c14d1_0.tar.bz2'
                             .format(conda_interface.subdir, pkg)))
                 for pkg in pkgs}
    else:
        index = {pkg: {
                "build": "h68c14d1_0",
                "build_number": 0,
                "date": "2015-10-28",
                "depends": [],
                "license": "LGPL",
                "md5": "7268f7dcc075e615af758d1243ed4f1d",
                "name": pkg,
                "requires": [],
                "size": 303694,
                "version": "920"
                } for pkg in pkgs}
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
    d['requirements']['host'] = ['python']
    d['test']['requires'] = ['test_requirement']
    d['test']['commands'] = ['echo "A-OK"', 'exit 0']
    d['about']['home'] = "sweet home"
    d['about']['license'] = "contract in blood"
    d['about']['summary'] = "a test package"
    m = MetaData.fromdict(d)
    m.config.variant = {'python': '3.6', 'numpy': '1.11'}
    m.config.variants = [{'python': '2.7', 'numpy': '1.11'}, {'python': '3.6', 'numpy': '1.11'}]
    return m
