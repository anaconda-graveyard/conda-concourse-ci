from __future__ import print_function, division
from collections import OrderedDict
import contextlib
import glob
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile

import conda_build.api
from conda_build.conda_interface import Resolve, TemporaryDirectory
from conda_build.index import get_build_index
import networkx as nx
import yaml

from .compute_build_graph import (construct_graph, expand_run, order_build, git_changed_recipes,
                                  package_key)
from .utils import HashableDict, load_yaml_config_dir, ensure_list

log = logging.getLogger(__file__)
bootstrap_path = os.path.join(os.path.dirname(__file__), 'bootstrap')

# get rid of the special object notation in the yaml file for HashableDict instances that we dump
yaml.add_representer(HashableDict, yaml.representer.SafeRepresenter.represent_dict)
yaml.add_representer(set, yaml.representer.SafeRepresenter.represent_list)
yaml.add_representer(tuple, yaml.representer.SafeRepresenter.represent_list)


conda_subdir_to_concourse_platform = {
    'win-64': 'windows',
    'win-32': 'windows',
    'osx-64': 'darwin',
    'linux-64': 'linux',
    'linux-32': 'linux',
}


def parse_platforms(matrix_base_dir, run):
    platform_folder = '{}_platforms.d'.format(run)
    platforms = load_yaml_config_dir(os.path.join(matrix_base_dir, platform_folder))
    log.debug("Platforms found for mode %s:", run)
    log.debug(platforms)
    return platforms


def collect_tasks(path, folders, matrix_base_dir, channels=None, steps=0, test=False,
                  max_downstream=5, variant_config_files=None):
    # runs = ['test']
    # not testing means build and test
    # if not test:
    #     runs.insert(0, 'build')
    runs = ['build']

    task_graph = nx.DiGraph()
    config = conda_build.api.Config()
    for run in runs:
        platforms = parse_platforms(matrix_base_dir, run)
        # loop over platforms here because each platform may have different dependencies
        # each platform will be submitted with a different label
        for platform in platforms:
            index_key = '-'.join([platform['platform'], str(platform['arch'])])
            config.channel_urls = channels or []
            config.variant_config_files = variant_config_files or []
            conda_resolve = Resolve(get_build_index(subdir=index_key,
                                                    bldpkgs_dir=config.bldpkgs_dir)[0])
            # this graph is potentially different for platform and for build or test mode ("run")
            g = construct_graph(path, worker=platform, folders=folders, run=run,
                                matrix_base_dir=matrix_base_dir, conda_resolve=conda_resolve,
                                config=config)
            # Apply the build label to any nodes that need (re)building or testing
            expand_run(g, conda_resolve=conda_resolve, worker=platform, run=run,
                       steps=steps, max_downstream=max_downstream, recipes_dir=path,
                       matrix_base_dir=matrix_base_dir)
            # merge this graph with the main one
            task_graph = nx.compose(task_graph, g)
    return task_graph


def consolidate_task(inputs, subdir):
    task_dict = {
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
            'args': ['-exc',
                    ('mkdir -p indexed-artifacts/{subdir}\n'
                     'mkdir -p indexed-artifacts/noarch \n'
                     'find . -name "indexed-artifacts" -prune -o -path "*/{subdir}/*.tar.bz2" -print0 | xargs -0 -I file mv file indexed-artifacts/{subdir}\n'  # NOQA
                     'find . -name "indexed-artifacts" -prune -o -path "*/noarch/*.tar.bz2" -print0 | xargs -0 -I file mv file indexed-artifacts/noarch\n'  # NOQA
                     'conda-index indexed-artifacts/{subdir}\n'
                     'conda-index indexed-artifacts/noarch\n'.format(subdir=subdir))]
        }}
    return {'task': 'update-artifact-index', 'config': task_dict}


