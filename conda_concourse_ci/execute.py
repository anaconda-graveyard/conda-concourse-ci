from __future__ import division, print_function

import contextlib
import glob
import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time

from collections import defaultdict
from fnmatch import fnmatch

import conda_build.api
from conda_build.conda_interface import Resolve, TemporaryDirectory, cc_conda_build
from conda_build.index import get_build_index
from conda_build.variants import get_package_variants

import networkx as nx

import requests

import yaml

from .compute_build_graph import (construct_graph, expand_run, git_changed_recipes, order_build,
                                  package_key)
from .concourse import Pipeline, Job, BuildStep
from .utils import HashableDict, ensure_list, load_yaml_config_dir

log = logging.getLogger(__file__)
bootstrap_path = os.path.join(os.path.dirname(__file__), 'bootstrap')

try:
    input = raw_input
except NameError:
    pass

# get rid of the special object notation in the yaml file for HashableDict instances that we dump
yaml.add_representer(HashableDict, yaml.representer.SafeRepresenter.represent_dict)
yaml.add_representer(set, yaml.representer.SafeRepresenter.represent_list)
yaml.add_representer(tuple, yaml.representer.SafeRepresenter.represent_list)


def parse_platforms(matrix_base_dir, run, platform_filters):
    platform_folder = '{}_platforms.d'.format(run)
    platforms = load_yaml_config_dir(os.path.join(matrix_base_dir, platform_folder),
                                     platform_filters)
    log.debug("Platforms found for mode %s:", run)
    log.debug(platforms)
    return platforms


def _parse_python_numpy_from_pass_throughs(pass_through_list):
    parsed = {}
    iterator = iter(ensure_list(pass_through_list))
    while True:
        try:
            args = next(iterator).lstrip("--").split("=")
            if args[0] in ("python", "numpy", "perl", "R", "lua"):
                if len(args) > 1:
                    value = args[1]
                else:
                    value = next(iterator)
                parsed[args[0]] = value
        except StopIteration:
            break

    return parsed


def collect_tasks(path, folders, matrix_base_dir, channels=None, steps=0, test=False,
                  max_downstream=5, variant_config_files=None, platform_filters=None,
                  clobber_sections_file=None, append_sections_file=None, pass_throughs=None,
                  skip_existing=True):
    # runs = ['test']
    # not testing means build and test
    # if not test:
    #     runs.insert(0, 'build')
    runs = ['build']

    task_graph = nx.DiGraph()
    parsed_cli_args = _parse_python_numpy_from_pass_throughs(pass_throughs)
    config = conda_build.api.Config(clobber_sections_file=clobber_sections_file,
                                    append_sections_file=append_sections_file,
                                    skip_existing=skip_existing, **parsed_cli_args)
    platform_filters = ensure_list(platform_filters) if platform_filters else ['*']
    for run in runs:
        platforms = parse_platforms(matrix_base_dir, run, platform_filters)
        # loop over platforms here because each platform may have different dependencies
        # each platform will be submitted with a different label

        for platform in platforms:
            index_key = '-'.join([platform['platform'], str(platform['arch'])])
            config.variants = get_package_variants(path, config, platform.get('variants'))
            config.channel_urls = channels or []
            config.variant_config_files = variant_config_files or []
            conda_resolve = Resolve(get_build_index(subdir=index_key,
                                                    bldpkgs_dir=config.bldpkgs_dir, channel_urls=channels)[0])
            # this graph is potentially different for platform and for build or test mode ("run")
            g = construct_graph(path, worker=platform, folders=folders, run=run,
                                matrix_base_dir=matrix_base_dir, conda_resolve=conda_resolve,
                                config=config)
            # Apply the build label to any nodes that need (re)building or testing
            expand_run(g, config=config.copy(), conda_resolve=conda_resolve, worker=platform,
                       run=run, steps=steps, max_downstream=max_downstream, recipes_dir=path,
                       matrix_base_dir=matrix_base_dir)
            # merge this graph with the main one
            task_graph = nx.compose(task_graph, g)
    collapse_noarch_python_nodes(task_graph)
    return task_graph


