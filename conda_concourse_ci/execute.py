from __future__ import print_function, division
import contextlib
import logging
import os
import re
import shutil
import subprocess
import tarfile

import boto3
import conda_build.api
from conda_build.conda_interface import Resolve, TemporaryDirectory
from conda_build.index import get_build_index
import networkx as nx
import yaml

from .compute_build_graph import construct_graph, expand_run, order_build, git_changed_recipes
from .uploads import get_upload_tasks, get_upload_channels
from .utils import HashableDict, load_yaml_config_dir

log = logging.getLogger(__file__)
bootstrap_path = os.path.join(os.path.dirname(__file__), 'bootstrap')

# get rid of the special object notation in the yaml file for HashableDict instances that we dump
yaml.add_representer(HashableDict, yaml.representer.SafeRepresenter.represent_dict)


def _s3_resource(s3_name, regexp, config_vars):
    return HashableDict(name=s3_name,
                        type='s3',
                        trigger=True,
                        source=HashableDict(bucket=config_vars['aws-bucket'],
                                            access_key_id=config_vars['aws-key-id'],
                                            secret_access_key=config_vars['aws-secret-key'],
                                            region_name=config_vars['aws-region-name'],
                                            regexp=regexp)
                        )


def _extract_task(base_name, version):
    return {'task': 'extract_archive',
            'config': {
                'inputs': [{'name': 's3-archive'}],
                'outputs': [{'name': 'extracted-archive'}],
                'image_resource': {
                    'type': 'docker-image',
                    'source': {'repository': 'msarahan/conda-concourse-ci'}},
                'platform': 'linux',
                'run': {
                    'path': 'tar',
                    'args': ['-xvf',
                             's3-archive/recipes-{0}-{1}.tar.bz2'.format(base_name, version),
                             '-C', 'extracted-archive']
                        }
                      }
            }


conda_platform_to_concourse_platform = {
    'win': 'windows',
    'osx': 'darwin',
    'linux': 'linux',
}


def parse_platforms(matrix_base_dir, run):
    platform_folder = '{}_platforms.d'.format(run)
    platforms = load_yaml_config_dir(os.path.join(matrix_base_dir, platform_folder))
    log.debug("Platforms found for mode %s:", run)
    log.debug(platforms)
    return platforms


def collect_tasks(path, folders, matrix_base_dir, steps=0, test=False, max_downstream=5):
    runs = ['test']
    upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    # not testing means build and test
    if not test:
        runs.insert(0, 'build')

    task_graph = nx.DiGraph()
    config = conda_build.api.Config()
    for run in runs:
        platforms = parse_platforms(matrix_base_dir, run)
        # loop over platforms here because each platform may have different dependencies
        # each platform will be submitted with a different label
        for platform in platforms:
            index_key = '-'.join([platform['platform'], str(platform['arch'])])
            config.channel_urls = get_upload_channels(upload_config_path, index_key)
            conda_resolve = Resolve(get_build_index(subdir=index_key,
                                                    bldpkgs_dir=config.bldpkgs_dir)[0])
            # this graph is potentially different for platform and for build or test mode ("run")
            g = construct_graph(path, worker=platform, folders=folders, run=run,
                                matrix_base_dir=matrix_base_dir, conda_resolve=conda_resolve)
            # Apply the build label to any nodes that need (re)building or testing
            expand_run(g, conda_resolve=conda_resolve, worker=platform, run=run,
                       steps=steps, max_downstream=max_downstream, recipes_dir=path,
                       matrix_base_dir=matrix_base_dir)
            # merge this graph with the main one
            task_graph = nx.compose(task_graph, g)
    return task_graph


def get_s3_package_regex(base_name, worker, package_name, package_version):
    resource_name = get_s3_resource_name(base_name, worker, package_name, package_version)
    subdir = '-'.join((worker['platform'], str(worker['arch'])))
    return "{resource_name}/{subdir}/{package_name}-{package_version}.tar.bz(.*)".format(
        resource_name=resource_name, subdir=subdir, package_name=package_name,
        package_version=package_version)


