"""
Purpose of this module is to facilitate generation of plans that build installers

Installers can currently be built with either Constructor, or the Continuum internal build system.
"""
import os

import yaml

from conda_build.variants import dict_of_lists_to_list_of_dicts


# Docker image.  Probably works for Mac and Linux, but not Windows (needs to run NSIS)
INSTALLER_IMAGE = 'msarahan/installer_builder'
C3I_IMAGE = 'msarahan/conda-concourse-ci'

PYTHON2 = '2.7'
PYTHON3 = '3.6'
NUMPY = '1.12'
PLATFORM = 'linux'
BITS = '64'
DIR = os.getcwd()


def get_config_file(path=DIR):
    """Retrieve the conda_build_config.yaml file.

    If the path provided as an argument is a conda_build_config.yaml file,
    then it is used as the configuration file. Otherwise, the current working
    directory is searched for the conda_build_config.yaml file. If the file
    is not found a RuntimeError is raised.

    Keyword argument:
    path -- the path to the conda_build_config.yaml file
    """
    if path.endswith('conda_build_config.yaml') and os.path.isfile(path):
        return path

    cwd_path = os.path.join(os.getcwd(), 'conda_build_config.yaml')

    if os.path.isfile(cwd_path):
        return cwd_path
    else:
        raise RuntimeError('conda_build_config.yaml file not found.')


def get_build_parameters(config_file):
    """Retrieve the build parameters from conda_build_config.yaml.

    Keyword argument:
    config_file -- the conda_build_config.yaml file
    """
    with open(config_file) as file:
        config = yaml.safe_load(file)

    return config


def get_build_variants(path=DIR):
    """Retrieve build variants from a conda_build_config.yaml file."""
    conda_config_file = get_config_file(path)
    build_parameters = get_build_parameters(conda_config_file)

    return dict_of_lists_to_list_of_dicts(build_parameters)


def get_build_plan(path=DIR):
    """Parse the build variants for the newest versions of numpy and python."""
    build_variants = get_build_variants(path)

    useful_builds = []
    for variant in build_variants:
        if NUMPY in str(variant.values()):
            if PYTHON2 in str(variant.values()):
                useful_builds.append(variant)
            elif PYTHON3 in str(variant.values()):
                useful_builds.append(variant)

    return useful_builds

def get_platform_file(path=DIR):
    """Retrieve the platform yaml file from build_platforms.d."""
    build_path = None
    for _, dirnames, _ in os.walk(path):
        for dirname in dirnames:
            if dirname.startswith('config-') and os.path.isdir(dirname):
                if 'build_platforms.d' in os.listdir(dirname):
                    build_path = os.path.abspath(os.path.join(dirname, 'build_platforms.d'))

    if build_path is not None:
        for filename in os.listdir(build_path):
            if filename.endswith('.yml'):
                return os.path.join(build_path, filename)

    return None


def get_upload_task(remote_destination=DIR, keyfile_path=DIR, command='scp'):
    """Retrieve the upload task.

    Keyword arguments:
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    command -- the upload command to execute
    """
    upload_task = {'task': 'upload',
                   # upload step is always on linux, so that we know that scp will work.
                   'config': {'platform': 'linux',
                              'image_resource': {'source': {'repository': C3I_IMAGE},
                                                 'type': 'docker-image'},
                              'inputs': [{'name': 'installer'}],
                              'run': {'path': command, 'args': ['installer/*',
                                                                remote_destination,
                                                                '-i',
                                                                keyfile_path]}}}
    return upload_task


def get_installer_job(platform=PLATFORM, py_ver=PYTHON3, np_ver=NUMPY, bits=BITS,
                      remote_destination=DIR, keyfile_path=DIR,
                      builder='constructor', miniconda=True):
    """Provide a dictionary to be configured by platform specific installers.

    Keyword arguments:
    platform -- the name of the platform: linux, windows, or darwin
    py_ver -- the target python version
    np_ver -- the target numpy version
    bits -- the target architecture: 32 or 64
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    builder -- the builder to use: constructor or ibuild
    miniconda -- boolean value to determine use of Miniconda
    """
    job = {'name': 'installer-{0}-py{1}-np{2}'.format(bits, py_ver, np_ver),
           'public': True,
           'serial': True,
           'plan': [
               {'get': 'recipe_repo_source', 'trigger': True},
               {'task': 'build installer',
                'config': {
                    'platform': platform,
                    'inputs': [
                        {'name': 'recipe-repo-source'}
                    ],
                    'outputs': [
                        {'name': 'installer'}
                    ],
                    'params': {
                        'ANA_LEVEL': str(np_ver).replace('.', '') + str(py_ver).replace('.', ''),
                        'MINICONDA': miniconda,
                        'IGNORE_USER': True,
                        'CONDA_PRIVATE': 0,
                        },
                    'run': {'path': 'sh',
                            'args': ['-exc',
                                     'cwd=$(pwd)\n'
                                     'mkdir aroot\n'
                                     'cd recipe-repo-source\n'
                                     'python setup.py develop\n'
                                     'cd ibuild\n'
                                     'python shar.py\n'
                                     'mv Miniconda*-*.sh ${cwd}/installer\n'
                                    ]
                           }
                    }
               },
            ]
          }

    # add the upload task to the plan key's list to make uploads part of the job
    job['plan'].append(get_upload_task(remote_destination, keyfile_path))

    # when we're on linux, use docker for building the installers
    if platform == 'linux':
        job['plan'][1]['config'].update({'image_resource': {
            'source': {
                'repository': INSTALLER_IMAGE,
                'tag': 'latest'
            },
            'type': 'docker-image',
        }})

    return job


