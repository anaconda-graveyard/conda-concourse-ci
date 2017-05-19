"""
Purpose of this module is to facilitate generation of plans that build installers

Installers can currently be built with either Constructor, or the Continuum internal build system.
"""

# Docker image.  Probably works for Mac and Linux, but not Windows (needs to run NSIS)
INSTALLER_IMAGE = 'msarahan/installer_builder'
C3I_IMAGE = 'msarahan/conda-concourse-ci'


def get_upload_task(extension):
    pass


def get_unix_installer_job(platform, bits, py_ver, np_ver, remote_destination, keyfile_path,
                            builder='constructor', miniconda=True):
    job = {'name': 'installer-linux-{0}-py{1}-np{2}'.format(bits, py_ver, np_ver),
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
                        }
                    }
                 },
                {'task': 'upload',
                'config': {
                    # upload step is always on linux, so that we know that scp will work.
                    'platform': 'linux',
                    'image_resource': {
                        'source': {
                            'repository': C3I_IMAGE
                        },
                        'type': 'docker-image'
                    },
                    'inputs': [
                        {'name': 'installer'},
                        ],
                    'run': {
                        'path': 'scp',
                        'args': [
                            'installer/*',
                            remote_destination,
                            '-i',
                            keyfile_path,
                            ]
                        }

                    }
                 }
            ]
           }
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

def get_linux_installer_job():
    pass

def get_osx_installer_job(py_ver, np_ver, remote_destination, keyfile_path,
                          builder='constructor', miniconda=True):
    pass