def get_s3_resource_name(base_name, worker, package_name, version):
    return "s3-{0}-{1}-{2}-{3}".format(base_name, worker['label'], package_name, version)


def consolidate_packages(path, subdir, **kwargs):
    print("consolidating package resources into 'packages' folder")
    packages_subdir = os.path.join('packages', subdir)
    dest_dir = os.path.join(path, packages_subdir)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith('.tar.bz2') and not root.endswith(packages_subdir):
                log.debug("copying package {0} to packages folder".format(os.path.join(root, f)))
                if os.path.exists(os.path.join(dest_dir, f)):
                    os.remove(os.path.join(dest_dir, f))
                shutil.copyfile(os.path.join(root, f), os.path.join(dest_dir, f))
    conda_build.api.update_index(dest_dir)
    noarch_dir = os.path.join(os.path.dirname(dest_dir), 'noarch')
    if not os.path.exists(noarch_dir):
        os.makedirs(noarch_dir)
    conda_build.api.update_index(noarch_dir)


def consolidate_packages_task(inputs, subdir):
    """Consolidate packages to one location for easier indexing"""
    task_dict = {
        'platform': 'linux',
        'inputs': [{'name': resource} for resource in inputs],
        'outputs': [{'name': 'packages'}],
        'image_resource': {
            'type': 'docker-image',
            'source': {'repository': 'msarahan/conda-concourse-ci'}},
        'run': {
             'path': 'c3i',
             'args': ['consolidate', subdir]
                }
         }
    return {'task': 'consolidate-packages', 'config': task_dict}


def append_consolidate_package_tasks(tasks, graph, node, base_name, resources=None,
                                     append_task=True):
    if not resources:
        resources = []

    # TODO: what to do about empty nodes?
    if graph.node[node]:
        worker = graph.node[node]['worker']
        subdir = "-".join([worker['platform'], str(worker['arch'])])

        # relate this package to dependencies that have been built
        for dep in graph.successors(node):
            # recurse, so that we include dependencies of dependencies also.  Only for test runs.
            #    test runs are our fundamental level of trust of a package, and all test runs
            #    depend on build (or otherwise having the package)
            if dep.startswith('test-'):
                append_consolidate_package_tasks(tasks, graph, dep, base_name, resources=resources,
                                                append_task=False)

            if graph.node[dep]:
                dep_meta = graph.node[dep]['meta']
                worker = graph.node[dep]['worker']
                pkg_version = '{0}-{1}'.format(dep_meta.version(), dep_meta.build_id())
                resource_name = get_s3_resource_name(base_name, worker, dep_meta.name(),
                                                    pkg_version)
                if not any('get' in task and task['get'] == resource_name for task in tasks):
                    tasks.append({'get': resource_name,
                                'trigger': True,
                                'passed': [dep]})
                resources.append(resource_name)
        if append_task:
            tasks.append(consolidate_packages_task(resources, subdir))
    return resources


def add_dependency_edge_tasks(graph, node, base_name):
    worker = graph.node[node]['worker']
    dependency_tasks = []
    for dep in graph.successors(node):
        meta = graph.node[dep]['meta']
        pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
        s3_resource_name = get_s3_resource_name(base_name, worker, meta.name(), pkg_version)
        dependency_tasks.append({'get': s3_resource_name,
                                'trigger': True,
                                'passed': [dep]})
    return dependency_tasks


def deduplicate_get_tasks(tasks):
    """Concourse does not allow tasks with similar names"""
    resources = {}
    other_tasks = []
    for task in tasks:
        resource = task.get('get')
        if resource:
            passed_deps = resources.get(resource, set())
            passed_deps.update(set(task.get('passed', [])))
            resources[resource] = passed_deps
        else:
            other_tasks.append(task)
    return [{'get': resource, 'trigger': True, 'passed': list(deps)}
            for resource, deps in resources.items()] + other_tasks