def get_build_task(base_path, graph, node, base_name, commit_id, public=True, artifact_input=False):
    meta = graph.node[node]['meta']
    build_args = ['--no-anaconda-upload', '--output-folder', 'output-artifacts',
                  '--cache-dir', 'output-source']
    inputs = [{'name': 'rsync-recipes'}]
    worker = graph.node[node]['worker']
    for channel in meta.config.channel_urls:
        build_args.extend(['-c', channel])
    if artifact_input:
        inputs.append({'name': 'indexed-artifacts'})
        build_args.extend(('-c', os.path.join('indexed-artifacts')))
    subdir = '-'.join((worker['platform'], str(worker['arch'])))

    task_dict = {
        'platform': conda_subdir_to_concourse_platform[subdir],
        # dependency inputs are down below
        'inputs': inputs,
        'outputs': [{'name': 'output-artifacts'}, {'name': 'output-source'}],
        'run': {}}

    if worker['platform'] == 'win':
        task_dict['run'].update({'path': 'cmd.exe', 'args': ['/c']})
        build_args.extend(['--croot', 'C:\\ci'])
    else:
        task_dict['run'].update({'path': 'sh', 'args': ['-exc']})
        build_args.extend(['--croot', '.'])

    # this is the recipe path to build
    build_args.append(os.path.join('rsync-recipes', node))

    build_prefix_commands = " ".join(ensure_list(worker.get('build_prefix_commands')))
    build_suffix_commands = " ".join(ensure_list(worker.get('build_suffix_commands')))

    cmds = 'hostname && conda update -y conda-build && conda info && ' + \
           build_prefix_commands + ' conda-build ' + " ".join(build_args) + \
           ' ' + build_suffix_commands
    prefix_commands = " && ".join(ensure_list(worker.get('prefix_commands')))
    suffix_commands = " && ".join(ensure_list(worker.get('suffix_commands')))
    if prefix_commands:
        cmds = prefix_commands + ' && ' + cmds
    if suffix_commands:
        cmds = cmds + ' && ' + suffix_commands

    task_dict['run']['args'].append(cmds)

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))
    return {'task': 'build', 'config': task_dict}


def get_test_recipe_task(base_path, graph, node, base_name, commit_id, public=True):
    recipe_folder_name = graph.node[node]['meta'].meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]

    args = ['--test']
    meta = graph.node[node]['meta']
    worker = graph.node[node]['worker']
    subdir = '-'.join((worker['platform'], str(worker['arch'])))
    for channel in meta.config.channel_urls:
        args.extend(['-c', channel])
    args.append(recipe_folder_name)
    task_dict = {
        'platform': conda_subdir_to_concourse_platform[subdir],
        'inputs': [{'name': 'rsync-recipes'}],
        'run': {'dir': os.path.join('rsync-recipes', commit_id)}
         }

    prefix_commands = " && ".join(ensure_list(worker.get('prefix_commands')))
    suffix_commands = " && ".join(ensure_list(worker.get('suffix_commands')))

    cmds = 'hostname && conda info && conda-build ' + " ".join(args)

    if prefix_commands:
        cmds = prefix_commands + ' && ' + cmds
    if suffix_commands:
        cmds = cmds + ' && ' + suffix_commands

    if worker['platform'] == 'win':
        task_dict['run'].update({'path': 'cmd.exe', 'args': ['/c', cmds]})
    else:
        task_dict['run'].update({'path': 'sh', 'args': ['-exc', cmds]})

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(worker.get('connector', {}))
    return {'task': node, 'config': task_dict}


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


