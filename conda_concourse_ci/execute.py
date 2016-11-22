from __future__ import print_function, division
import logging
import os
import re

import conda_build.api
from conda_build.conda_interface import Resolve, get_index
import networkx as nx
import yaml

from .compute_build_graph import construct_graph, expand_run, order_build
from .build_matrix import load_yaml_config_dir
from .uploads import get_upload_tasks

log = logging.getLogger(__file__)


def _plan_boilerplate():
    return """
resources:
- name: s3-archive
  type: s3
  trigger: true
  source:
    bucket: {{aws-bucket}}
    access_key_id: {{aws-key-id}}
    secret_access_key: {{aws-secret-key}}
    region_name: {{aws-region-name}}
    regexp: tasks-and-recipes-(.*).tar.bz2
"""


def find_task_deps_in_group(task, graph, groups):
    found = [-1]
    for dep in graph.successors(task):
        for idx, group in enumerate(groups):
            if any(dep == entry['task'] for entry in group):
                found.append(idx)
                break
    return max(found)


def _extract_task(version):
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
                             's3-archive/tasks-and-recipes-{0}.tar.bz2'.format(version),
                             '-C', 'extracted-archive']
                        }
                      }
            }


_ls_task = {'task': 'ls-folders',
           'config': {
               'inputs': [{'name': 'extracted-archive'}],
               'image_resource': {
                    'type': 'docker-image',
                    'source': {'repository': 'msarahan/conda-concourse-ci'}},
               'platform': 'linux',
               'run': {
                   'path': 'ls',
                   'args': ['-lR']
                   }
               }}


def graph_to_plan_text(graph, version, upload_tasks, public=True):
    order = order_build(graph)
    tasks = [{'get': 's3-archive',
              'trigger': 'true', 'params': {'version': '{{version}}'}},
             _extract_task(version), _ls_task]
    # cluster things together into explicitly parallel groups
    # aggregate_groups = [[], ]
    # for task in order:
    #     # If any dependency is part of a current group, then we need to go one past that group.
    #     in_group = find_task_deps_in_group(task, graph, aggregate_groups)
    #     if in_group == -1:
    #         aggregate_groups[0].append({'task': task,
    #                                     'file': 'extracted-archive/output/{}.yml'.format(task),
    #                                     })
    #     else:
    #         try:
    #             aggregate_groups[in_group + 1]
    #         except IndexError:
    #             aggregate_groups.append([])
    #         aggregate_groups[in_group + 1].append({'task': task,
    #                                                 'file': ('extracted-archive/output/{}.yml'
    #                                                          .format(task)),
    #                                                })

    # tasks.extend([{'aggregate': group} for group in aggregate_groups])
    tasks.extend({'task': task, 'file': 'extracted-archive/output/{}.yml'.format(task)}
                 for task in order if task.split('-')[0] in ('build', 'test'))
    tasks.extend({'task': task, 'file': 'extracted-archive/output/{}.yml'.format(task)}
                 for task in upload_tasks)
    # it probably seems a little crazy that we do this as a string, not as a dictionary.
    #    it is crazy.  The crappy thing is that the placeholder variables in the boilerplate
    #    are not evaluated correctly if we dump a dictionary.  They end up quoted, which prevents
    #    their evaluation.  So, strings it is.
    plan = _plan_boilerplate()
    plan = plan + '\n' + yaml.dump({'jobs': [{'name': 'execute',
                           'public': public,
                           'plan': tasks
                                              }]})
    # yaml dump quotes this inappropriately.  Nuke quoting in string.
    plan = plan.replace('"{{version}}"', '{{version}}').replace("'{{version}}'", '{{version}}')
    return plan


conda_platform_to_concourse_platform = {
    'win': 'windows',
    'osx': 'darwin',
    'linux': 'linux',
}


def get_task_dict(base_path, graph, node):
    test_arg = '--no-test' if node.startswith('build') else '--test'
    recipe_folder_name = graph.node[node]['meta'].meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]
    inputs = [{'name': 'extracted-archive'}]
    inputs.extend([{'name': dep} for dep in graph.successors(node)])
    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        # dependency inputs are down below
        'inputs': inputs,
        'outputs': [{'name': node}, ],
        'params': graph.node[node]['env'],
        'run': {
             'path': 'conda',
             'args': ['build', test_arg, '--no-anaconda-upload', '--output-folder', node],
             'dir': 'extracted-archive',
                }
         }
    if node.startswith('build'):
        input_path = os.path.join('recipe-repo-source', recipe_folder_name)
    else:
        # the build copies the built package into a folder named after the build task.  That folder
        #    is an output of the build step, and an input to the test step.
        meta = graph.node[node]['meta']
        package_filename = os.path.basename(conda_build.api.get_output_file_path(meta))
        input_path = os.path.join(os.path.join(node.replace('build', 'test'), package_filename))
    task_dict['run']['args'].append(input_path)

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))

    return task_dict


def parse_platforms(matrix_base_dir, run):
    platform_folder = '{}_platforms.d'.format(run)
    platforms = load_yaml_config_dir(os.path.join(matrix_base_dir, platform_folder))
    log.debug("Platforms found for mode %s:", run)
    log.debug(platforms)
    return platforms


def collect_tasks(path, folders, matrix_base_dir, steps=0, test=False, max_downstream=5):
    runs = ['test']
    # not testing means build and test
    if not test:
        runs.insert(0, 'build')

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


def graph_to_plan_and_tasks(base_path, graph, version, matrix_base_dir, public=True):
    upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    tasks = {}
    upload_tasks = {}
    # as far as the graph is concerned, there's only one upload job.  However, this job can
    # represent several upload tasks.  This take the job from the graph, and creates tasks
    # appropriately.
    for node in graph.nodes():
        if node.startswith('upload'):
            filename = os.path.basename(conda_build.api.get_output_file_path(graph.node[node]['meta']))  # NOQA
            test_task = node.replace('upload', 'test')
            for task in get_upload_tasks(test_task, filename, upload_config_path,
                                         worker=graph.node[node]['worker']):
                upload_tasks.update(task)
        else:
            tasks.update({node: get_task_dict(base_path, graph, node)})
    plan = graph_to_plan_text(graph, version, upload_tasks, public)

    for k, v in upload_tasks.items():
        tasks.update({k: v})

    return plan, tasks


def write_tasks(tasks, output_folder='output'):
    try:
        os.makedirs(output_folder)
    except:
        pass
    for name, task in tasks.items():
        with open(os.path.join(output_folder, name + '.yml'), 'w') as f:
            f.write(yaml.dump(task))
