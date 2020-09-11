import json
import logging
import subprocess
from contextlib import AbstractContextManager


class Concourse(AbstractContextManager):
    """
    A class for interacting with a Concourse CI instance

    Uses fly for interactions, a compatible version must be installed and on
    path.

    This can be used as a context manager with login/logout. For example:

    with Concourse(url, username, password) as con:
        for pipeline in con.pipelines:
            print(pipeline)

    Parameters
    ----------
    concourse_url : str
        The URL of the Concourse CI server
    username : str, optional
        Concourse username.
    password : str, optional
        Password for user.
    team_name : str, optional
        Team to autheticate with.
    target : str, optional
        Concourse target name

    """

    def __init__(
            self,
            concourse_url,
            username=None,
            password=None,
            team_name=None,
            target='conda-concourse-server'
            ):
        self.concourse_url = concourse_url
        self.username = username
        self.password = password
        self.team_name = team_name
        self.target = target

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *exc_details):
        self.logout()

    def _fly(self, fly_args, check=True):
        """ Run a fly command with the stored target """
        args = ['fly', '-t', self.target] + fly_args
        logging.debug('command: ' + ' '.join(args))
        complete = subprocess.run(args, capture_output=True)
        logging.debug('returncode: ' + str(complete.returncode))
        logging.debug('stdout: ' + complete.stdout.decode('utf-8'))
        logging.debug('stderr: ' + complete.stderr.decode('utf-8'))
        if check:
            complete.check_returncode()
        return complete

    def _flyj(self, fly_args, check=True):
        """ Return the deserialized json output from a fly command. """
        complete = self._fly(fly_args=fly_args + ['--json'], check=check)
        return json.loads(complete.stdout)

    def login(self):
        fly_args = ['login', '--concourse-url', self.concourse_url]
        if self.team_name is not None:
            fly_args.extend(['--team-name', self.team_name])
        if self.username is not None:
            fly_args.extend(['--username', self.username])
        if self.password is not None:
            fly_args.extend(['--password', self.password])
        self._fly(fly_args)

    def logout(self):
        self._fly(["logout"])

    def sync(self):
        self._fly(['sync'])

    def set_pipeline(self, pipeline, config_file, vars_path):
        self._fly([
            "set-pipeline",
            "--pipeline", pipeline,
            "--config", config_file,
            "--load-vars-from", vars_path
        ])

    def unpause_pipeline(self, pipeline):
        self._fly(['unpause-pipeline', '--pipeline', pipeline])

    def expose_pipeline(self, pipeline):
        self._fly(['expose-pipeline', '--pipeline', pipeline])

    def destroy_pipeline(self, pipeline):
        self._fly(['destroy-pipeline', '--pipeline', pipeline])

    @property
    def pipelines(self):
        """ A list of pipelines names """
        return [i['name'] for i in self._flyj(['pipelines'])]

    def get_jobs(self, pipeline):
        return self._flyj(['jobs', '-p', pipeline])

    def get_builds(self, pipeline):
        return self._flyj(['builds', '--pipeline', pipeline])

    def status_of_jobs(self, pipeline):
        statuses = {}
        jobs = self.get_jobs(pipeline)
        for job in jobs:
            name = job.get('name', 'unknown')
            build = job.get('finished_build', None)
            if build:
                status = build.get('status', 'n/a')
            else:
                status = 'n/a'
            statuses[name] = status
        return statuses

    def trigger_job(self, pipeline, job):
        self._fly(['trigger-job', '--job', f'{pipeline}/{job}'])

    def abort_build(self, pipeline, job, name):
        self._fly([
            'abort-build',
            '--job', f'{pipeline}/{job}',
            '--build', name
        ])