def graph_to_plan_with_jobs(base_path, graph, commit_id, matrix_base_dir, config_vars, public=True):
    jobs = OrderedDict()
    # upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    order = order_build(graph)

    resource_types = [{'name': 'rsync-resource',
                       'type': 'docker-image',
                       'source': {
                           'repository': 'msarahan/concourse-rsync-resource',
                           'tag': 'latest'
                           }
                       }]
    base_folder = os.path.join(config_vars['intermediate-base-folder'], config_vars['base-name'])
    recipe_folder = os.path.join(base_folder, 'plan_and_recipes')
    artifact_folder = os.path.join(base_folder, 'artifacts')
    if commit_id:
        recipe_folder = os.path.join(recipe_folder, commit_id)
        artifact_folder = os.path.join(artifact_folder, commit_id)
    resources = [{'name': 'rsync-recipes',
                  'type': 'rsync-resource',
                  'source': {
                      'server': config_vars['intermediate-server'],
                      'base_dir': recipe_folder,
                      'user': config_vars['intermediate-user'],
                      'private_key': config_vars['intermediate-private-key'],
                      'disable_version_path': True,
                  }},
                 {'name': 'rsync-source',
                  'type': 'rsync-resource',
                      'source': {
                      'server': config_vars['intermediate-server'],
                      'base_dir': os.path.join(config_vars['intermediate-base-folder'], 'source'),
                      'user': config_vars['intermediate-user'],
                      'private_key': config_vars['intermediate-private-key'],
                      'disable_version_path': True,
                  }}]

    rsync_resources = []

    # each package is a unit in the concourse graph.  This step recombines our separate steps.

    for node in order:
        pkgs = tuple(conda_build.api.get_output_file_paths(graph.node[node]['meta']))
        meta = graph.node[node]['meta']
        worker = graph.node[node]['worker']
        resource_name = 'rsync_' + node
        rsync_resources.append(resource_name)

        resources.append(
            {'name': resource_name,
             'type': 'rsync-resource',
             'source': {
                 'server': config_vars['intermediate-server'],
                 'base_dir': os.path.join(config_vars['intermediate-base-folder'],
                                          config_vars['base-name'], 'artifacts'),
                 'user': config_vars['intermediate-user'],
                 'private_key': config_vars['intermediate-private-key'],
                 'disable_version_path': True,
             }})

        tasks = jobs.get(pkgs, {}).get('tasks',
                                [{'get': 'rsync-recipes', 'trigger': True}])

        prereqs = set(graph.successors(node))
        for prereq in prereqs:
            tasks.append({'get': 'rsync_' + prereq,
                            'trigger': False,
                            'passed': [prereq]})

        if prereqs:
            tasks.append(consolidate_task(prereqs, meta.config.host_subdir))
        tasks.append(get_build_task(base_path, graph, node, config_vars['base-name'],
                                    commit_id, public, artifact_input=bool(prereqs)))
        tasks.append({'put': resource_name,
                      'params': {'sync_dir': 'output-artifacts',
                                 'rsync_opts': ["--archive", "--no-perms",
                                                "--omit-dir-times", "--verbose",
                                                "--exclude", '"*.json*"']},
                      'get_params': {'skip_download': True}})

        # as far as the graph is concerned, there's only one upload job.  However, this job can
        # represent several upload tasks.  This take the job from the graph, and creates tasks
        # appropriately.
        #
        # This is also more complicated, because uploads may involve other resource types and
        # resources that are not used for build/test.  For example, the scp and commands uploads
        # need to be able to access private keys, which are stored in config uploads.d folder.
        # elif node.startswith('upload'):
        #     pass
        #     # tasks.extend(get_upload_tasks(graph, node, upload_config_path, config_vars,
        #     #                               commit_id=commit_id, public=public))
        # else:
        #     raise NotImplementedError("Don't know how to handle task.  Currently, tasks must "
        #                                 "start with 'build', 'test', or 'upload'")
        jobs[pkgs] = {'tasks': tasks, 'meta': meta, 'worker': worker}
    remapped_jobs = []
    for plan_dict in jobs.values():
        # name = _get_successor_condensed_job_name(graph, plan_dict['meta'])
        name = package_key(plan_dict['meta'], plan_dict['worker']['label'])
        plan_dict['tasks'].append({'put': 'rsync-source',
                                   'params': {'sync_dir': 'output-source',
                                              'rsync_opts': ["--archive", "--no-perms",
                                                             "--omit-dir-times", "--verbose",
                                                             "--exclude", '"*.json*"']},
                                   'get_params': {'skip_download': True}})
        remapped_jobs.append({'name': name, 'plan': plan_dict['tasks']})

    if config_vars.get('anaconda-upload-token'):
        remapped_jobs.append({'name': 'anaconda_upload',
                              'plan': [{'get': 'rsync_' + node, 'trigger': True, 'passed': [node]}
                                       for node in order] + [{'put': 'anaconda_upload_resource'}]})
        resource_types.append({'name': 'anacondaorg-resource',
                       'type': 'docker-image',
                       'source': {
                           'repository': 'msarahan/concourse-anaconda_org-resource',
                           'tag': 'latest'
                           }
                       })
        resources.append({'name': 'anaconda_upload_resource',
                  'type': 'anacondaorg-resource',
                      'source': {
                      'token': config_vars['anaconda-upload-token'],
                  }})

    # convert types for smoother output to yaml
    return {'resource_types': resource_types, 'resources': resources, 'jobs': remapped_jobs}


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


