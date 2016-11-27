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


def _s3_resource(s3_name, regexp, vars):
    return {'name': s3_name,
            'type': 's3',
            'trigger': True,
            'source': {
                'bucket': vars['aws-bucket'],
                'access_key_id': vars['aws-key-id'],
                'secret_access_key': vars['aws-secret-key'],
                'region_name': vars['aws-region-name'],
                'regexp': regexp,
                }
            }


# def find_task_deps_in_group(task, graph, groups):
#     found = [-1]
#     for dep in graph.successors(task):
#         for idx, group in enumerate(groups):
#             if any(dep == entry['task'] for entry in group):
#                 found.append(idx)
#                 break
#     return max(found)


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


def get_s3_package_regex(base_name, worker, package_name):
    return "pkg_tmp_{0}_{1}/{2}-(.*).tar.bz2".format(base_name, worker['label'], package_name)


def get_s3_resource_name(base_name, worker, package_name):
    return "s3-{0}-{1}-{2}".format(base_name, worker['label'], package_name)


def get_build_job(base_path, graph, node, base_name, recipe_archive_version):
    tasks = [{'get': 's3-archive',
              'trigger': 'true',
              'params': {'version': recipe_archive_version},
              'passed': graph.successors(node)},
             _extract_task(base_name, recipe_archive_version)]
    meta = graph.node[node]['meta']
    recipe_folder_name = meta.meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]
    inputs = [{'name': 'extracted-archive'}]
    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        # dependency inputs are down below
        'inputs': inputs,
        'outputs': [{'name': node}, ],
        'params': graph.node[node]['env'],
        'run': {
             'path': 'conda',
             'args': ['build', '--no-test', '--no-anaconda-upload', '--output-folder', node,
                      os.path.join('recipe-repo-source', recipe_folder_name)],
             'dir': 'extracted-archive',
                }
         }

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))

    tasks.append({'task': node, 'config': task_dict})
    tasks.append({'put': get_s3_resource_name(base_name, graph.node[node]['worker'], meta.name()),
                  'params': {'from': os.path.join(node, '*.tar.bz2')}})
    return {'name': node, 'plan': tasks}


def get_test_recipe_job(base_path, graph, node, base_name, recipe_archive_version):
    tasks = [{'get': 's3-archive',
              'trigger': 'true',
              'params': {'version': recipe_archive_version},
              'passed': graph.successors(node)},
             _extract_task(base_name, recipe_archive_version)]
    recipe_folder_name = graph.node[node]['meta'].meta_path.replace(base_path, '')
    if '\\' in recipe_folder_name or '/' in recipe_folder_name:
        recipe_folder_name = list(filter(None, re.split("[\\/]+", recipe_folder_name)))[0]
    input_path = os.path.join('recipe-repo-source', recipe_folder_name)

    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        'inputs': [{'name': 'extracted-archive'}],
        'params': graph.node[node]['env'],
        'run': {
             'path': 'conda',
             'args': ['build', '--test', input_path],
             'dir': 'extracted-archive',
                }
         }

    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))
    tasks.append({'task': node, 'config': task_dict})

    return {'name': node, 'plan': tasks}


def get_test_package_job(graph, node, base_name):
    meta = graph.node[node]['meta']
    worker = graph.node[node]['worker']
    s3_resource_name = get_s3_resource_name(base_name, worker, meta.name())
    pkg_version = '{0}-{1}'.format(meta.version(), meta.build_id())
    tasks = [{'get': s3_resource_name,
              'trigger': 'true', 'params': {'version': pkg_version},
              'passed': graph.successors(node)},
             ]

    package_filename = os.path.basename(conda_build.api.get_output_file_path(meta))

    task_dict = {
        'platform': conda_platform_to_concourse_platform[graph.node[node]['worker']['platform']],
        # dependency inputs are down below
        'inputs': [{'name': s3_resource_name}],
        'params': graph.node[node]['env'],
        'run': {
             'path': 'conda',
             'args': ['build', '--test', os.path.join(s3_resource_name, package_filename)],
                }
         }
    # this has details on what image or image_resource to use.
    #   It is OK for it to be empty - it is used only for docker images, which is only a Linux
    #   feature right now.
    task_dict.update(graph.node[node]['worker'].get('connector', {}))

    tasks.append({'task': node, 'config': task_dict})

    return {'name': node, 'plan': tasks}


def graph_to_plan_with_jobs(base_path, graph, version, matrix_base_dir, vars, public=True):
    upload_config_path = os.path.join(matrix_base_dir, 'uploads.d')
    jobs = []
    order = order_build(graph)

    upload_tasks = []
    s3_resources = [("s3-archive", "recipes-{base-name}-(.*).tar.bz2")]
    for node in order:
        package_name = graph.node[node]['meta'].name()
        worker = graph.node[node]['worker']
        # build jobs need to get the recipes from s3, extract them, and run a build task
        #    same is true for test jobs that do not have a preceding test job.  These use the
        #    recipe for determining which package to download from available channels.
        if node.startswith('build'):
            # need to define an s3 resource for each built package
            s3_resources.append(_s3_resource(get_s3_resource_name(vars['base-name'],
                                                                  worker, package_name),
                                             get_s3_package_regex(vars['base-name'],
                                                                  worker, package_name),
                                             vars=vars))
            job = get_build_job(base_path, graph, node, vars['base-name'], version)

        # test jobs need to get the package from either the temporary s3 store or test using the
        #     recipe (download package from available channels) and run a test task
        elif node.startswith('test'):
            if node.replace('test', 'build') in graph.nodes():
                # we build the package in this plan.  Get it from s3.
                job = get_test_package_job(graph, node, vars['base-name'])
            else:
                # we are only testing this package in this plan.  Get it from configured channels.
                job = get_test_recipe_job(base_path, graph, node, vars['base-name'], version)

        # as far as the graph is concerned, there's only one upload job.  However, this job can
        # represent several upload tasks.  This take the job from the graph, and creates tasks
        # appropriately.
        elif node.startswith('upload'):
            filename = os.path.basename(conda_build.api.get_output_file_path(graph.node[node]['meta']))  # NOQA
            test_task = node.replace('upload', 'test')
            for task in get_upload_tasks(test_task, filename, upload_config_path,
                                         worker=graph.node[node]['worker']):
                upload_tasks.append(task)

        else:
            raise NotImplementedError("Don't know how to handle task.  Currently, tasks must start "
                                      "with 'build', 'test', or 'upload'")
        jobs.append(job)

    return {'resources': s3_resources, 'jobs': jobs}