def collapse_noarch_python_nodes(graph):
    """ Collapse nodes for noarch python packages into a single node

    Collapse nodes corresponding to any noarch python packages so that each package
    in built on a single platform and test on the remaining platforms.  Edges are
    reassinged or removed as needed.
    """
    # TODO make build_subdir configurable
    build_subdir = 'linux-64'

    # find all noarch python builds, group by package name
    noarch_groups = defaultdict(list)
    for node in graph.nodes():
        if graph.nodes[node].get('noarch_pkg', False):
            pkg_name = graph.nodes[node]['meta'].name()
            noarch_groups[pkg_name].append(node)

    for pkg_name, nodes in noarch_groups.items():
        # split into build and test nodes
        build_nodes = []
        test_nodes = []
        for node in nodes:
            if graph.nodes[node]['meta'].config.subdir == build_subdir:
                build_nodes.append(node)
            else:
                test_nodes.append(node)
        if len(build_nodes) > 1:
            log.warn('more than one noarch python build for %s' % (pkg_name))
        if len(build_nodes) == 0:
            raise ValueError(
                'The %s platform has no noarch python build for %s' % (build_subdir, pkg_name))
        build_node = build_nodes[0]

        for test_node in test_nodes:
            # reassign any dependencies on the test_only node to the build node
            for edge in tuple(graph.in_edges(test_node)):
                new_edge = edge[0], build_node
                graph.add_edge(*new_edge)
                graph.remove_edge(*edge)
            # remove all test_only node dependencies
            for edge in tuple(graph.out_edges(test_node)):
                graph.remove_edge(*edge)
            # add a test only node
            metadata = graph.nodes[test_node]['meta']
            worker = graph.nodes[test_node]['worker']
            name = 'test-' + test_node
            graph.add_node(name, meta=metadata, worker=worker, test_only=True)
            graph.add_edge(name, build_node)
            # remove the test_only node
            graph.remove_node(test_node)
    return


def get_build_task(
        node,
        meta,
        worker,
        artifact_input=False,
        worker_tags=None,
        config_vars={},
        pass_throughs=None,
        test_only=False,
        use_repo_access=False,
        use_staging_channel=False):

    worker_tags = (ensure_list(worker_tags) +
                   ensure_list(meta.meta.get('extra', {}).get('worker_tags')))
    step = BuildStep(test_only, worker['platform'], worker_tags)

    # setup the task config
    step.set_config_platform(worker['arch'])
    step.set_config_inputs(artifact_input)
    step.set_config_outputs()
    step.set_config_init_run()

    # build up the arguments to pass to conda build
    step.set_initial_cb_args()
    stats_file = os.path.join('stats', f"{node}_{int(time.time())}.json")
    step.cb_args.append(f'--stats-file={stats_file}')
    if test_only:
        step.cb_args.append('--test')
    for channel in meta.config.channel_urls:
        step.cb_args.extend(['-c', channel])
    if artifact_input:
        step.cb_args.extend(('-c', os.path.join('indexed-artifacts')))
    if step.platform == 'win':
        step.cb_args.extend(['--croot', 'C:\\ci'])
    else:
        step.cb_args.extend(['--croot', '.'])
    # these are any arguments passed to c3i that c3i doesn't recognize
    step.cb_args.extend(ensure_list(pass_throughs))
    # this is the recipe path to build
    step.cb_args.append(os.path.join('rsync-recipes', node))
    if use_staging_channel:
        channel = config_vars.get('staging-channel-user', 'staging')
        step.cb_args.extend(['-c', channel])

    # create the commands to run in the task
    cb_prefix_cmds = ensure_list(worker.get("build_prefix_commands"))
    cb_suffix_cmds = ensure_list(worker.get("build_suffix_commands"))
    step.create_build_cmds(cb_prefix_cmds, cb_suffix_cmds)
    step.add_prefix_cmds(ensure_list(worker.get('prefix_commands')))
    if use_repo_access:
        github_user = config_vars.get('recipe-repo-access-user', None)
        github_token = config_vars.get('recipe-repo-access-token', None)
        if github_user and github_token:
            step.add_repo_access(github_user, github_token)
    step.add_suffix_cmds(ensure_list(worker.get('suffix_commands')))
    if use_staging_channel:
        channel = config_vars.get('staging-channel-user', 'staging')
        step.add_staging_channel_cmd(channel)
    step.config['run']['args'].append(step.cmds)

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    step.config.update(worker.get('connector', {}))

    return step.to_dict()


