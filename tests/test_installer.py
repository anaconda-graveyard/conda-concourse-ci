import os

import pytest
import yaml

from conda_concourse_ci import installer


@pytest.fixture
def config_file(testing_workdir):
    """Create a conda_build_config.yaml file to be used by tests."""
    configuration = os.path.join(testing_workdir, 'conda_build_config.yaml')
    variants = {'python': [2.6, 2.7, 3.4, 3.5, 3.6],
                'numpy': [1.12, 1.11],
                'platform': ['linux']}

    with open(configuration, 'w') as file:
        yaml.safe_dump(variants, file)

    return configuration


@pytest.fixture
def another_config_file(testing_workdir):
    """Create a conda_build_config.yaml file to be used by tests.

    This config file contains zip_keys of python and numpy.
    """
    configuration = os.path.join(testing_workdir, 'conda_build_config.yaml')
    variants = {'python': ['3.6', '2.7'],
                'numpy': ['1.12', '1.11'],
                'platform': ['linux'],
                'zip_keys': [('python', 'numpy')]}

    with open(configuration, 'w') as file:
        yaml.safe_dump(variants, file)

    return configuration


@pytest.fixture
def platform_config(testing_workdir):
    """Create a build platform directory along with an example.yml file."""
    build_platform_dir = os.path.join(testing_workdir, 'config-test/build_platforms.d/')
    os.makedirs(build_platform_dir)

    example_config = os.path.join(build_platform_dir, 'example.yml')

    contents = {'label': 'centos5-64', 'arch': 64, 'platform': 'linux'}

    with open(example_config, 'w') as file:
        yaml.safe_dump(contents, file)

    return example_config

def test_get_config_file(config_file):
    """Test that get_config_file correctly identifies conda_build_config.yaml."""
    assert os.path.isfile(installer.get_config_file(config_file))

    # find the conda_build_config.yaml file in the cwd
    assert os.path.isfile(installer.get_config_file())


def test_get_config_file_exception():
    """Test that a RuntimeError is raised when conda_build_config.yaml isn't found."""
    with pytest.raises(RuntimeError):
        installer.get_config_file('')


def test_get_build_parameters(config_file):
    """Test that the parameters from the config_file load correctly."""
    parameters = installer.get_build_parameters(config_file)
    assert 'python' in parameters
    assert 'numpy' in parameters
    assert 'platform' in parameters
    assert [2.6, 2.7, 3.4, 3.5, 3.6] == parameters['python']
    assert [1.12, 1.11] == parameters['numpy']
    assert ['linux'] == parameters['platform']


def test_get_build_variants(config_file):
    """Test that the builds are created correctly."""
    build_variants = installer.get_build_variants(config_file)

    # one of the ten possible build variants
    build = {'cpu_optimization_target': 'nocona',
             'lua': '5.2',
             'numpy': 1.12,
             'perl': '5.22.2',
             'pin_run_as_build': {'python': {'max_pin': 'x.x', 'min_pin': 'x.x'}},
             'platform': 'linux',
             'python': 2.6,
             'r_base': '3.3.2',
             'target_platform': 'osx-109-x86_64'}

    assert build in build_variants
    assert len(build_variants) == 10


def test_get_build_variants_with_zip_keys(another_config_file):
    """Test that the builds with zip_keys are created correctly."""
    build_variants = installer.get_build_variants(another_config_file)

    build_one = {'cpu_optimization_target': 'nocona',
                 'lua': '5.2',
                 'numpy': '1.11',
                 'perl': '5.22.2',
                 'pin_run_as_build': {'python': {'max_pin': 'x.x', 'min_pin': 'x.x'}},
                 'platform': 'linux',
                 'python': '2.7',
                 'r_base': '3.3.2',
                 'target_platform': 'osx-109-x86_64',
                 'zip_keys': ['python', 'numpy']}

    build_two = {'cpu_optimization_target': 'nocona',
                 'lua': '5.2',
                 'numpy': '1.12',
                 'perl': '5.22.2',
                 'pin_run_as_build': {'python': {'max_pin': 'x.x', 'min_pin': 'x.x'}},
                 'platform': 'linux',
                 'python': '3.6',
                 'r_base': '3.3.2',
                 'target_platform': 'osx-109-x86_64',
                 'zip_keys': ['python', 'numpy']}

    assert build_one in build_variants
    assert build_two in build_variants
    assert len(build_variants) == 2


def test_get_build_plan(config_file):
    """Test that the correct builds are obtained."""
    build_variants = installer.get_build_plan(config_file)

    build = {'cpu_optimization_target': 'nocona',
             'lua': '5.2',
             'numpy': 1.12,
             'perl': '5.22.2',
             'pin_run_as_build': {'python': {'max_pin': 'x.x', 'min_pin': 'x.x'}},
             'platform': 'linux',
             'python': 2.7,
             'r_base': '3.3.2',
             'target_platform': 'osx-109-x86_64'}

    assert build in build_variants
    assert len(build_variants) == 2


def test_get_platform_file(testing_workdir, platform_config):
    """Test that an example.yml file can be found by get_platform_file."""
    assert os.path.isfile(platform_config)

    config = installer.get_platform_file(testing_workdir)
    assert os.path.isfile(config)
    assert config.endswith('example.yml')

    with open(config) as file:
        platform_file = yaml.safe_load(file)

    with open(platform_config) as other_file:
        premade_platform_file = yaml.safe_load(other_file)

    assert platform_file == premade_platform_file

def test_get_platform_file_blank():
    """Test that None is returned when a file isn't found."""

    assert installer.get_platform_file() == None


def test_osx_installer_job():
    """Test that the osx_installer_job correctly assigns darwin as platform."""
    osx_job = installer.get_installer_job('darwin')
    assert osx_job == installer.get_osx_installer_job()


def test_windows_installer_job():
    """Test that the windows_installer_job is correctly made."""
    windows_job = installer.get_windows_installer_job()

    run_args = ['-exc',
                'cwd=$(pwd)\n'
                'mkdir aroot\n'
                'cd recipe-repo-source\n'
                'python setup.py develop\n'
                'cd ibuild\n'
                'python winexe.py\n'
                'mv Miniconda*-*.exe ${cwd}/installer\n']

    assert run_args == windows_job['plan'][1]['config']['run']['args']


def test_create_jobs(testing_workdir, config_file, platform_config):
    """Test that create_jobs correctly dumps to a yaml file."""
    installer.create_jobs(testing_workdir)

    with open('output.yml') as file:
        config = yaml.safe_load(file)

    assert len(config['jobs']) == 2
    assert config['jobs'][0]['name'] == 'installer-64-py2.7-np1.12'
    assert config['jobs'][1]['name'] == 'installer-64-py3.6-np1.12'
    assert 'plan' in config['jobs'][0]
    assert 'plan' in config['jobs'][1]


def test_create_windows_job(testing_workdir, config_file):
    """Test that the platform name is correctly assigned to windows."""
    installer.create_jobs(testing_workdir, 'win32')

    with open('output.yml') as file:
        config = yaml.safe_load(file)

    assert config['jobs'][0]['plan'][1]['config']['platform'] == 'windows'


def test_create_osx_job(testing_workdir, config_file):
    """Test that the platform name is correctly assigned to osx."""
    installer.create_jobs(testing_workdir, 'osx')

    with open('output.yml') as file:
        config = yaml.safe_load(file)

    assert config['jobs'][0]['plan'][1]['config']['platform'] == 'darwin'
