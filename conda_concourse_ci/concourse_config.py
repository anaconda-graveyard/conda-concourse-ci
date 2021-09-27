"""
Classes for representing Concourse pipeline configuration items

These map to the schema's in https://concourse-ci.org/docs.html
"""

import os


CONDA_SUBDIR_TO_CONCOURSE_PLATFORM = {
    'win-64': 'windows',
    'win-32': 'windows',
    'osx-64': 'darwin',
    'linux-64': 'linux',
    'linux-32': 'linux',
    'linux-ppc64le': 'linux-ppc64le'
}


class PipelineConfig:
    """ configuration for a concourse pipeline. """
    # https://concourse-ci.org/pipelines.html
    jobs = []
    resources = []
    resource_types = []
    var_sources = []
    groups = []

    def add_job(self, name, plan=None, **kwargs):
        if plan is None:
            plan = []
        job = {"name": name, "plan": plan, **kwargs}
        self.jobs.append(job)

    def add_resource(self, name, type_, source, **kwargs):
        resource = {'name': name, 'type': type_, "source": source, **kwargs}
        self.resources.append(resource)

    def add_resource_type(self, name, type_, source, **kwargs):
        rtype = {'name': name, 'type': type_, "source": source, **kwargs}
        self.resource_types.append(rtype)

    def to_dict(self):
        out = {}
        attrs = ['jobs', 'resources', 'resource_types', 'var_sources', 'groups']
        for attr in attrs:
            items = getattr(self, attr)
            if not len(items):
                continue
            out[attr] = [v if isinstance(v, dict) else v.to_dict() for v in items]
        return out

    def add_rsync_resource_type(self, docker_user=None, docker_pass=None):
        _source = {
                'repository': 'public.ecr.aws/y0o4y9o3/concourse-rsync-resource',
                'tag': 'latest'
                }

        if docker_user and docker_pass:
            _source.update({'username': docker_user, 'password': docker_pass})

        self.add_resource_type(
            name='rsync-resource',
            type_='docker-image',
            source=_source,
        )

    def add_rsync_recipes(self, config_vars, recipe_folder):
        self.add_resource(
            name='rsync-recipes',
            type_='rsync-resource',
            source={
                'server': config_vars['intermediate-server'],
                'base_dir': recipe_folder,
                'user': config_vars['intermediate-user'],
                'private_key': config_vars['intermediate-private-key-job'],
                'disable_version_path': True,
            },
        )

    def add_rsync_source(self, config_vars):
        self.add_resource(
            name='rsync-source',
            type_='rsync-resource',
            source={
                'server': config_vars['intermediate-server'],
                'base_dir': os.path.join(config_vars['intermediate-base-folder'], 'source'),
                'user': config_vars['intermediate-user'],
                'private_key': config_vars['intermediate-private-key-job'],
                'disable_version_path': True,
            },
        )

    def add_rsync_stats(self, config_vars):
        self.add_resource(
            name='rsync-stats',
            type_='rsync-resource',
            source={
                'server': config_vars['intermediate-server'],
                'base_dir': os.path.join(config_vars['intermediate-base-folder'], 'stats'),
                'user': config_vars['intermediate-user'],
                'private_key': config_vars['intermediate-private-key-job'],
                'disable_version_path': True,
            },
        )

    def add_rsync_build_pack(self, config_vars):
        self.add_resource(
            name='rsync-build-pack',
            type_='rsync-resource',
            source={
                'server': config_vars['intermediate-server'],
                'base_dir': config_vars['build_env_pkgs'],
                'user': config_vars['intermediate-user'],
                'private_key': config_vars['intermediate-private-key-job'],
                'disable_version_path': True,
            },
        )

    def add_rsync_packages(self, resource_name, config_vars):
        source = {
            'server': config_vars['intermediate-server'],
            'base_dir': os.path.join(
                config_vars['intermediate-base-folder'],
                config_vars['base-name'], 'artifacts'),
            'user': config_vars['intermediate-user'],
            'private_key': config_vars['intermediate-private-key-job'],
            'disable_version_path': True,
        }
        self.add_resource(resource_name, 'rsync-resource', source=source)

    def add_anaconda_upload(self, all_rsync, config_vars):
        self.add_jobs(
            name='anaconda_upload',
            plan=all_rsync + [{'put': 'anaconda_upload_resource'}]
        )
        _source = {
                'repository': 'conda/concourse-anaconda_org-resource',
                'tag': 'latest'
                }
        if config_vars.get('docker-user', None) and config_vars.get('docker-pass', None):
            _source.update({'username': config_vars.get('docker-user'),
                            'password': config_vars.get('docker-pass')})
        self.add_resource_type(
            name='anacondaorg-resource',
            type_='docker-image',
            source=_source,
        )
        self.add_resource(
            name='anaconda_upload_resource',
            type_='anacondaorg-resource',
            source={'token': config_vars['anaconda-upload-token']}
        )

    def add_repo_v6_upload(self, all_rsync, config_vars):
        self.add_job(
            name='repo_v6_upload',
            plan=all_rsync + [{'put': 'repo_resource'}]
        )
        _source = {
                'repository': 'condatest/repo_cli',
                'tag': 'latest'}
        if config_vars.get('docker-user', None) and config_vars.get('docker-pass', None):
            _source.update({'username': config_vars.get('docker-user'),
                            'password': config_vars.get('docker-pass')})

        self.add_resource_type(
            name='repo-resource-type',
            type_='docker-image',
            source=_source,
        )
        self.add_resource(
            name='repo_resource',
            type_='repo-resource-type',
            source={
                'token': config_vars['repo-token'],
                'user': config_vars['repo-username'],
                'password': config_vars['repo-password'],
                'channel': config_vars['repo-channel'],
            },
        )

    def add_pr_merged_resource(self, pr_repo, pr_file):
        self.add_resource(
            name="pr-merged",
            type_="git",
            source={
                "uri": pr_repo,
                "branch": "latest",
                "paths": [pr_file],
            },
        )

    def add_upload_job(self, config_vars, commit_msg, pr_merged_resource):
        """ Adds the upload job and a resource (if needed) to the pipeline. """
        plan = []
        if pr_merged_resource:
            plan.append({'get': 'pr-merged', 'trigger': True})
        # add a git resource if specified in the configuration file
        # this resource should be added as an input to the stage-for-upload-config
        # if it is needed in the upload job
        if "stage-for-upload-repo" in config_vars:
            self.add_resource(
                name="stage-packages-scripts",
                type_="git",
                source={
                    "uri": config_vars["stage-for-upload-repo"],
                    "branch": config_vars.get("stage-for-upload-branch", "latest"),
                },
            )
            plan.append({'get': 'stage-packages-scripts', 'trigger': False})

        config = config_vars.get('stage-for-upload-config')
        # add PIPELINE and GIT_COMMIT_MSG to params
        params = config.get('params', {})
        params['PIPELINE'] = config_vars['base-name']
        params['GIT_COMMIT_MSG'] = commit_msg
        config['params'] = params

        plan.append({
            'task': 'stage-packages',
            'trigger': False,
            'config': config,
        })
        self.add_job('stage_for_upload', plan)

    def add_push_branch_job(
            self,
            config_vars,
            folders,
            branches,
            pr_num,
            pr_merged_resource,
            stage_job_name):
        plan = []
        if pr_merged_resource:
            # The branch push causes a version change in the pull-recipes-<branch>
            # resource(s) which causes the artifacts to be removed. To avoid a
            # race condition between these jobs the packages need to be uploaded
            # before pushing branch(es).
            if stage_job_name:
                plan.append({'get': 'pr-merged', 'trigger': True, 'passed': ['stage_for_upload']})
            else:
                plan.append({'get': 'pr-merged', 'trigger': True})
        # resources to add
        if branches is None:
            branches = ['automated-build']
        for n, folder in enumerate(folders):
            if len(branches) == 1:
                branch = branches[0]
            elif len(folders) == len(branches):
                branch = branches[n]
            else:
                raise Exception(
                    "The number of branches either needs to be exactly one or "
                    "equal to the number of feedstocks submitted. Exiting.")

            config = config_vars.get('push-branch-config')
            # add PIPELINE and GIT_COMMIT_MSG to params
            params = config.get('params', {})
            params['BRANCH'] = branch
            params['FEEDSTOCK'] = folder
            params['PR_NUMBER'] = pr_num
            config['params'] = params
            plan.append({
                'task': 'push-branch',
                'trigger': False,
                'config': config,
            })
            self.add_job(f'push_branch_to_{folder}', plan)

    def add_destroy_pipeline_job(self, config_vars, folders):
        """
        Adds a destroy pipeline job to the pipeline.
        """
        passed_jobs = [f'push_branch_to_{folder}' for folder in folders]
        passed_jobs.append('stage_for_upload')
        config = config_vars.get("destroy-pipeline-config")
        params = config.get("params", {})
        params['PIPELINE'] = config_vars['base-name']
        config['params'] = params
        plan = [{
            'get': 'pr-merged',
            'trigger': True,
            'passed': passed_jobs
        }, {
            'task': 'destroy-pipeline',
            'trigger': False,
            'config': config
        }]
        self.add_job('destroy_pipeline', plan)


