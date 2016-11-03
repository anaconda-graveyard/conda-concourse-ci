import logging
import os
import subprocess

import paramiko
from paramiko_scp import SCPClient
import six

from .build_matrix import load_platforms

log = logging.getLogger(__file__)


def upload_anaconda(package, token, user=None, label=None):
    """
    Upload to anaconda.org using a token.  Tokens are associated with a channel, so the channel
    need not be specified.  You may specify a label to install to a label other than main.

    Instructions for generating a token are at:
        https://docs.continuum.io/anaconda-cloud/managing-account#using-tokens
    """
    cmd = ['anaconda', '--token', token, 'upload']
    if user:
        cmd.extend(['--user', user])
    if label:
        cmd.extend(['--label', label])
    cmd.append(package)
    subprocess.check_call(cmd)


def upload_scp(package, server, destination_path, port=22, key_var=None, user_password_var=None):
    """
    Upload using scp (using paramiko).  Authentication can be done via key or username/password.

    For key authentication, store your desired private key as text in a secret environment variable
       on Concourse CI.  Provide the name of that variable as the key_var argument here.  A temporary
       in-memory file will be wrtten and fed to paramiko for authentication.

    For user, provide username and password, separated by a colon in a secret environment variable
      on Concourse CI, and provide the name of that variable here.

    This tries to call conda index on the remote side after uploading.  Otherwise, the new
      package would be unavailable.
    """
    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        if user_password_var:
            user, password = os.getenv(user_password_var).split(":")
            ssh.connect(server, port=port, username=user, password=password)
        elif key_var:
            key = six.StringIO(os.getenv(key_var))
            key = paramiko.RSAKey.from_private_key(key)
            ssh.connect(server, pkey=key)
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(package, destination_path)
        if destination_path.endswith(os.path.splitext(package)[1]):
            destination_path = os.path.dirname(destination_path)
        try:
            ssh.exec_command('conda index {0}'.format(destination_path))
        except paramiko.SSHException as e:
            log.warn("Conda index failed on remote end (%s) for %s", server, package)
            log.warn(str(e))


def upload_command(package, command):
    """Execute an arbitrary upload command.  Input string is expected to have a placeholder for
    the package to upload.  For example:

    command = "scp {package} someuser@someserver:somefolder"

    """
    command = command.format(package=package).split()
    subprocess.check_call(command)
