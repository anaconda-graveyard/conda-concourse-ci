"""
for the sake of simplicity, all uploads are done with a linux worker, whose capabilities are
well known and understood.  This file is dedicated to helpers to write tasks for that linux
worker

Each function here returns a list of task dictionaries.  This is because some tasks (scp) need
to run additional tasks (for example, to update the index on the remote side)
"""

import json
import logging
import os
# import subprocess

from conda_build.utils import package_has_file
# import paramiko
# from paramiko_scp import SCPClient
# import six

from .build_matrix import load_yaml_config_dir

log = logging.getLogger(__file__)


def _get_package_subdir(package):
    index = json.load(package_has_file(package, 'info/index.json'))
    return index['subdir']


def get_upload_job_name(test_job_name, upload_job_name):
    return test_job_name.replace('test', 'upload') + '-' + upload_job_name


def _base_task(test_job_name, upload_job_name):
    return {'task': upload_job_name,
            'config': {
                'inputs': [{'name': test_job_name}],
                'image_resource': {
                    'type': 'docker-image',
                    'source': {'repository': 'msarahan/conda-concourse-ci'}},
                'platform': 'linux',
                'run': {}
            }}


def upload_anaconda(test_job_name, package_path, token, user=None, label=None):
    """
    Upload to anaconda.org using a token.  Tokens are associated with a channel, so the channel
    need not be specified.  You may specify a label to install to a label other than main.

    Instructions for generating a token are at:
        https://docs.continuum.io/anaconda-cloud/managing-account#using-tokens

    the task name looks like:

    upload-<task name>-anaconda-<user name or first 4 letters of token if no user provided>
    """
    cmd = ['--token', token, '--force', 'upload', os.path.join(test_job_name, package_path)]
    identifier = token[-4:]
    if user:
        cmd.extend(['--user', user])
        identifier = user
    if label:
        cmd.extend(['--label', label])
    upload_job_name = get_upload_job_name(test_job_name, 'anaconda-' + identifier)
    task = _base_task(test_job_name, upload_job_name)
    task['config']['run'].update({'path': 'anaconda', 'args': cmd})
    return [{upload_job_name: task}]


def upload_scp(test_job_name, package_path, server, destination_path, auth_dict, worker, port=22):
    """
    Upload using scp (using paramiko).  Authentication can be done via key or username/password.

    destination_path should have a placeholder for the platform/arch subdir.  For example:

       destination_path = "test-pkgs-someuser/{subdir}"

    auth_dict needs:
        user: the username to log in with
        key_file: the private key to use for the connection.  This key needs to part of your
            config folder, inside your uploads.d folder.

    This tries to call conda index on the remote side after uploading.  Otherwise, the new
      package would be unavailable.
    """
    identifier = server
    tasks = []
    for task in ('scp', 'chmod', 'index'):
        job_name = get_upload_job_name(test_job_name, task + '-' + identifier)
        tasks.append(_base_task(test_job_name, job_name))
    key = os.path.join('config', 'uploads.d', auth_dict['key_file'])

    package_path = os.path.join(test_job_name, package_path)
    subdir = "-".join([worker['platform'], str(worker['arch'])])

    server = "{user}@{server}".format(user=auth_dict['user'], server=server)
    destination_path = destination_path.format(subdir=subdir)
    remote = server + ":" + destination_path

    scp_args = [package_path, remote, '-i', key]
    chmod_args = ['-i', key, server,
        'chmod 664 {0}/{1}'.format(destination_path, os.path.basename(package_path))]
    index_args = ['-i', key, server, 'conda index {0}'.format(destination_path)]

    # scp
    tasks[0]['config']['run'].update({'path': 'scp', 'args': scp_args})
    tasks[0]['config']['outputs'] = [{'name': tasks[0]['task']}]
    # chmod
    tasks[1]['config']['run'].update({'path': 'ssh', 'args': chmod_args})
    tasks[1]['config']['inputs'] = [{'name': tasks[0]['task']}]
    tasks[1]['config']['outputs'] = [{'name': tasks[1]['task']}]
    # index
    tasks[2]['config']['run'].update({'path': 'ssh', 'args': index_args})
    tasks[2]['config']['inputs'] = [{'name': tasks[1]['task']}]
    return [{task['task']: task} for task in tasks]


def upload_command(test_job_name, package_path, command):
    """Execute an arbitrary upload command.  Input string is expected to have a placeholder for
    the package to upload.  For example:

    command = "scp {package} someuser@someserver:somefolder"

    package is the filename of the output package, only.  Subfoldering is handled with the
    test_job_name.
    """
    raise NotImplementedError
    # command = command.format(package=os.path.join(test_job_name, package)).split()
    # # TODO: need to finish this
    # task = _base_task(test_job_name, 'custom')

    # task['config']['run'].update({'path': command[0], 'args': command[1:]})
    # return [task]


def get_upload_tasks(test_job_name, package_path, upload_config_dir, worker):
    tasks = []
    configurations = load_yaml_config_dir(upload_config_dir)

    for config in configurations:
        if 'token' in config:
            tasks.extend(upload_anaconda(test_job_name, package_path, **config))
        elif 'server' in config:
            tasks.extend(upload_scp(test_job_name=test_job_name, package_path=package_path,
                                    worker=worker, **config))
        elif 'command' in config:
            tasks.extend(upload_command(test_job_name, package_path, **config))
        else:
            raise ValueError("Unrecognized upload configuration.  Each file needs one of: "
                             "'token', 'server', or 'command'")
    return tasks
