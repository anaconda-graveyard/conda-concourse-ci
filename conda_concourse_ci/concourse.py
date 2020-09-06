"""
Classes for representing Concourse pipeline configuration items

These map to the schema's in https://concourse-ci.org/docs.html
"""

import os


class Pipeline:
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

    def add_rsync_resources(self, config_vars, recipe_folder):
        self.add_resource_type(
            name='rsync-resource',
            type_='docker-image',
            source={
                'repository': 'conda/concourse-rsync-resource',
                'tag': 'latest'
            },
        )
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
        self.add_resource_type(
            name='anacondaorg-resource',
            type_='docker-image',
            source={
                'repository': 'conda/concourse-anaconda_org-resource',
                'tag': 'latest'
            },
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
        self.add_resource_type(
            name='repo-resource-type',
            type_='docker-image',
            source={
                'repository': 'condatest/repo_cli',
                'tag': 'latest'},
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


class _DictBacked:
    """ Base class where attributes are stored in the _dict attribute """
    _dict = None

    def _ensure_dict_init(self):
        if self._dict is None:
            self.__dict__["_dict"] = {}

    def __getattr__(self, attr):
        self._ensure_dict_init()
        if attr not in self._dict:
            name = type(self).__name__
            raise AttributeError(f"'{name}' object has no attribute '{attr}'")
        return self._dict[attr]

    def __setattr__(self, attr, value):
        self._ensure_dict_init()
        self._dict[attr] = value

    def to_dict(self):
        return self._dict


class Resource(_DictBacked):
    """ configuration for a concourse resource. """
    # https://concourse-ci.org/resources.html

    def __init__(self, name, type_, source, **kwargs):
        self.name = name
        self.type = type_
        self.source = source
        for attr, value in kwargs.items():
            setattr(self, attr, value)


class ResourceType(_DictBacked):
    """ configuration for a concourse resource type. """
    # https://concourse-ci.org/resource-types.html

    def __init__(self, name, type_, source, **kwargs):
        self.name = name
        self.type = type_
        self.source = source
        for attr, value in kwargs.items():
            setattr(self, attr, value)


class Job():
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

    def add_consolidate_task(self, inputs, subdir):
        config = {
            # we can always do this on linux, so prefer it for speed.
            'platform': 'linux',
            'image_resource': {
                'type': 'docker-image',
                'source': {
                    'repository': 'conda/c3i-linux-64',
                    'tag': 'latest',
                    }
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

    def add_convert_task(self, subdir):
        inputs = [{'name': 'output-artifacts'}]
        outputs = [{'name': 'converted-artifacts'}]
        config = {
            # we can always do this on linux, so prefer it for speed.
            'platform': 'linux',
            'inputs': inputs,
            'outputs': outputs,
            'image_resource': {
                'type': 'docker-image',
                'source': {
                    'repository': 'conda/c3i-linux-64',
                    'tag': 'latest',
                }
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