def get_build_job(base_path, graph, node, base_name, recipe_archive_version, public=True):
    # we append each individual s3 resource in the graph successors loop below
    tasks = [{'get': 's3-archive',
              'trigger': True},
             _extract_task(base_name, recipe_archive_version)]
    tasks.extend(add_dependency_edge_tasks(graph, node, base_name))
    tasks = deduplicate_get_tasks(tasks)

    meta = graph.node[node]['meta']
    recipe_folder_name = meta.meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]

    inputs = [{'name': 'extracted-archive'}, {'name': 'packages'}]

    # mutate tasks in place
    append_consolidate_package_tasks(tasks, graph, node, base_name)

    build_args = ['--no-test', '--no-anaconda-upload', '--output-folder', node,
                  '-c', 'packages']
    recipe_path = os.path.join('extracted-archive', recipe_folder_name)
    for channel in meta.config.channel_urls:
        build_args.extend(['-c', channel])
    # this is the recipe path to build
    build_args.append(recipe_path)

    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        # dependency inputs are down below
        'inputs': inputs,
        'outputs': [{'name': node}, ],
        'run': {
             'path': 'conda-build',
             'args': build_args,
                }
         }

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))

    tasks.append({'task': node, 'config': task_dict})

    pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
    subdir = meta.config.host_subdir
    tasks.append({'put': get_s3_resource_name(base_name, graph.node[node]['worker'],
                                              meta.name(), pkg_version),
                  'params': {'file': os.path.join(node, subdir, '*.tar.bz2')}})

    return {'name': node, 'plan': tasks, 'public': public}


def get_test_recipe_job(base_path, graph, node, base_name, recipe_archive_version, public=True):
    tasks = [{'get': 's3-archive',
              'trigger': 'true'},
             _extract_task(base_name, recipe_archive_version)]
    recipe_folder_name = graph.node[node]['meta'].meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]

    # mutate tasks in place
    append_consolidate_package_tasks(tasks, graph, node, base_name)

    args = ['--test', '-c', 'packages']
    meta = graph.node[node]['meta']
    for channel in meta.config.channel_urls:
        args.extend(['-c', channel])
    args.append(recipe_folder_name)
    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        'inputs': [{'name': 'extracted-archive'}, {'name': 'packages'}],
        'run': {
             'path': 'conda-build',
             'args': args,
             'dir': 'extracted-archive',
                }
         }

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))
    tasks.append({'task': node, 'config': task_dict})

    return {'name': node, 'plan': tasks, 'public': public}


def get_test_package_job(graph, node, base_name, public=True):
    # this is for packages that we build elsewhere in the batch
    meta = graph.node[node]['meta']
    worker = graph.node[node]['worker']
    pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
    s3_resource_name = get_s3_resource_name(base_name, worker, meta.name(), pkg_version)
    tasks = [{'get': s3_resource_name,
              'trigger': True,
              'passed': [node.replace('test', 'build', 1)]}]
    tasks.extend(add_dependency_edge_tasks(graph, node, base_name))
    tasks = deduplicate_get_tasks(tasks)

    inputs = [{'name': s3_resource_name}, {'name': 'packages'}]

    # mutate tasks in place; build up list of resources used
    resources = []
    append_consolidate_package_tasks(tasks, graph, node, base_name, resources)

    for pkg in conda_build.api.get_output_file_paths(meta):
        subdir = os.path.basename(os.path.dirname(pkg))
        filename = os.path.basename(pkg)

        args = ['--test', '-c', 'packages']
        for channel in meta.config.channel_urls:
            args.extend(['-c', channel])
        args.append(os.path.join('packages', subdir, filename))

        task_dict = {
            'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],  # NOQA
            # dependency inputs are down below
            'inputs': inputs,
            'run': {
                'path': 'conda-build',
                'args': args,
                    }
            }
        # this has details on what image or image_resource to use.
        #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
        #   feature right now.
        task_dict.update(graph.node[node]['worker'].get('connector', {}))
        tasks.append({'task': node, 'config': task_dict})

    return {'name': node, 'plan': tasks, 'public': public}


