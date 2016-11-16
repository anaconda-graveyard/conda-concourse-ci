"""
for the sake of simplicity, all uploads are done with a linux worker, whose capabilities are
well known and understood.  This file is dedicated to helpers to write tasks for that linux
worker

Each function here returns a list of task dictionaries.  This is because some tasks (scp) need
to run additional tasks (for example, to update the index on the remote side)
"""

import json
import logging
# import os
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


def upload_anaconda(test_job_name, token, user=None, label=None):
    """
    Upload to anaconda.org using a token.  Tokens are associated with a channel, so the channel
    need not be specified.  You may specify a label to install to a label other than main.

    Instructions for generating a token are at:
        https://docs.continuum.io/anaconda-cloud/managing-account#using-tokens
    """
    cmd = ['--token', token, '--force', 'upload']
    identifier = token[-4:]
    if user:
        cmd.extend(['--user', user])
        identifier = user
    if label:
        cmd.extend(['--label', label])
    upload_job_name = get_upload_job_name(test_job_name, 'anaconda-' + identifier)
    task = _base_task(test_job_name, upload_job_name)
    task['config']['run'].update({'path': 'anaconda', 'args': cmd})
    return [{upload_job_name, task}]


def upload_scp(test_job_name, server, destination_path, auth_dict, port=22):
    """
    Upload using scp (using paramiko).  Authentication can be done via key or username/password.

    destination_path should have a placeholder for the platform/arch subdir.  For example:

       destination_path = "test-pkgs-someuser/{subdir}"

    auth_dict needs either:

        key: the private key to use for the connection.  Can be either a path to a file locally, or
            text of the key itself.
        password: optional password for provided key.  If not provided, assumed to be empty.

        user: the username to log in with
        password: the password for the user

    This tries to call conda index on the remote side after uploading.  Otherwise, the new
      package would be unavailable.
    """
    identifier = server
    task = _base_task(test_job_name, 'scp-' + identifier)

    raise NotImplementedError
    # with paramiko.SSHClient() as ssh:
    #     ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    #     if 'user' in auth_dict:
    #         ssh.connect(server, port=port, username=auth_dict['user'],
    #                     password=auth_dict['password'])
    #     elif 'key' in auth_dict:
    #         if os.path.exists(os.path.expanduser(auth_dict['key'])):
    #             key = open(auth_dict['key']).read()
    #         else:
    #             key = auth_dict['key']
    #         key = six.StringIO(key)
    #         key = paramiko.RSAKey.from_private_key(key, password=auth_dict.get('password'))
    #         ssh.connect(server, pkey=key)
    #     else:
    #         raise ValueError("Neither user nor key provided to scp auth_dict.  Aborting.")
    #     with SCPClient(ssh.get_transport()) as scp:
    #         scp.put(package, destination_path)
    #     if destination_path.endswith(os.path.splitext(package)[1]):
    #         destination_path = os.path.dirname(destination_path)

    #     # get package subdir from the package itself, rather than trying to pass it through steps
    #     subdir = _get_package_subdir(package)

    #     try:
    #         ssh.exec_command('conda index {0}'.format(destination_path.format(subdir)))
    #     except paramiko.SSHException as e:
    #         log.warn("Conda index failed on remote end (%s) for %s", server, package)
    #         log.warn(str(e))


def upload_command(package, test_job_name, command):
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


def get_upload_tasks(package_path, upload_config_dir):
    tasks = []
    configurations = load_yaml_config_dir(upload_config_dir)

    for config in configurations:
        if 'token' in config:
            tasks.extend(upload_anaconda(package_path, **config))
        elif 'server' in config:
            tasks.extend(upload_scp(package_path, **config))
        elif 'command' in config:
            tasks.extend(upload_command(package_path, **config))
        else:
            raise ValueError("Unrecognized upload configuration.  Each file needs one of: "
                             "'token', 'server', or 'command'")
    return tasks