def graph_to_plan_with_jobs(
        base_path, graph, commit_id, matrix_base_dir, config_vars,
        public=True, worker_tags=None, pass_throughs=None,
        use_repo_access=False, use_staging_channel=False,
        automated_pipeline=False, branches=None, folders=None,
        pr_num=None, repository=None):
    # upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    order = order_build(graph)
    if graph.number_of_nodes() == 0:
        raise Exception(
            "Build graph is empty. The default behaviour is to skip existing builds."
        )

    base_folder = os.path.join(config_vars['intermediate-base-folder'], config_vars['base-name'])
    recipe_folder = os.path.join(base_folder, 'plan_and_recipes')
    artifact_folder = os.path.join(base_folder, 'artifacts')
    status_folder = os.path.join(base_folder, 'status')
    if commit_id:
        recipe_folder = os.path.join(recipe_folder, commit_id)
        artifact_folder = os.path.join(artifact_folder, commit_id)
        status_folder = os.path.join(status_folder, commit_id)

    pipeline = Pipeline()
    pipeline.add_rsync_resources(config_vars, recipe_folder)
    if any(graph.nodes[node]['worker']['platform'] in ["win", "osx"] for node in order):
        pipeline.add_rsync_build_pack(config_vars)

    for node in order:
        meta = graph.nodes[node]['meta']
        worker = graph.nodes[node]['worker']
        test_only = graph.nodes[node].get('test_only', False)
        rsync_artifacts = worker.get("rsync") in [None, True]
        name = package_key(meta, worker['label'])
        if test_only:
            name = 'test-' + name
        job = Job(name=name)
        job.add_rsync_recipes()
        if worker['platform'] == "win":
            job.add_rsync_build_pack_win()
        elif worker['platform'] == "osx":
            job.add_rsync_build_pack_osx()
        prereqs = set(graph.successors(node))
        for prereq in prereqs:
            if rsync_artifacts:
                job.add_rsync_prereq(prereq)
        if prereqs:
            job.add_consolidate_task(prereqs, meta.config.host_subdir)
        job.plan.append(get_build_task(
            node, meta, worker,
            artifact_input=bool(prereqs),
            worker_tags=worker_tags,
            config_vars=config_vars,
            pass_throughs=pass_throughs,
            test_only=test_only,
            use_repo_access=use_repo_access,
            use_staging_channel=use_staging_channel
        ))
        if not test_only:
            job.add_convert_task(meta.config.host_subdir)
            resource_name = 'rsync_' + node
            job.add_put_artifacts(resource_name)
            pipeline.add_rsync_packages(resource_name, config_vars)
        if rsync_artifacts:
            job.add_rsync_source()
            job.add_rsync_stats()
        pipeline.add_job(**job.to_dict())

    if config_vars.get('anaconda-upload-token') or config_vars.get('repo-username'):
        all_rsync = [
            {'get': 'rsync_' + node, 'trigger': True, 'passed': [node]}
            for node in order if
            graph.nodes[node]['worker'].get("rsync") is None or
            graph.nodes[node]['worker'].get("rsync") is True]
        if config_vars.get('anaconda-upload-token'):
            pipeline.add_anaconda_upload(all_rsync, config_vars)
        if config_vars.get('repo-username'):
            pipeline.add_repo_v6_upload(all_rsync, config_vars)

    if automated_pipeline:
        # build the automated pipeline
        build_automated_pipeline(pipeline, folders, order, branches, pr_num, repository, config_vars)

    # convert types for smoother output to yaml
    return pipeline


def build_automated_pipeline(pline, folders, order, branches, pr_num, repository, config_vars):
    # TODO adjust to use pipeline rather than pline or incorperate into earlier function
    # resources to add
    if branches is None:
        branches = ['automated-build']
    for n, folder in enumerate(folders):
        if len(branches) == 1:
            branch = branches[0]
        elif len(folders) == len(branches):
            branch = branches[n]
        else:
            raise Exception("The number of branches either needs to be exactly one or equal to the number of feedstocks submitted. Exiting.")

        pull_recipes = {
            'name': 'pull-recipes-{0}'.format(folder.rsplit('-', 1)[0]),
            'type': 'git',
            'source': {
                'branch': branch,
                'uri': 'https://github.com/AnacondaRecipes/{0}.git'.format(folder)
            },
        }
        pline.resources.append(pull_recipes)

    for n, resource in enumerate(pline.resources):
        if resource.get('name') == 'rsync-recipes' and not any(i.startswith('test-') for i in order):
            del(pline.resources[n])

    for job in pline.jobs:
        if job.get('name') in order:
            for num, plan in enumerate(job.get('plan')):
                if plan.get('get') == 'rsync-recipes' and not job.get('name').startswith('test-'):
                    for folder in folders:
                        if job.get('name').startswith(folder.rsplit('-', 1)[0]):
                            plan.update({'get': 'pull-recipes-{0}'.format(folder.rsplit('-', 1)[0])})
                if plan.get('task', '') == 'build':
                    command = plan.get('config').get('run').get('args')[-1]
                    clean_feedstock_linux = 'for i in `ls pull-recipes*`; do if [[ $i != "recipe" ]]; then rm -rf $i; fi done && '
                    # TODO fix this
                    # clean_feedstock_win = 'pushd %cd%\pull-recipes* for /D %%D in ("*") do (if /I not "%%~nxD"=="recipe") for %%F in ("*") do (del "%%~F") popd'
                    import re
                    # replace the old rsync dir with the new one
                    command = re.sub(r'rsync-recipes/([a-zA-Z\d\D+]*\ )', 'pull-recipes*/ ', command)
                    print(job.get("name"))
                    if "winbuilder" in job.get("name"):
                        # command = clean_feedstock_win + command
                        command = command
                    else:
                        command = clean_feedstock_linux + command
                    plan.get('config').get('run').get('args')[-1] = command
                    inputs = plan.get('config').get('inputs')
                    for folder in folders:
                        if job.get('name').startswith(folder.rsplit('-', 1)[0]):
                            inputs.append({'name': 'pull-recipes-{0}'.format(folder.rsplit('-', 1)[0])})
                    plan['config']['inputs'] = inputs
                    for n, i in enumerate(plan.get('config').get('inputs')):
                        if i.get('name') == 'rsync-recipes':
                            del(plan['config']['inputs'][n])
                if plan.get('task', '') == 'test':
                    for resource in plan.resources:
                        if resource.get('name').startswith('rsync_{}'.format(folders[0].split('-')[0])) and 'canary' not in resource.get('name'):
                            plan.get('config').get('inputs').append({'name': resource.get('name')})

    return


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


