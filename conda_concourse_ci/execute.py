from __future__ import print_function, division
import contextlib
import logging
import os
import re
import shutil
import subprocess
import tempfile

import conda_build.api
from conda_build.conda_interface import Resolve
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


def get_build_job(base_path, graph, node, base_name, commit_id, public=True):
    tasks = [{'get': 'rsync-intermediary',
              'trigger': True,
              'passed': list(graph.successors(node))}]
    meta = graph.node[node]['meta']
    output_path = os.path.join('rsync-intermediary', commit_id, 'artifacts')
    # TODO: use git rev info to determine the folder where artifacts should go
    build_args = ['--no-test', '--no-anaconda-upload', '--output-folder', output_path,
                  '-c', os.path.join('rsync-intermediary', commit_id, 'artifacts')]
    for channel in meta.config.channel_urls:
        build_args.extend(['-c', channel])
    # this is the recipe path to build
    build_args.append(os.path.join('rsync-intermediary', commit_id, 'recipes', node))

    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        # dependency inputs are down below
        'inputs': [{'name': 'rsync-intermediary'}],
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
    tasks.append({'put': 'rsync-intermediary'})

    # do not store empty sets for passed reqs
    if not tasks[0]['passed']:
        del tasks[0]['passed']

    return {'name': node, 'plan': tasks, 'public': public}


def get_test_recipe_job(base_path, graph, node, base_name, commit_id, public=True):
    tasks = [{'get': 'rsync-intermediary',
              'trigger': True,
              'passed': list(graph.successors(node))}]
    recipe_folder_name = graph.node[node]['meta'].meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]

    args = ['--test']
    meta = graph.node[node]['meta']
    for channel in meta.config.channel_urls:
        args.extend(['-c', channel])
    args.append(recipe_folder_name)
    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        'inputs': [{'name': 'rsync-intermediary'}],
        'run': {
             'path': 'conda-build',
             'args': args,
             'dir': os.path.join('rsync-intermediary', commit_id, 'recipes'),
                }
         }

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))
    tasks.append({'task': node, 'config': task_dict})

    return {'name': node, 'plan': tasks, 'public': public}