def get_upload_job(graph, node, upload_config_path, config_vars, public=True):
    meta = graph.node[node]['meta']
    worker = graph.node[node]['worker']
    base_name = config_vars['base-name']
    pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
    s3_resource_name = get_s3_resource_name(base_name, worker, meta.name(), pkg_version)
    pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())

    plan = [{'get': s3_resource_name,
             'trigger': True,
             'passed': [node.replace('upload', 'test')]}]

    for package in conda_build.api.get_output_file_paths(meta):
        filename = os.path.basename(package)
        resource_types, resources, tasks = get_upload_tasks(s3_resource_name, filename,
                                                            upload_config_path,
                                                            worker=graph.node[node]['worker'],
                                                            config_vars=config_vars)
        plan.extend(tasks)
    job = {'name': node, 'plan': plan, 'public': public}
    return resource_types, resources, job


def _resource_type_to_dict(resource_type):
    """We use sets and HashableDict to ensure no duplicates of resource types

    These are not nicely yaml-encodable.  We convert them into yaml-friendly containers here.
    """
    out = dict(resource_type)
    out['source'] = dict(out['source'])
    return out


def _resource_to_dict(resource):
    """We use sets and HashableDict to ensure no duplicates of resources.

    These are not nicely yaml-encodable.  We convert them into yaml-friendly containers here.
    """
    out = _resource_type_to_dict(resource)
    if 'options' in out['source']:
        out['source']['options'] = list(out['source']['options'])
    return out


def graph_to_plan_with_jobs(base_path, graph, version, matrix_base_dir, config_vars, public=True):
    jobs = []
    upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    order = order_build(graph)

    resource_types = set()
    config_vars['version'] = version
    resources = set([_s3_resource("s3-archive",
                                  # crappy hack.  s3-resource doesn't allow us to specify version
                                  # to get.  Only latest.  This hack might work.
                                  "recipes-{base-name}-{version}.tar.bz(.*)".format(**config_vars),
                                  config_vars)])

    for node in order:
        meta = graph.node[node]['meta']
        package_name = meta.name()
        worker = graph.node[node]['worker']
        # build jobs need to get the recipes from s3, extract them, and run a build task
        #    same is true for test jobs that do not have a preceding test job.  These use the
        #    recipe for determining which package to download from available channels.
        if node.startswith('build'):
            # need to define an s3 resource for each built package
            pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
            resource = _s3_resource(get_s3_resource_name(config_vars['base-name'],
                                                        worker, package_name, pkg_version),
                                    get_s3_package_regex(config_vars['base-name'],
                                                        worker, package_name, pkg_version),
                                    config_vars=config_vars)
            if resource['name'] not in (r['name'] for r in resources):
                resources.add(resource)
            jobs.append(get_build_job(base_path, graph, node, config_vars['base-name'],
                                    version, public))

        # test jobs need to get the package from either the temporary s3 store or test using the
        #     recipe (download package from available channels) and run a test task

        # TODO: currently tests for things that have no build are broken and skipped

        elif node.startswith('test'):
            if node.replace('test', 'build', 1) in graph.nodes():
                # we build the package in this plan.  Get it from s3.
                jobs.append(get_test_package_job(graph, node, config_vars['base-name'], public))
            else:
                # we are only testing this package in this plan.  Get from configured channels.
                jobs.append(get_test_recipe_job(base_path, graph, node,
                                                config_vars['base-name'], version, public))

        # as far as the graph is concerned, there's only one upload job.  However, this job can
        # represent several upload tasks.  This take the job from the graph, and creates tasks
        # appropriately.
        #
        # This is also more complicated, because uploads may involve other resource types and
        # resources that are not used for build/test.  For example, the scp and commands uploads
        # need to be able to access private keys, which are stored in config uploads.d folder.
        elif node.startswith('upload'):
            upload_resource_types, upload_resources, job = get_upload_job(graph, node,
                                                                        upload_config_path,
                                                                        config_vars, public)
            resource_types.update(upload_resource_types)
            resources.update(upload_resources)
            jobs.append(job)

        else:
            raise NotImplementedError("Don't know how to handle task.  Currently, tasks must "
                                        "start with 'build', 'test', or 'upload'")

    # convert types for smoother output to yaml
    upload_resource_types = [_resource_type_to_dict(t) for t in upload_resource_types]
    resources = [_resource_to_dict(r) for r in resources]

    return {'resource_types': upload_resource_types, 'resources': resources, 'jobs': jobs}