# possibly move this and the osx installer job to argparser
def get_linux_installer_job(py_ver=PYTHON3, np_ver=NUMPY, bits=BITS,
                            remote_destination=DIR, keyfile_path=DIR,
                            builder='constructor', miniconda=True):
    """Retrieve a job installer for the linux platform.

    Keyword arguments:
    py_ver -- the target python version
    np_ver -- the target numpy version
    bits -- the target architecture: 32 or 64
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    builder -- the builder to use: constructor or ibuild
    miniconda -- boolean value to determine use of Miniconda
    """
    return get_installer_job('linux', py_ver, np_ver, bits, remote_destination,
                             keyfile_path, builder, miniconda)


def get_osx_installer_job(py_ver=PYTHON3, np_ver=NUMPY, bits=BITS,
                          remote_destination=DIR, keyfile_path=DIR,
                          builder='constructor', miniconda=True):
    """Retrieve a job installer for the Mac OS platform.

    Keyword arguments:
    py_ver -- the target python version
    np_ver -- the target numpy version
    bits -- the target architecture: 32 or 64
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    builder -- the builder to use: constructor or ibuild
    miniconda -- boolean value to determine use of Miniconda
    """
    return get_installer_job('darwin', py_ver, np_ver, bits, remote_destination,
                             keyfile_path, builder, miniconda)


def get_windows_installer_job(py_ver=PYTHON3, np_ver=NUMPY, bits=BITS,
                              remote_destination=DIR, keyfile_path=DIR,
                              builder='constructor', miniconda=True):
    """Retrieve a job installer for the Windows platform.

    Keyword arguments:
    py_ver -- the target python version
    np_ver -- the target numpy version
    bits -- the target architecture: 32 or 64
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    builder -- the builder to use: constructor or ibuild
    miniconda -- boolean value to determine use of Miniconda
    """
    windows_job = get_installer_job('windows', py_ver, np_ver, bits, remote_destination,
                                    keyfile_path, builder, miniconda)

    windows_job['plan'][1]['config']['run']['args'] = ['-exc',
                                                       'cwd=$(pwd)\n'
                                                       'mkdir aroot\n'
                                                       'cd recipe-repo-source\n'
                                                       'python setup.py develop\n'
                                                       'cd ibuild\n'
                                                       'python winexe.py\n'
                                                       'mv Miniconda*-*.exe ${cwd}/installer\n']
    return windows_job


def create_jobs(path=DIR, platform=PLATFORM, py_ver=PYTHON3, np_ver=NUMPY, bits=BITS,
                remote_destination=DIR, keyfile_path=DIR,
                builder='constructor', miniconda=True):
    """Create a Concourse plan from a conda_build_config.yaml file.

    Keyword arguments:
    path -- the path to the conda_build_config.yaml file
    platform -- the Concourse build platform
    py_ver -- the target python version
    np_ver -- the target numpy version
    bits -- the target architecture: 32 or 64
    remote_destination -- the output path
    keyfile_path -- the path to the keyfile
    builder -- the builder to use: constructor or ibuild
    miniconda -- boolean value to determine use of Miniconda
    """
    builds = get_build_plan(path)
    platform_file = get_platform_file(path)

    if platform_file is not None:
        with open(platform_file) as file:
            platform_config = yaml.safe_load(file)

        platform = platform_config.get('platform', platform)
        bits = platform_config.get('arch', bits)

    plan = {'jobs': []}
    for build in builds:
        py_ver = build.get('python', py_ver)
        np_ver = build.get('numpy', np_ver)

        if platform.startswith('win'):
            job = get_windows_installer_job(py_ver, np_ver, bits, remote_destination,
                                            keyfile_path, builder, miniconda)

        elif platform.startswith('osx') or platform.startswith('mac'):
            job = get_osx_installer_job(py_ver, np_ver, bits, remote_destination,
                                        keyfile_path, builder, miniconda)

        else:
            job = get_linux_installer_job(py_ver, np_ver, bits, remote_destination,
                                          keyfile_path, builder, miniconda)

        plan['jobs'].append(job)

    with open('output.yml', 'w') as output_file:
        yaml.dump(plan, output_file)