def _ensure_login_and_sync(config_root_dir):
    """Make sure end user is logged in and has a compatible version of the fly
    utility. This function should be called before executing other fly commands
    which require authentication.
    """

    config_path = os.path.expanduser(os.path.join(config_root_dir, 'config.yml'))
    with open(config_path) as src:
        data = yaml.safe_load(src)

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


def _filter_existing_pipelines(pipeline_patterns):
    """Iterate over the list of existing pipelines and filter out those which
    match any pattern in the given list (passed as an argument to this
    function). This function can be called before performing bulk operations on
    pipelines.
    """

    existing_pipelines = subprocess.check_output('fly -t conda-concourse-server ps'.split())
    if hasattr(existing_pipelines, 'decode'):
        existing_pipelines = existing_pipelines.decode()
    existing_pipelines = [line.split()[0] for line in existing_pipelines.splitlines()[1:]]

    filtered_pipelines = []
    for pattern in ensure_list(pipeline_patterns):
        filtered_pipelines.extend([p for p in existing_pipelines if fnmatch(p, pattern)])

    return filtered_pipelines


def submit(pipeline_file, base_name, pipeline_name, src_dir, config_root_dir,
           public=True, config_overrides=None, pass_throughs=None, **kw):
    """submit task that will monitor changes and trigger other build tasks

    This gets the ball rolling.  Once submitted, you don't need to manually trigger
    builds.  This is creating the task that monitors git changes and triggers regeneration
    of the dynamic job.
    """
    git_identifier = _get_current_git_rev(src_dir) if config_overrides else None
    pipeline_name = pipeline_name.format(base_name=base_name,
                                         git_identifier=git_identifier)
    pipeline_file = pipeline_file.format(git_identifier=git_identifier)

    config_path = os.path.join(config_root_dir, 'config.yml')
    with open(config_path) as src:
        data = yaml.safe_load(src)

    if config_overrides:
        data.update(config_overrides)

    key_handle, key_file = tempfile.mkstemp()
    key_handle = os.fdopen(key_handle, 'w')
    key_handle.write(data['intermediate-private-key'])
    key_handle.close()
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    # this is a plan director job.  Sync config.
    if not config_overrides:
        subprocess.check_call(['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                        '-o', 'StrictHostKeyChecking=no', '-i', key_file,
                        '{intermediate-user}@{intermediate-server}'.format(**data),
                        'mkdir -p {intermediate-base-folder}/{base-name}/config'.format(**data)])
        subprocess.check_call(['rsync', '--delete', '-av', '-e',
                               'ssh -o UserKnownHostsFile=/dev/null '
                               '-o StrictHostKeyChecking=no -i ' + key_file,
                               config_root_dir + '/',
                               ('{intermediate-user}@{intermediate-server}:'
                                '{intermediate-base-folder}/{base-name}/config'.format(**data))
                               ])
    # this is a one-off job.  Sync the recipes we've computed locally.
    else:
        subprocess.check_call(['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                        '-o', 'StrictHostKeyChecking=no', '-i', key_file,
                        '{intermediate-user}@{intermediate-server}'.format(**data),
                        'mkdir -p {intermediate-base-folder}/{base-name}'.format(**data)])
        # create the PR file
        if kw.get('pr_num', None):
            with open(f"{src_dir}/pr_num", 'w') as pr_file:
                pr_file.write(kw.get('pr_num'))

        subprocess.check_call(['rsync', '--delete', '-av', '-e',
                               'ssh -o UserKnownHostsFile=/dev/null '
                               '-o StrictHostKeyChecking=no -i ' + key_file,
                               '-p', '--chmod=a=rwx',
                               src_dir + '/',
                               ('{intermediate-user}@{intermediate-server}:'
                                '{intermediate-base-folder}/{base-name}/plan_and_recipes'
                                .format(**data))
                               ])
        # remove any existing artifacts for sanity's sake - artifacts are only from this build.
        subprocess.check_call(['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                        '-o', 'StrictHostKeyChecking=no', '-i', key_file,
                        '{intermediate-user}@{intermediate-server}'.format(**data),
                        'rm -rf {intermediate-base-folder}/{base-name}/artifacts'.format(**data)])
        # create the status dir
        subprocess.check_call(['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                        '-o', 'StrictHostKeyChecking=no', '-i', key_file,
                        '{intermediate-user}@{intermediate-server}'.format(**data),
                        'mkdir -p {intermediate-base-folder}/{base-name}/status'.format(**data)])
    os.remove(key_file)

    _ensure_login_and_sync(config_root_dir)

    # set the new pipeline details
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'sp',
                           '-c', pipeline_file,
                           '-p', pipeline_name, '-n', '-l', config_path])
    # unpause the pipeline
    subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                           'up', '-p', pipeline_name])

    if public:
        subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                               'expose-pipeline', '-p', pipeline_name])