def _get_current_git_rev(path, branch=False):
    out = 'HEAD'
    args = ['git', 'rev-parse']

    if branch:
        args.append("--abbrev-ref")

    args.append('HEAD')

    try:
        out = subprocess.check_output(args, cwd=path).rstrip()
        if hasattr(out, 'decode'):
            out = out.decode()
    except subprocess.CalledProcessError:   # pragma: no cover
        pass   # pragma: no cover
    return out[:8] if not branch else out


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    checkout_ok = False
    try:
        git_current_rev = _get_current_git_rev(path, branch=True)
        subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
        checkout_ok = True
    except subprocess.CalledProcessError:    # pragma: no cover
        log.warn("failed to check out git revision.  "
                 "Source may not be a git repo (that's OK, "
                 "but you need to specify --folders.)")  # pragma: no cover
    yield
    if checkout_ok:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def _archive_recipes(output_folder, recipe_root, base_name, version):
    filename = 'recipes-{0}-{1}.tar.bz2'.format(base_name, version)
    recipe_folders = os.listdir(recipe_root)
    with tarfile.TarFile(filename, 'w') as tar:
        for folder in recipe_folders:
            tar.add(os.path.join(recipe_root, folder), arcname=folder)

    # this move into output is because that's the folder that concourse finds output in
    dest = os.path.join(output_folder, filename)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(filename, dest)


def _upload_to_s3(local_location, remote_location, bucket, key_id, secret_key,
                 region_name='us-west-2'):
    s3 = boto3.resource('s3', aws_access_key_id=key_id,
                        aws_secret_access_key=secret_key,
                        region_name=region_name)  # pragma: no cover

    bucket = s3.Bucket(bucket)  # pragma: no cover
    bucket.upload_file(local_location, remote_location)  # pragma: no cover


def _remove_bucket_folder(folder_name, bucket, key_id, secret_key, region_name='us-west-2'):
    s3 = boto3.resource('s3', aws_access_key_id=key_id,
                        aws_secret_access_key=secret_key,
                        region_name=region_name)

    bucket = s3.Bucket(bucket)  # pragma: no cover
    objects_to_delete = []  # pragma: no cover
    for obj in bucket.objects.filter(Prefix='{}/'.format(folder_name)):  # pragma: no cover
        objects_to_delete.append({'Key': obj.key})  # pragma: no cover
    bucket.delete_objects(Delete={'Objects': objects_to_delete})  # pragma: no cover


def _get_git_identifier(path):
    try:
        # set by pullrequest-resource, but probably doesn't exist locally
        id = 'PR_{0}'.format(subprocess.check_output('git config --get pullrequest.id'.split()))
    except subprocess.CalledProcessError:
        id = _get_current_git_rev(path)
    return id