def get_test_package_job(graph, node, base_name, commit_id, public=True):
    """this is for packages that we build elsewhere in the batch"""
    tasks = [{'get': 'rsync-intermediary',
              'trigger': True,
              'passed': list(graph.successors(node))}]

    meta = graph.node[node]['meta']
    local_channel = os.path.join('rsync-intermediary', commit_id, 'artifacts')
    for pkg in conda_build.api.get_output_file_paths(meta):
        subdir = os.path.basename(os.path.dirname(pkg))
        filename = os.path.basename(pkg)

        args = ['--test', '-c', local_channel]
        for channel in meta.config.channel_urls:
            args.extend(['-c', channel])
        args.append(os.path.join(local_channel, subdir, filename))

        task_dict = {
            'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],  # NOQA
            # dependency inputs are down below
            'inputs': [{'name': 'rsync-intermediary'}],
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


def get_upload_job(graph, node, upload_config_path, config_vars, commit_id, public=True):
    meta = graph.node[node]['meta']
    plan = [{'get': 'rsync-intermediary',
             'trigger': True,
             'passed': list(graph.successors(node))}]

    for package in conda_build.api.get_output_file_paths(meta):
        filename = os.path.basename(package)
        tasks = get_upload_tasks(filename, upload_config_path, worker=graph.node[node]['worker'],
                                 config_vars=config_vars, commit_id=commit_id)
        plan.extend(tasks)
    job = {'name': node, 'plan': plan, 'public': public}
    return job


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
    jobs = []
    upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    order = order_build(graph)

    resource_types = [{'name': 'rsync-resource',
                       'type': 'docker-image',
                       'source': {
                           'repository': 'mrsixw/concourse-rsync-resource',
                           'tag': 'latest'
                           }
                       }]
    resources = [{'name': 'rsync-intermediary',
                  'type': 'rsync-resource',
                  'source': {
                      'server': config_vars['intermediate-server'],
                      'base_dir': config_vars['intermediate-base-folder'],
                      'user': config_vars['intermediate-user'],
                      'private_key': config_vars['intermediate-private-key'],
                      }
                  }]

    for node in order:
        if node.startswith('build'):
            jobs.append(get_build_job(base_path, graph, node, config_vars['base-name'],
                                    commit_id, public))

        # test jobs need to get the package from either the temporary s3 store or test using the
        #     recipe (download package from available channels) and run a test task

        # TODO: currently tests for things that have no build are broken and skipped

        elif node.startswith('test'):
            if node.replace('test', 'build', 1) in graph.nodes():
                # we build the package in this plan.  Get it from s3.
                jobs.append(get_test_package_job(graph, node, config_vars['base-name'],
                                                 commit_id, public))
            else:
                # we are only testing this package in this plan.  Get from configured channels.
                jobs.append(get_test_recipe_job(base_path, graph, node,
                                                config_vars['base-name'], commit_id, public))

        # as far as the graph is concerned, there's only one upload job.  However, this job can
        # represent several upload tasks.  This take the job from the graph, and creates tasks
        # appropriately.
        #
        # This is also more complicated, because uploads may involve other resource types and
        # resources that are not used for build/test.  For example, the scp and commands uploads
        # need to be able to access private keys, which are stored in config uploads.d folder.
        elif node.startswith('upload'):
            job = get_upload_job(graph, node, upload_config_path, config_vars, commit_id=commit_id,
                                 public=public)
            jobs.append(job)

        else:
            raise NotImplementedError("Don't know how to handle task.  Currently, tasks must "
                                        "start with 'build', 'test', or 'upload'")

    # convert types for smoother output to yaml
    return {'resource_types': resource_types, 'resources': resources, 'jobs': jobs}


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
           public=True, output_dir='../output', **kw):
    """submit task that will monitor changes and trigger other build tasks

    This gets the ball rolling.  Once submitted, you don't need to manually trigger
    builds.  This is creating the task that monitors git changes and triggers regeneration
    of the dynamic job.
    """
    git_identifier = _get_current_git_rev(src_dir)
    pipeline_name = pipeline_name.format(base_name=base_name,
                                         git_identifier=git_identifier)
    pipeline_file = pipeline_file.format(git_identifier=git_identifier)

    config_path = os.path.join(config_root_dir, 'config.yml')
    with open(config_path) as src:
        data = yaml.load(src)

    key_handle, key_file = tempfile.mkstemp()
    key_handle = os.fdopen(key_handle, 'w')
    key_handle.write(data['intermediate-private-key'])
    key_handle.close()

    subprocess.check_call(['ssh', '-o', 'UserKnownHostsFile=/dev/null',
                           '-o', 'StrictHostKeyChecking=no',
                           '-i', key_file,
                           '{intermediate-user}@{intermediate-server}'.format(**data),
                           'mkdir -p {intermediate-base-folder}/config'.format(**data)])
    # TODO: rsync config folder to intermediate server
    subprocess.check_call(['rsync', '--delete', '-av', '-e', 'ssh -o UserKnownHostsFile=/dev/null '
                           '-o StrictHostKeyChecking=no -i ' + key_file,
                           config_root_dir + '/',
                           ('{intermediate-user}@{intermediate-server}:'
                            '{intermediate-base-folder}/config'.format(**data))
                           ])

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


def compute_builds(path, base_name, git_rev, stop_rev=None, folders=None, matrix_base_dir=None,
                   steps=0, max_downstream=5, test=False, public=True, output_dir='../output',
                   **kw):
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

    with open(os.path.join(matrix_base_dir, 'config.yml')) as src:
        data = yaml.load(src)
    data['recipe-repo-commit'] = repo_commit

    plan = graph_to_plan_with_jobs(os.path.abspath(path), task_graph,
                                   commit_id=repo_commit, matrix_base_dir=matrix_base_dir,
                                   config_vars=data, public=public)

    git_identifier = _get_current_git_rev(path)
    # here's how we fill in recipe output destination for the git commit we're working with
    output_dir = output_dir.format(base_name=base_name, git_identifier=git_identifier)

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    with open(os.path.join(output_dir, 'plan.yml'), 'w') as f:
        yaml.dump(plan, f, default_flow_style=False)

    # expand folders to include any dependency builds or tests
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.getcwd(), path))
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
            out_folder = os.path.join(output_dir, node)
            shutil.copytree(os.path.join(path, recipe), out_folder)
            # write the conda_build_config.yaml for this particular metadata into that recipe
            #   This should sit alongside meta.yaml, where conda-build will be able to find it
            with open(os.path.join(out_folder, 'conda_build_config.yaml'), 'w') as f:
                yaml.dump(meta.config.variant, f, default_flow_style=False)


def _copy_yaml_if_not_there(path, base_name):
    """For aribtrarily nested yaml files, check if they exist in the destination bootstrap
    dir. If not, copy them there from our central install.

    path looks something like:
    my_config_folder/config/config.yaml
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
    except:
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