def compute_builds(path, base_name, folders, matrix_base_dir=None,
                   steps=0, max_downstream=5, test=False, public=True, output_dir='../output',
                   output_folder_label='git', config_overrides=None, platform_filters=None,
                   worker_tags=None, clobber_sections_file=None, append_sections_file=None,
                   pass_throughs=None, skip_existing=True,
                   use_repo_access=False, use_staging_channel=False, **kw):
    if kw.get('stage_for_upload', False):
        if kw.get('commit_msg') is None:
            raise ValueError(
                "--stage-for-upload requires --commit-msg to be specified")
    if kw.get('destroy_pipeline', False):
        if not kw.get('stage_for_upload', False) or not kw.get('push_branch', False):
            raise ValueError(
                    "--destroy-pipeline requires that --push-branch "
                    "and stage-for-upload be specified as well.")
    folders = folders
    path = path.replace('"', '')
    if not folders:
        print("No folders specified to build, and nothing changed in git.  Exiting.")
        return
    matrix_base_dir = os.path.expanduser(matrix_base_dir or path)
    # clean up quoting from concourse template evaluation
    matrix_base_dir = matrix_base_dir.replace('"', '')

    append_sections_file = append_sections_file or cc_conda_build.get('append_sections_file')
    clobber_sections_file = clobber_sections_file or cc_conda_build.get('clobber_sections_file')

    repo_commit = ''
    git_identifier = ''
    task_graph = collect_tasks(path, folders=folders, steps=steps,
                                max_downstream=max_downstream, test=test,
                                matrix_base_dir=matrix_base_dir,
                                channels=kw.get('channel', []),
                                variant_config_files=kw.get('variant_config_files', []),
                                platform_filters=platform_filters,
                                append_sections_file=append_sections_file,
                                clobber_sections_file=clobber_sections_file,
                                pass_throughs=pass_throughs, skip_existing=skip_existing)

    with open(os.path.join(matrix_base_dir, 'config.yml')) as src:
        config_vars = yaml.safe_load(src)
    config_vars['recipe-repo-commit'] = repo_commit

    if config_overrides:
        config_vars.update(config_overrides)

    pipeline = graph_to_plan_with_jobs(
        os.path.abspath(path),
        task_graph,
        commit_id=repo_commit,
        matrix_base_dir=matrix_base_dir,
        config_vars=config_vars,
        public=public,
        worker_tags=worker_tags,
        pass_throughs=pass_throughs,
        use_repo_access=use_repo_access,
        use_staging_channel=use_staging_channel,
        automated_pipeline=kw.get("automated_pipeline", False),
        branches=kw.get("branches", None),
        pr_num=kw.get("pr_num", None),
        repository=kw.get("repository", None),
        folders=folders
    )

    if kw.get('pr_file'):
        pr_merged_resource = "pr-merged"  # TODO actually a name
        pipeline.add_pr_merged_resource(config_vars['pr-repo'], kw.get("pr_file"))
    else:
        pr_merged_resource = None

    if kw.get('stage_for_upload', False):
        # TODO move this
        if 'stage-for-upload-config' not in config_vars:
            raise Exception(
                ("--stage-for-upload specified but configuration file contains "
                "to 'stage-for-upload-config entry"))
        pipeline.add_upload_job(config_vars, kw['commit_msg'], pr_merged_resource)

    if kw.get('push_branch', False):
        # TODO move this
        if 'push-branch-config' not in config_vars:
            raise Exception(
                ("--push-branch specified but configuration file contains "
                "to 'push-branch-config entry"))
        if kw.get('stage_for_upload', False):
            stage_job_name = 'stage_for_upload'
        else:
            stage_job_name = None
        pipeline.add_push_branch_job(
            config_vars, folders, kw['branches'], pr_merged_resource, stage_job_name)
    if kw.get('destroy_pipeline', False):
        # TODO move this
        if 'destroy-pipeline-config' not in config_vars:
            raise Exception(
                "--destroy-pipeline specified but configuration file does not "
                "have that entry."
                    )
        pipeline.add_destroy_pipeline_job(config_vars, folders)
    output_dir = output_dir.format(base_name=base_name, git_identifier=git_identifier)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    with open(os.path.join(output_dir, 'plan.yml'), 'w') as f:
        yaml.dump(pipeline.to_dict(), f, default_flow_style=False)

    # expand folders to include any dependency builds or tests
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
    for fn in glob.glob(os.path.join(output_dir, 'output_order*')):
        os.remove(fn)
    last_recipe_dir = None
    nodes = list(nx.topological_sort(task_graph))
    nodes.reverse()
    for node in nodes:
        meta = task_graph.nodes[node]['meta']
        if meta.meta_path:
            recipe = os.path.dirname(meta.meta_path)
        else:
            recipe = meta.meta.get('extra', {}).get('parent_recipe', {}).get('path', '')
        assert recipe, ("no parent recipe set, and no path associated "
                                "with this metadata")
        # make recipe path relative
        recipe = recipe.replace(path + '/', '')
        # copy base recipe into a folder named for this node
        out_folder = os.path.join(output_dir, node)
        if os.path.isdir(out_folder):
            shutil.rmtree(out_folder)

        shutil.copytree(os.path.join(path, recipe), out_folder)
        # write the conda_build_config.yml for this particular metadata into that recipe
        #   This should sit alongside meta.yaml, where conda-build will be able to find it
        with open(os.path.join(out_folder, 'conda_build_config.yaml'), 'w') as f:
            yaml.dump(meta.config.squished_variants, f, default_flow_style=False)

        # copy any clobber or append file that is specified either on CLI or via condarc
        if clobber_sections_file:
            shutil.copyfile(clobber_sections_file, os.path.join(out_folder, 'recipe_clobber.yaml'))

        if append_sections_file:
            shutil.copyfile(append_sections_file, os.path.join(out_folder, 'recipe_append.yaml'))

        order_fn = 'output_order_' + task_graph.nodes[node]['worker']['label']
        with open(os.path.join(output_dir, order_fn), 'a') as f:
            f.write(node + '\n')
        recipe_dir = os.path.dirname(recipe) if os.sep in recipe else recipe
        if not last_recipe_dir or last_recipe_dir != recipe_dir:
            order_recipes_fn = 'output_order_recipes_' + task_graph.nodes[node]['worker']['label']
            with open(os.path.join(output_dir, order_recipes_fn), 'a') as f:
                f.write(recipe_dir + '\n')
            last_recipe_dir = recipe_dir

    # clean up recipe_log.txt so that we don't leave a dirty git state
    for node in nodes:
        meta = task_graph.nodes[node]['meta']
        if meta.meta_path:
            recipe = os.path.dirname(meta.meta_path)
        else:
            recipe = meta.meta.get('extra', {}).get('parent_recipe', {}).get('path', '')
        if os.path.isfile(os.path.join(recipe, 'recipe_log.json')):
            os.remove(os.path.join(recipe, 'recipe_log.json'))
        if os.path.isfile(os.path.join(recipe, 'recipe_log.txt')):
            os.remove(os.path.join(recipe, 'recipe_log.txt'))


