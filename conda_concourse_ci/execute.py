from __future__ import print_function, division
from collections import OrderedDict
import contextlib
import logging
import os
import subprocess

from conda_build.conda_interface import Resolve, get_index
import networkx as nx
import yaml

from .compute_build_graph import construct_graph, expand_run, order_build
from .build_matrix import load_platforms, expand_build_matrix

log = logging.getLogger(__file__)


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    git_current_rev = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                              cwd=path).rstrip()
    subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
    try:
        yield
    except:    # pragma: no cover
        raise  # pragma: no cover
    finally:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def _get_current_git_info(checkout_rev, path):
    branch = subprocess.check_output('git rev-parse --abbrev-ref {}'.format(checkout_rev).
                                     split(), cwd=path).decode().rstrip()

    commit = subprocess.check_output('git rev-parse {}'.format(checkout_rev).
                                     split(), cwd=path).decode().rstrip()
    return branch, commit


def get_plan_dict(repo, graph, node, env_vars):
    plan_dict = {'resources': [
                    {'name': 'source-code',
                     'type': 'git',
                     'source': {'uri': repo}
                     },
                   ],
                 'params': env_vars,
                 }
    return plan_dict


def get_task_dict(recipe, run, platform_dict, variables, dependencies=()):
    test_arg = '--no-test' if run == 'build' else '--test'
    task_dict = {
        {'platform': platform_dict['worker_label'],
         'image_resource': platform_dict['connector'],
         'outputs': {'name': _package_key(run, recipe)},
         'run': {
             'path': 'conda',
             'args': ['build', test_arg, recipe]}

         }
        }
    if dependencies:
        task_dict.update({
            'inputs': [{'name': dep} for dep in dependencies]
        })
    return task_dict


def collect_tasks(path, packages=(), git_rev='HEAD', stop_rev=None, steps=0,
                     test=False, max_downstream=5, **kwargs):
    checkout_rev = stop_rev or git_rev

    runs = ['test']
    # not testing means build and test
    if not test:
        runs.insert(0, 'build')

    branch, commit_sha = _get_current_git_info(checkout_rev, path)

    indexes = {}
    tasks = nx.DiGraph()
    with checkout_git_rev(checkout_rev, path):
        for run in runs:
            platform_folder = '{}_platforms.d'.format(run)
            platforms = load_platforms(os.path.join(path, platform_folder))
            log.debug("Platforms found for mode %s:", run)
            log.debug(platforms)
            # loop over platforms here because each platform may have different dependencies
            # each platform will be submitted with a different label
            for platform in platforms:
                index_key = '-'.join([platform['platform'], str(platform['arch'])])
                if index_key not in indexes:
                    indexes[index_key] = Resolve(get_index(platform=index_key))
                # this graph is potentially different for both platform, and for build or test mode
                g = construct_graph(path, platform=platform['platform'], arch=platform['arch'],
                                    folders=packages, git_rev=git_rev, stop_rev=stop_rev,
                                    deps_type=run)
                # Apply the build label to any nodes that need (re)building.
                # note that the graph is changed in place here.
                expand_run(g, conda_resolve=indexes[index_key], run=run, steps=steps,
                           max_downstream=max_downstream, matrix_base_path=path)
                tasks = nx.compose(tasks, g)
    return tasks


def graph_to_plan_and_tasks(graph, filter_dirty):
    # sort build order, and also filter so that we have solely dirty nodes in subgraph
    subgraph, order = order_build(graph, filter_dirty=filter_dirty)

    return plan, tasks


def write_tasks(tasks, output_folder='ci-tasks'):
    for name, task in tasks.items():
        with open(os.path.join(output_folder, name + '.yml'), 'w') as f:
            f.write(yaml.dump(task))
