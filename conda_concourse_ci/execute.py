from __future__ import print_function, division
import logging
import os
import subprocess

from conda_build.conda_interface import Resolve, get_index
from conda_build.metadata import build_string_from_metadata
import networkx as nx
import yaml

from .compute_build_graph import construct_graph, expand_run, order_build, package_key
from .build_matrix import load_platforms

log = logging.getLogger(__file__)


def _plan_boilerplate():
    return {
        "resource_types": [
            {'name': 'concourse-pipeline',
             'type': 'docker-image',
             'source': {
                 'repository': 'robdimsdale/concourse-pipeline-resource',
                 'tag': 'latest-final'}
             },
            {'name': 's3-simple',
             'type': 'docker-image',
             'source': {'repository': '18fgsa/s3-resource-simple'}}
        ],
        'resources': [
            {'name': 'recipe-repo',
             'type': 'git',
             'source': {
                 'uri': '{{recipe-repo}}'},
                 'branch': "{{recipe-repo-commit}}"
            },
            {'name': 'execute-tasks',
             'type': 'concourse-pipeline',
             'source': {
                 'target': '{{concourse-url}}',
                 'teams': [
                     {'name': '{{concourse-team}}',
                      'username': "{{concourse-user}}",
                      'password': "{{concourse-password}}",
                      }
                 ]

             }},
            {'name': 's3-intermediary',
             'type': 's3-simple',
             'trigger': True,
             'source': {
                 'bucket': '{{aws-bucket}}',
                 'access_key_id': '{{aws-key-id}}',
                 'secret_access_key': '{{aws-secret-key}}',
                 # tiny bit hokey here.  We include only paths starting with c
                 #   This includes config and ci-tasks folders
                 'options': [
                     '"--exclude \'*\'"',
                     '"--include \'c*\'"'
                     ]
                 }
             }
        ],
    }


def find_task_deps_in_group(task, graph, groups):
    found = [-1]
    for dep in graph.successors(task):
        for idx, group in enumerate(groups):
            if any(dep == entry['task'] for entry in group):
                found.append(idx)
                break
    return max(found)


def graph_to_plan_dict(graph, public=True):
    plan = _plan_boilerplate()
    order = order_build(graph)
    tasks = [{'get': 's3-intermediary'}]
    # cluster things together into explicitly parallel groups
    aggregate_groups = [[], ]
    for task in order:
        # If any dependency is part of a current group, then we need to go one past that group.
        in_group = find_task_deps_in_group(task, graph, aggregate_groups)
        if in_group == -1:
            aggregate_groups[0].append({'task': task,
                                        'file': 's3-intermediary/ci-tasks/{}.yml'.format(task),
                                        })
        else:
            try:
                aggregate_groups[in_group + 1]
            except IndexError:
                aggregate_groups.append([])
            aggregate_groups[in_group + 1].append({'task': task,
                                                    'file': ('s3-intermediary/ci-tasks/{}.yml'
                                                             .format(task)),
                                                   })

    tasks.extend([{'aggregate': group} for group in aggregate_groups])
    plan.update({'jobs': [{'name': 'execute',
                           'public': public,
                           'plan': tasks
                           }]})
    return plan


def get_task_dict(graph, node):
    test_arg = '--no-test' if node.startswith('build') else '--test'
    task_dict = {
        'platform': graph.node[node]['worker']['label'],
        'outputs': {'name': node},
        'run': {
             'path': 'conda',
             'args': ['build', test_arg, os.path.dirname(graph.node[node]['meta'].meta_path)]}

         }

    # this has details on what image or image_resource to use.
    #   TODO: is it OK to be empty?
    task_dict.update(graph.node[node]['worker'].get('connector', {}))

    task_dict.update({
        'inputs': graph.successors(node)
    })
    return task_dict


def parse_platforms(matrix_base_dir, run):
    platform_folder = '{}_platforms.d'.format(run)
    platforms = load_platforms(os.path.join(matrix_base_dir, platform_folder))
    log.debug("Platforms found for mode %s:", run)
    log.debug(platforms)
    return platforms


def collect_tasks(path, folders, steps=0, test=False, max_downstream=5, matrix_base_dir=None):
    runs = ['test']
    # not testing means build and test
    if not test:
        runs.insert(0, 'build')

    if not matrix_base_dir:
        matrix_base_dir = path

    indexes = {}
    task_graph = nx.DiGraph()
    for run in runs:
        platforms = parse_platforms(matrix_base_dir, run)
        # loop over platforms here because each platform may have different dependencies
        # each platform will be submitted with a different label
        for platform in platforms:
            index_key = '-'.join([platform['platform'], str(platform['arch'])])
            if index_key not in indexes:
                indexes[index_key] = Resolve(get_index(platform=index_key))
            # this graph is potentially different for platform and for build or test mode ("run")
            g = construct_graph(path, worker=platform, folders=folders, run=run,
                                matrix_base_dir=matrix_base_dir, conda_resolve=indexes[index_key])
            # Apply the build label to any nodes that need (re)building or testing
            expand_run(g, conda_resolve=indexes[index_key], worker=platform, run=run,
                       steps=steps, max_downstream=max_downstream, recipes_dir=path,
                       matrix_base_dir=matrix_base_dir)
            # merge this graph with the main one
            task_graph = nx.compose(task_graph, g)
    return task_graph


def graph_to_plan_and_tasks(graph, public=True):
    plan = graph_to_plan_dict(graph, public)
    tasks = {node: get_task_dict(graph, node) for node in graph.nodes()}
    return plan, tasks


def write_tasks(tasks, output_folder='ci-tasks'):
    try:
        os.makedirs(output_folder)
    except:
        pass
    for name, task in tasks.items():
        with open(os.path.join(output_folder, name + '.yml'), 'w') as f:
            f.write(yaml.dump(task))