def submit(pipeline_file, base_name, pipeline_name, src_dir, config_root_dir=None,
           recipe_pkg=None, public=True, **kw):
    """submit task that will monitor changes and trigger other build tasks

    This gets the ball rolling.  Once submitted, you don't need to manually trigger
    builds.  This is creating the task that monitors git changes and triggers regeneration
    of the dynamic job.
    """
    pipeline_name = pipeline_name.format(base_name=base_name,
                                         git_identifier=_get_git_identifier(src_dir))

    config_folder_name = 'config' + ('-' + base_name) if base_name else ""
    if not config_root_dir:
        config_root_dir = os.path.dirname(pipeline_file)
    config_folder = os.path.join(config_root_dir, config_folder_name)
    config_path = os.path.join(config_folder, 'config.yml')
    with open(config_path) as src:
        data = yaml.load(src)

    # TODO: need to be able to upload arbitrary recipe packages and fill in the filename
    #     for these into the plan.  This will facilitate one-off builds that are not computed
    #     by the central facility
    # if not recipe_pkg:
    #     # extract the version from the pipeline file
    #     with open(pipeline_file) as f:
    #         pipeline_data = yaml.load(f)

    #     recipe_pkg = 'recipes-{0}-{1}.tar.bz2'.format(base_name, pipeline_data)
    # _upload_to_s3(recipe_pkg, os.path.basename(recipe_pkg), bucket=data['aws-bucket'],
    #                      key_id=data['aws-key-id'], secret_key=data['aws-secret-key'],
    #                      region_name=data['aws-region-name'])

    for root, dirnames, files in os.walk(config_folder):
        for dirname in dirnames:
            _remove_bucket_folder(os.path.join(config_folder_name, dirname),
                                  bucket=data['aws-bucket'],
                                  key_id=data['aws-key-id'], secret_key=data['aws-secret-key'],
                                  region_name=data['aws-region-name'])

        for f in files:
            local_path = os.path.join(root, f)
            remote_path = local_path.replace(config_folder, 'config-' + base_name)
            _upload_to_s3(local_path, remote_path, bucket=data['aws-bucket'],
                         key_id=data['aws-key-id'], secret_key=data['aws-secret-key'],
                         region_name=data['aws-region-name'])

    # make sure we are logged in to the configured server
    login_args = ['fly', '-t', 'conda-concourse-server', 'login',
                  '--concourse-url', data['concourse-url'],
                  '--team-name', data['concourse-team']]
    if 'concourse-username' in data:
        # auth is optional.  With Github OAuth, there's an interactive prompt that asks
        #   the user to go log in with a web browser.  This should not interfere with that.
        login_args.extend(['--username', data['concourse-username'],
                           '--password', data['concourse-password']])

    subprocess.check_call(login_args)

    # sync (possibly update our client version)
    subprocess.check_call('fly -t conda-concourse-server sync'.split())

    # set the new pipeline details
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'sp',
                           '-c', pipeline_file,
                           '-p', pipeline_name, '-n', '-l', config_path])
    # unpause the pipeline
    subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                           'up', '-p', pipeline_name])

    # trigger the job to actually run
    # subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'tj', '-j',
    #                        '{0}/collect-tasks'.format(pipeline_name)])

    if public:
        subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                               'expose-pipeline', '-p', pipeline_name])


def compute_builds(path, base_name, git_rev, stop_rev=None, folders=None, matrix_base_dir=None,
                   steps=0, max_downstream=5, test=False, public=True, **kw):
    checkout_rev = stop_rev or git_rev
    folders = folders
    path = path.replace('"', '')
    if not folders:
        folders = git_changed_recipes(git_rev, stop_rev, git_root=path)
    if not folders:
        print("No folders specified to build, and nothing changed in git.  Exiting.")
        return
    matrix_base_dir = matrix_base_dir or path
    # clean up quoting from concourse template evaluation
    matrix_base_dir = matrix_base_dir.replace('"', '')

    with checkout_git_rev(checkout_rev, path):
        task_graph = collect_tasks(path, folders=folders, steps=steps,
                                   max_downstream=max_downstream, test=test,
                                   matrix_base_dir=matrix_base_dir)
        try:
            repo_commit = _get_current_git_rev(path)
        except subprocess.CalledProcessError:
            repo_commit = 'master'

    # this file is created and updated by the semver resource
    with open(os.path.join(matrix_base_dir, '..', '..', 'version', 'version')) as f:
        version = f.read().rstrip()
    with open(os.path.join(matrix_base_dir, 'config.yml')) as src:
        data = yaml.load(src)
    data['recipe-repo-commit'] = repo_commit
    data['version'] = version

    plan = graph_to_plan_with_jobs(os.path.abspath(path), task_graph,
                                   version, matrix_base_dir=matrix_base_dir,
                                   config_vars=data, public=public)

    output_folder = '../output'
    try:
        os.makedirs(output_folder)
    except:
        pass
    with open(os.path.join(output_folder, 'plan.yml'), 'w') as f:
        yaml.dump(plan, f, default_flow_style=False)

    # expand folders to include any dependency builds or tests
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
    with TemporaryDirectory() as tmp:
        for node in task_graph:
            if node.split('-')[0] == 'build':
                meta = task_graph.node[node]['meta']
                if meta.meta_path:
                    recipe = os.path.dirname(meta.meta_path)
                else:
                    recipe = meta.get('extra', {}).get('parent_recipe', {})
                assert recipe, ("no parent recipe set, and no path associated "
                                        "with this metadata")
                # make recipe path relative
                recipe = recipe.replace(path + '/', '')
                # copy base recipe into a folder named for this node
                out_folder = os.path.join(tmp, node)
                shutil.copytree(os.path.join(path, recipe), out_folder)
                # write the conda_build_config.yaml for this particular metadata into that recipe
                #   This should sit alongside meta.yaml, where conda-build will be able to find it
                with open(os.path.join(out_folder, 'conda_build_config.yaml'), 'w') as f:
                    yaml.dump(meta.config.variant, f, default_flow_style=False)

        _archive_recipes(output_folder, tmp, base_name, version)


