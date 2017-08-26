"""
for the sake of simplicity, all uploads are done with a linux worker, whose capabilities are
well known and understood.  This file is dedicated to helpers to write tasks for that linux
worker

Each function here returns a list of task dictionaries.  This is because some tasks (scp) need
to run additional tasks (for example, to update the index on the remote side)
"""

import logging
import os

from six.moves.urllib import parse
from conda_build import api

from .utils import ensure_list, load_yaml_config_dir

log = logging.getLogger(__file__)


def _base_task(upload_job_name):
    return {'task': upload_job_name,
            'config': {
                'inputs': [{'name': 'output-artifacts'}],
                'image_resource': {
                    'type': 'docker-image',
                    'source': {'repository': 'conda/c3i-linux-64',
                               'tag': 'latest'}},
                'platform': 'linux',
                'run': {}
            }}


def upload_anaconda(package_path, token, user=None, label=None):
    """
    Upload to anaconda.org using a token.  Tokens are associated with a channel, so the channel
    need not be specified.  You may specify a label to install to a label other than main.

    Instructions for generating a token are at:
        https://docs.continuum.io/anaconda-cloud/managing-account#using-tokens

    the task name looks like:

    upload-<task name>-anaconda-<user name or first 4 letters of token if no user provided>
    """
    cmd = ['-t', token, 'upload', '--force']
    identifier = token[-4:]
    if user:
        cmd.extend(['--user', user])
        identifier = user
    if label:
        cmd.extend(['--label', label])
    cmd.append(os.path.join(package_path))
    upload_job_name = 'anaconda-' + identifier
    task = _base_task(upload_job_name)
    task['config']['run'].update({'path': 'anaconda', 'args': cmd})
    return [task]


def upload_scp(package_path, server, destination_path, auth_dict, worker,
               config_vars, port=22):
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
    tasks = []
    identifier = server

    for task in ('scp', 'chmod', 'index'):
        job_name = task + '-' + identifier
        tasks.append(_base_task(job_name))
    key = os.path.join('config', 'uploads.d', auth_dict['key_file'])

    package_path = os.path.join(package_path)
    subdir = "-".join([worker['platform'], str(worker['arch'])])

    server = "{user}@{server}".format(user=auth_dict['user'], server=server)
    destination_path = destination_path.format(subdir=subdir)
    remote = server + ":" + destination_path

    scp_args = ['-i', key, '-P', port, package_path, remote]
    tasks[0]['config']['run'].update({'path': 'scp', 'args': scp_args})
    chmod_args = ['-i', key, '-p', port, server,
        'chmod 664 {0}/{1}'.format(destination_path, os.path.basename(package_path))]
    tasks[1]['config']['run'].update({'path': 'ssh', 'args': chmod_args})
    index_args = ['-i', key, '-p', port, server, 'conda index {0}'.format(destination_path)]
    tasks[2]['config']['run'].update({'path': 'ssh', 'args': index_args})

    return tasks


def upload_commands(package_path, commands, config_vars, **file_contents):
    """Execute arbitrary upload commands.

    Command input strings are expected to have a placeholder for
    the package to upload.  For example:

    commands = ["scp {package} someuser@someserver:somefolder", ]

    Arguments are split by the space character.

    ``package`` is the relative path to the output package, in Concourse terms.
    The contents of the config.yml file are provided in config_vars.  The config files are present
        in the ``config`` relative folder.

    WARNING: abuse of this feature can expose your private keys.  Do not allow any commands that
        expose the contents of your files.
    """

    # first task is to get the config, which includes any private keys in the uploads.d folder
    tasks = []
    package = os.path.join(package_path)
    commands = ensure_list(commands)
    commands = [command.format(package=package, **config_vars) for command in commands]

    for command in commands:
        command = command.split(' ')
        task = _base_task('custom')
        task['config']['run'].update({'path': command[0]})
        if len(command) > 1:
            task['config']['run'].update({'args': command[1:]})
        tasks.append(task)
    return tasks


def get_upload_tasks(graph, node, upload_config_path, config_vars, commit_id, public=True):
    upload_tasks = []
    meta = graph.node[node]['meta']
    worker = graph.node[node]['worker']
    configurations = load_yaml_config_dir(upload_config_path)
    for package in api.get_output_file_paths(meta):
        filename = os.path.basename(package)
        package_path = os.path.join('output-artifacts', commit_id, meta.config.host_subdir,
                                    filename)
        for config in configurations:
            if 'token' in config:
                tasks = upload_anaconda(package_path, **config)
            elif 'server' in config:
                tasks = upload_scp(package_path=package_path,
                                worker=worker, config_vars=config_vars,
                                **config)
            elif 'commands' in config:
                tasks = upload_commands(package_path, config_vars=config_vars,
                                                        **config)
            else:
                raise ValueError("Unrecognized upload configuration.  Each file needs one of: "
                                "'token', 'server', or 'command'")
            upload_tasks.extend(task for task in tasks if task not in upload_tasks)
    return upload_tasks


def get_upload_channels(upload_config_dir, subdir):
    """thought here was to provide whatever channel you have set as an output also to be an input

    Killed this in favor of setting channels in condarc in the docker image.
    """
    configurations = load_yaml_config_dir(upload_config_dir)
    channels = []

    for config in configurations:
        if 'token' in config:
            channels.append(config['user'])
        elif 'server' in config:
            channels.append(parse.urljoin('http://' + config['server'],
                            config['destination_path'].format(subdir=subdir)))
        else:
            channels.append(config['channel'])
    return channels