def _copy_yaml_if_not_there(path, base_name):
    """For aribtrarily nested yaml files, check if they exist in the destination bootstrap
    dir. If not, copy them there from our central install.

    path looks something like:
    my_config_folder/config/config.yml
    """
    bootstrap_config_path = os.path.join(bootstrap_path, 'config')
    path_without_config = []
    for p in reversed(path.split('/')):
        if p != base_name:
            path_without_config.append(p)
        else:
            break
    original = os.path.join(bootstrap_config_path, *reversed(path_without_config))
    try:
        os.makedirs(os.path.dirname(path))
    except OSError:
        pass
    # write config
    if not os.path.isfile(path):
        print("writing new file: ")
        print(path)
        shutil.copyfile(original, path)


def bootstrap(base_name, pass_throughs=None, **kw):
    """Generate template files and folders to help set up CI for a new location"""
    _copy_yaml_if_not_there('{0}/config.yml'.format(base_name), base_name)
    # this is one that we add the base_name to for future purposes
    with open('{0}/config.yml'.format(base_name)) as f:
        config = yaml.safe_load(f)
    config['base-name'] = base_name
    config['intermediate-base-folder'] = '/ci'
    config['execute-job-name'] = 'execute-' + base_name
    with open('{0}/config.yml'.format(base_name), 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    # create platform.d folders
    for run_type in ('build', 'test'):
        if not os.path.exists('{0}/{1}_platforms.d'.format(base_name, run_type)):
            _copy_yaml_if_not_there('{0}/{1}_platforms.d/example.yml'.format(base_name,
                                                                             run_type), base_name)
    if not os.path.exists('{0}/uploads.d'.format(base_name)):
        _copy_yaml_if_not_there('{0}/uploads.d/anaconda-example.yml'.format(base_name), base_name)
        _copy_yaml_if_not_there('{0}/uploads.d/scp-example.yml'.format(base_name), base_name)
        _copy_yaml_if_not_there('{0}/uploads.d/custom-example.yml'.format(base_name), base_name)
    # create initial plan that runs c3i to determine further plans
    #    This one is safe to overwrite, as it is dynamically generated.
    shutil.copyfile(os.path.join(bootstrap_path, 'plan_director.yml'), 'plan_director.yml')
    # advise user on what to edit and how to submit this job
    print(""" Wrote bootstrap config files into '{0}' folder.

Overview:
    - set your passwords and access keys in {0}/config.yml
    - edit target build and test platforms in {0}/*_platforms.d.  Note that 'connector' key
      is optional.
    - Finally, submit this configuration with 'c3i submit {0}'
    """.format(base_name))


def submit_one_off(pipeline_label, recipe_root_dir, folders, config_root_dir, pass_throughs=None,
                   **kwargs):
    """A 'one-off' job is a submission of local recipes that use the concourse build workers.

    Submitting one of these involves a few steps:
        1. actual build recipes are computed locally (as opposed to on the concourse host
           with plan directors)
        2. rsync those to a remote location based on the config_root, but with the base_name
           replaced with the pipeline_label here
        3. clear out the remote base_name/artifacts folder, to remove previous builds with the same
           name
        4. submit the generated plan created by step 1
    """

    # the intermediate paths are set up for the configuration name.  With one-offs, we're ignoring
    #    the configuration's tie to a github repo.  What we should do is replace the base_name in
    #    the configuration locations with our pipeline label
    config_overrides = {'base-name': pipeline_label}
    config_root_dir = os.path.expanduser(config_root_dir)
    ctx = (contextlib.contextmanager(lambda: (yield kwargs.get('output_dir'))) if
           kwargs.get('output_dir') else TemporaryDirectory)
    with ctx() as tmpdir:
        kwargs['output_dir'] = tmpdir
        compute_builds(path=recipe_root_dir, base_name=pipeline_label, folders=folders,
                       matrix_base_dir=config_root_dir, config_overrides=config_overrides,
                       pass_throughs=pass_throughs, **kwargs)
        if kwargs.get("dry_run", False):
            print("!!! Dry run, pipeline not submitted to concourse")
            print(f"!!! Prepared plans and recipes stored in {tmpdir}")
        else:
            submit(pipeline_file=os.path.join(tmpdir, 'plan.yml'), base_name=pipeline_label,
                pipeline_name=pipeline_label, src_dir=tmpdir, config_root_dir=config_root_dir,
                config_overrides=config_overrides, pass_throughs=pass_throughs, **kwargs)


def submit_batch(
        batch_file, recipe_root_dir, config_root_dir,
        max_builds, poll_time, build_lookback, label_prefix,
        pass_throughs=None, **kwargs):
    """
    Submit a batch of 'one-off' jobs with controlled submission based on the
    number of running builds.
    """
    with open(batch_file) as f:
        batch_lines = sorted([line for line in f])
        batch_items = [BatchItem(line) for line in batch_lines]

    _ensure_login_and_sync(config_root_dir)

    config_path = os.path.expanduser(os.path.join(config_root_dir, 'config.yml'))
    with open(config_path) as src:
        data = yaml.safe_load(src)

    concourse_url = data['concourse-url']

    success = []
    failed = []
    while len(batch_items):
        num_activate_builds = _get_activate_builds(concourse_url, build_lookback)
        if num_activate_builds < max_builds:
            # use a try/except block here so a single failed one-off does not
            # break the batch
            try:
                batch_item = batch_items.pop(0)
                print("Starting build for:", batch_item)

                pipeline_label = batch_item.get_label(label_prefix)
                extra = kwargs.copy()
                extra.update(batch_item.item_kwargs)
                submit_one_off(pipeline_label, recipe_root_dir, batch_item.folders,
                               config_root_dir, pass_throughs=pass_throughs, **extra)
                print("Success", batch_item)
                success.append(batch_item)
            except Exception as e:
                print("Fail", batch_item)
                print("Exception was:", e)
                failed.append(batch_item)
        else:
            print("Too many active builds:", num_activate_builds)
        time.sleep(poll_time)

    print("one-off jobs submitted:", len(success))
    if len(failed):
        print("one-off jobs which failed to submit:", len(failed))
        print("details:")
        for item in failed:
            print(item)


class BatchItem(object):

    def __init__(self, line):
        if ';' in line:
            folders_str, extra_str = line.split(';', 2)
            extra_str = extra_str.strip()
        else:
            folders_str = line
            extra_str = ''

        if len(extra_str):
            item_kwargs = dict(i.split('=') for i in extra_str.split(','))
        else:
            item_kwargs = {}
        self.folders = folders_str.split()
        self.item_kwargs = item_kwargs

    def get_label(self, prefix):
        return prefix + self.folders[0].rsplit('-', 1)[0]

    def __str__(self):
        return ' '.join(self.folders)


def _get_activate_builds(concourse_url, limit):
    """ Return the number of active builds on the server. """
    url = requests.compat.urljoin(concourse_url, 'api/v1/builds')
    r = requests.get(url, params={'limit': limit})
    all_items = r.json()
    if len(all_items) < 5:
        raise ValueError("Something wrong")
    running = [i for i in all_items if i['status'] == 'started']
    return len(running)


def rm_pipeline(pipeline_names, config_root_dir, do_it_dammit=False, pass_throughs=None, **kwargs):
    _ensure_login_and_sync(config_root_dir)

    pipelines_to_remove = _filter_existing_pipelines(pipeline_names)

    print("Removing pipelines:")
    for p in pipelines_to_remove:
        print(p)
    if not do_it_dammit:
        confirmation = input("Confirm [y]/n: ") or 'y'
    else:
        print("YOLO! removing all listed pipelines")

    if do_it_dammit or confirmation == 'y':
        # make sure we have aborted all pipelines and their jobs ...
        abort_pipeline(pipelines_to_remove, config_root_dir)
        # remove the specified pipelines
        for pipeline_name in pipelines_to_remove:
            subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                                'dp', '-np', pipeline_name])
    else:
        print("aborted")