class JobConfig:
    """ configuration for a concourse job. """
    # https://concourse-ci.org/jobs.html

    def __init__(self, name="placeholder", plan=None):
        self.name = name
        self.plan = plan
        if plan is None:
            self.plan = []

    def to_dict(self):
        return {"name": self.name, "plan": self.plan}

    def add_rsync_recipes(self):
        self.plan.append({
            'get': 'rsync-recipes',
            'trigger': True
        })

    def add_rsync_source(self):
        self.plan.append({
            'put': 'rsync-source',
            'params': {
                'sync_dir': 'output-source',
                'rsync_opts': [
                    "--archive",
                    "--no-perms",
                    "--omit-dir-times",
                    "--verbose",
                    "--exclude",
                    '"*.json*"']
            },
            'get_params': {'skip_download': True}
        })

    def add_rsync_stats(self):
        self.plan.append({
            'put': 'rsync-stats',
            'params': {
                'sync_dir': 'stats',
                'rsync_opts': [
                    "--archive",
                    "--no-perms",
                    "--omit-dir-times",
                    "--verbose"]},
            'get_params': {'skip_download': True}
        })

    def add_rsync_build_pack_win(self):
        self.plan.append({
            'get': 'rsync-build-pack',
            'params': {
                'rsync_opts': [
                    '--include',
                    'loner_conda_windows.exe',
                    '--exclude', '*',
                    '-v'
                ]
            },
        })

    def add_rsync_build_pack_osx(self):
        self.plan.append({
            'get': 'rsync-build-pack',
            'params': {
                'rsync_opts': [
                    '--include',
                    'loner_conda_osx.exe',
                    '--exclude',
                    '*',
                    '-v'
                ]
            }
        })

    def add_rsync_prereq(self, prereq):
        self.plan.append({
            'get': 'rsync_' + prereq,
            'trigger': False,
            'passed': [prereq]}
        )

    def add_put_artifacts(self, resource_name):
        self.plan.append({
            'put': resource_name,
            'params': {
                'sync_dir': 'converted-artifacts',
                'rsync_opts': [
                    "--archive",
                    "--no-perms",
                    "--omit-dir-times",
                    "--verbose",
                    "--exclude", '"**/*.json*"',
                    # html and xml files
                    "--exclude", '"**/*.*ml"',
                    # conda index cache
                    "--exclude", '"**/.cache"',

                ]
            },
            'get_params': {'skip_download': True}
        })

    def add_consolidate_task(self, inputs, subdir, docker_user=None, docker_pass=None):
        _source = {
                    'repository': 'continuumio/anaconda-pkg-build',
                    'tag': 'latest',
                    'username': '((common.dockerhub-user))',
                    'password': '((common.dockerhub-pass))'
                    }
        if docker_user and docker_pass:
            _source.update({
                'username': docker_user,
                'password': docker_pass
                })

        config = {
            # we can always do this on linux, so prefer it for speed.
            'platform': 'linux',
            'image_resource': {
                'type': 'docker-image',
                'source': _source,
            },
            'inputs': [{'name': 'rsync_' + req} for req in inputs],
            'outputs': [{'name': 'indexed-artifacts'}],
            'run': {
                'path': 'sh',
                'args': ['-exc', (
                    'mkdir -p indexed-artifacts/{subdir}\n'
                    'mkdir -p indexed-artifacts/noarch \n'
                    'find . -name "indexed-artifacts" -prune -o -path "*/{subdir}/*.tar.bz2" -print0 | xargs -0 -I file mv file indexed-artifacts/{subdir}\n'  # NOQA
                    'find . -name "indexed-artifacts" -prune -o -path "*/noarch/*.tar.bz2" -print0 | xargs -0 -I file mv file indexed-artifacts/noarch\n'  # NOQA
                    'conda-index indexed-artifacts\n'.format(subdir=subdir))
                    ]
            }
        }
        self.plan.append({'task': 'update-artifact-index', 'config': config})

    def add_convert_task(self, subdir, docker_user=None, docker_pass=None):
        inputs = [{'name': 'output-artifacts'}]
        outputs = [{'name': 'converted-artifacts'}]

        _source = {
                    'repository': 'continuumio/anaconda-pkg-build',
                    'tag': 'latest',
                    'username': '((common.dockerhub-user))',
                    'password': '((common.dockerhub-pass))'
                }
        if docker_user and docker_pass:
            _source.update({
                'username': docker_user,
                'password': docker_pass
                })

        config = {
            # we can always do this on linux, so prefer it for speed.
            'platform': 'linux',
            'inputs': inputs,
            'outputs': outputs,
            'image_resource': {
                'type': 'docker-image',
                'source': _source,
            },
            'run': {
                'path': 'sh',
                'args': [
                    '-exc',
                        'mkdir -p converted-artifacts/{subdir}\n'
                        'mkdir -p converted-artifacts/noarch\n'
                        'find . -name "converted-artifacts" -prune -o -path "*/{subdir}/*.tar.bz2" -print0 | xargs -0 -I file mv file converted-artifacts/{subdir}\n'  # NOQA
                        'find . -name "converted-artifacts" -prune -o -path "*/noarch/*.tar.bz2" -print0 | xargs -0 -I file mv file converted-artifacts/noarch\n'  # NOQA
                'pushd converted-artifacts/{subdir} && cph t "*.tar.bz2" .conda && popd\n'
                'pushd converted-artifacts/noarch && cph t "*.tar.bz2" .conda && popd\n'
                    .format(subdir=subdir)
                    ],
            }
        }
        self.plan.append({'task': 'convert .tar.bz2 to .conda', 'config': config})