def submit(pipeline_file, base_name, pipeline_name, src_dir, config_root_dir,
           public=True, config_overrides=None, **kw):
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
        data = yaml.load(src)

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
        subprocess.check_call(['rsync', '--delete', '-av', '-e',
                               'ssh -o UserKnownHostsFile=/dev/null '
                               '-o StrictHostKeyChecking=no -i ' + key_file,
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
    os.remove(key_file)

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

    if public:
        subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                               'expose-pipeline', '-p', pipeline_name])


def compute_builds(path, base_name, git_rev=None, stop_rev=None, folders=None, matrix_base_dir=None,
                   steps=0, max_downstream=5, test=False, public=True, output_dir='../output',
                   output_folder_label='git', config_overrides=None, **kw):
    if not git_rev and not folders:
        raise ValueError("Either git_rev or folders list are required to know what to compute")
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

    repo_commit = ''
    git_identifier = ''
    if checkout_rev:
        with checkout_git_rev(checkout_rev, path):
            git_identifier = _get_current_git_rev(path)
            task_graph = collect_tasks(path, folders=folders, steps=steps,
                                       max_downstream=max_downstream, test=test,
                                       matrix_base_dir=matrix_base_dir,
                                       channels=kw.get('channel', []),
                                       variant_config_files=kw.get('variant_config_files', []))
            try:
                repo_commit = _get_current_git_rev(path)
            except subprocess.CalledProcessError:
                repo_commit = 'master'
    else:
        task_graph = collect_tasks(path, folders=folders, steps=steps,
                                   max_downstream=max_downstream, test=test,
                                   matrix_base_dir=matrix_base_dir,
                                   channels=kw.get('channel', []),
                                   variant_config_files=kw.get('variant_config_files', []))

    with open(os.path.join(matrix_base_dir, 'config.yml')) as src:
        data = yaml.load(src)
    data['recipe-repo-commit'] = repo_commit

    if config_overrides:
        data.update(config_overrides)

    plan = graph_to_plan_with_jobs(os.path.abspath(path), task_graph,
                                commit_id=repo_commit, matrix_base_dir=matrix_base_dir,
                                config_vars=data, public=public)

    output_dir = output_dir.format(base_name=base_name, git_identifier=git_identifier)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    with open(os.path.join(output_dir, 'plan.yml'), 'w') as f:
        yaml.dump(plan, f, default_flow_style=False)

    # expand folders to include any dependency builds or tests
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
    for fn in glob.glob(os.path.join(output_dir, 'output_order*')):
        os.remove(fn)
    last_recipe_dir = None
    for node in nx.topological_sort(task_graph, reverse=True):
        meta = task_graph.node[node]['meta']
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
        order_fn = 'output_order_' + task_graph.node[node]['worker']['label']
        with open(os.path.join(output_dir, order_fn), 'a') as f:
            f.write(node + '\n')
        recipe_dir = os.path.dirname(recipe) if os.sep in recipe else recipe
        if not last_recipe_dir or last_recipe_dir != recipe_dir:
            order_recipes_fn = 'output_order_recipes_' + task_graph.node[node]['worker']['label']
            with open(os.path.join(output_dir, order_recipes_fn), 'a') as f:
                f.write(recipe_dir + '\n')
            last_recipe_dir = recipe_dir


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


def bootstrap(base_name, **kw):
    """Generate template files and folders to help set up CI for a new location"""
    _copy_yaml_if_not_there('{0}/config.yml'.format(base_name), base_name)
    # this is one that we add the base_name to for future purposes
    with open('{0}/config.yml'.format(base_name)) as f:
        config = yaml.load(f)
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


def submit_one_off(pipeline_label, recipe_root_dir, folders, config_root_dir, **kwargs):
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
    ctx = (contextlib.contextmanager(lambda: (yield kwargs.get('output_dir'))) if
           kwargs.get('output_dir') else TemporaryDirectory)
    with ctx() as tmpdir:
        kwargs['output_dir'] = tmpdir
        compute_builds(path=recipe_root_dir, base_name=pipeline_label, folders=folders,
                       matrix_base_dir=config_root_dir, config_overrides=config_overrides,
                       **kwargs)
        submit(pipeline_file=os.path.join(tmpdir, 'plan.yml'), base_name=pipeline_label,
               pipeline_name=pipeline_label, src_dir=tmpdir, config_root_dir=config_root_dir,
               config_overrides=config_overrides, **kwargs)