def trigger_pipeline(pipeline_names, config_root_dir, trigger_all=False,
                     pass_throughs=None, **kwargs):
    _ensure_login_and_sync(config_root_dir)

    pipelines_to_trigger = _filter_existing_pipelines(pipeline_names)

    print("Triggering jobs:")
    for pipeline in pipelines_to_trigger:
        pipeline_jobs = subprocess.check_output(['fly', '-t', 'conda-concourse-server',
                                                 'jobs', '--json', '-p', pipeline])
        if hasattr(pipeline_jobs, 'decode'):
            pipeline_jobs = pipeline_jobs.decode()
        jobs_to_trigger = []
        for job in json.loads(pipeline_jobs):
            if trigger_all:
                jobs_to_trigger.append(job["name"])
            elif not job["next_build"]:  # next build has not been triggered yet
                if ((not job["finished_build"]) or  # has never been triggered
                    (job["finished_build"]["status"] !=
                     "succeeded")):  # last trigger resulted in failure
                    jobs_to_trigger.append(job["name"])
        for job in jobs_to_trigger:
            job_fqdn = "{}/{}".format(pipeline, job)
            print(job_fqdn)
            subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                                   'trigger-job', '-j', job_fqdn])


def abort_pipeline(pipeline_names, config_root_dir, pass_throughs=None, **kwargs):
    _ensure_login_and_sync(config_root_dir)

    pipelines_to_abort = _filter_existing_pipelines(pipeline_names)

    print("Aborting pipelines:")
    for pipeline in pipelines_to_abort:
        pipeline_jobs = subprocess.check_output(['fly', '-t', 'conda-concourse-server',
                                                 'builds', '--json', '-p', pipeline])
        if hasattr(pipeline_jobs, 'decode'):
            pipeline_jobs = pipeline_jobs.decode()
        jobs_to_abort = []
        for job in json.loads(pipeline_jobs):
            if job["status"] == "started":
                jobs_to_abort.append(job)
        for job in jobs_to_abort:
            job_fqdn = "{}/{}".format(pipeline, job["job_name"])
            print(job_fqdn)
            subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                                   'abort-build', '-j', job_fqdn, '-b', job["name"]])