class BuildStepConfig:
    """ Class for creating a Concourse step for package build jobs. """

    def __init__(self, test_only, platform, worker_tags):
        self.task_name = 'test' if test_only else 'build'
        self.platform = platform
        self.worker_tags = worker_tags
        self.config = {}
        self.cb_args = []  # list of arguments to pass to conda build
        self.cmds = ''

    def set_config_inputs(self, artifact_input):
        """ Add inputs to the task config. """
        inputs = [{'name': 'rsync-recipes'}]
        if self.platform in ['win', 'osx']:
            inputs.append({'name': 'rsync-build-pack'})
        if artifact_input:
            inputs.append({'name': 'indexed-artifacts'})
        self.config["inputs"] = inputs

    def set_config_outputs(self):
        self.config["outputs"] = [
            {'name': 'output-artifacts'},
            {'name': 'output-source'},
            {'name': 'stats'}
        ]

    def set_config_platform(self, arch):
        subdir = f"{self.platform}-{arch}"
        self.config["platform"] = CONDA_SUBDIR_TO_CONCOURSE_PLATFORM[subdir]

    def set_config_init_run(self):
        if self.platform == 'win':
            self.config["run"] = {'path': 'cmd.exe', 'args': ['/d', '/c']}
        else:
            self.config["run"] = {'path': 'sh', 'args': ['-exc']}

    def set_initial_cb_args(self):
        self.cb_args = [
            '--no-anaconda-upload',
            '--error-overlinking',
            '--error-overdepending',
            '--output-folder=output-artifacts',
            '--cache-dir=output-source',
        ]

    def create_build_cmds(self, build_prefix_cmds, build_suffix_cmds):
        build_cmd = " conda-build " + " ".join(self.cb_args) + " "
        prefix = " ".join(build_prefix_cmds)
        suffix = " ".join(build_suffix_cmds)
        self.cmds = prefix + build_cmd + suffix

    def add_autobuild_cmds(self, recipe_path, cbc_path):
        # combine the recipe from recipe_path with the conda_build_config.yaml
        # file in the cbc_path directory into a combined_recipe directory
        if self.platform == 'win':
            win_cbc_path = cbc_path.replace("/", "\\")
            win_recipe_path = recipe_path.replace("/", "\\")
            # no need to mkdir, xcopy /i creates the directory
            cmd = (
                f"xcopy /i /s /e /f /y {win_recipe_path} combined_recipe&&"
                f"copy /y {win_cbc_path} combined_recipe\\conda_build_config.yaml&&"
                "dir combined_recipe&&"
            )
        else:
            cmd = (
                "mkdir -p combined_recipe && "
                f"cp -r {recipe_path}/* combined_recipe/ && "
                f"cp {cbc_path} combined_recipe/ && "
                "ls -lh combined_recipe/* && "
            )
        self.cmds = cmd + self.cmds

    def add_prefix_cmds(self, prefix_cmds):
        prefix = "&& ".join(prefix_cmds)
        if prefix:
            self.cmds = prefix + "&& " + self.cmds

    def add_repo_access(self, github_user, github_token):
        self.config['params'] = {
            'GITHUB_USER': github_user,
            'GITHUB_TOKEN': github_token,
        }
        if self.platform == 'win':
            creds_cmds = [
                '(echo machine github.com '
                'login %GITHUB_USER% '
                'password %GITHUB_TOKEN% '
                'protocol https > %USERPROFILE%\\_netrc || exit 0)'
            ]
        else:
            creds_cmds = [
                'set +x',
                'echo machine github.com '
                'login $GITHUB_USER '
                'password $GITHUB_TOKEN '
                'protocol https > ~/.netrc',
                'set -x'
            ]
        cmds = "&& ".join(creds_cmds)
        self.cmds = cmds + '&& ' + self.cmds

    def add_suffix_cmds(self, suffix_cmds):
        suffix = "&& ".join(suffix_cmds)
        if suffix:
            self.cmds = self.cmds + "&& " + suffix

    def add_staging_channel_cmd(self, channel):
        # todo: add proper source package path
        path = "*.tar.bz2"
        cmd = f"anaconda upload --skip-existing --force -u {channel} {path}"
        self.cmds += cmd

    def to_dict(self):
        step = {'task': self.task_name, 'config': self.config}
        if self.worker_tags:
            step['tags'] = self.worker_tags
        return step