def _copy_yaml_if_not_there(path):
    bootstrap_config_path = os.path.join(bootstrap_path, 'config')
    path_without_config = [p for p in path.split('/') if not p.startswith('config-')]
    original = os.path.join(bootstrap_config_path, *path_without_config)
    try:
        os.makedirs(os.path.dirname(path))
    except:
        pass
    # write config
    if not os.path.isfile(path):
        print("writing new file: ")
        print(path)
        shutil.copyfile(original, path)


def bootstrap(base_name, **kw):
    """Generate template files and folders to help set up CI for a new location"""
    _copy_yaml_if_not_there('config-{0}/config.yml'.format(base_name))
    # this is one that we add the base_name to for future purposes
    with open('config-{0}/config.yml'.format(base_name)) as f:
        config = yaml.load(f)
    config['base-name'] = base_name
    config['config-folder'] = 'config-' + base_name
    config['config-folder-star'] = 'config-' + base_name + '/*'
    config['version-file'] = 'version-' + base_name
    config['execute-job-name'] = 'execute-' + base_name
    # these don't match the download side in the generated execution pipeline.  The download side
    #    has to hack this to fix the version.  For the sake of uploading, this is the right way.
    config['tarball-regex'] = 'recipes-{0}-(.*).tar.bz2'.format(base_name)
    config['tarball-glob'] = 'output/recipes-{0}-*.tar.bz2'.format(base_name)
    config['channels'] = []
    with open('config-{0}/config.yml'.format(base_name), 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    # create platform.d folders
    for run_type in ('build', 'test'):
        if not os.path.exists('config-{0}/{1}_platforms.d'.format(base_name, run_type)):
            _copy_yaml_if_not_there('config-{0}/{1}_platforms.d/example.yml'.format(base_name,
                                                                                    run_type))
    if not os.path.exists('config-{0}/uploads.d'.format(base_name)):
        _copy_yaml_if_not_there('config-{0}/uploads.d/anaconda-example.yml'.format(base_name))
        _copy_yaml_if_not_there('config-{0}/uploads.d/scp-example.yml'.format(base_name))
        _copy_yaml_if_not_there('config-{0}/uploads.d/custom-example.yml'.format(base_name))
    # create initial plan that runs c3i to determine further plans
    #    This one is safe to overwrite, as it is dynamically generated.
    shutil.copyfile(os.path.join(bootstrap_path, 'plan_director.yml'), 'plan_director.yml')
    # advise user on what to edit and how to submit this job
    print("""Greetings, earthling.

    Wrote bootstrap config files into 'config-{0}' folder.

Overview:
    - set your passwords and access keys in config-{0}/config.yml
    - edit target build and test platforms in config-{0}/*_platforms.d.  Note that 'connector' key
      is optional.
    - Finally, submit this configuration with 'c3i submit {0}'
    """.format(base_name))
