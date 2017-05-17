#!/usr/bin/env python
from __future__ import print_function, division

import logging
import os
import re
import subprocess
import sys

import networkx as nx
from conda_build import api, conda_interface
from conda_build.metadata import MetaData, find_recipe

from .utils import HashableDict

log = logging.getLogger(__file__)
CONDA_BUILD_CACHE = os.environ.get("CONDA_BUILD_CACHE")
hash_length = api.Config().hash_length


def package_key(run, metadata, label):
    # get the build string from whatever conda-build makes of the configuration
    return "-".join([run, metadata.name(), metadata.build_id(), label])


def _git_changed_files(git_rev, stop_rev=None, git_root=''):
    if not git_root:
        git_root = os.getcwd()
    if stop_rev:
        git_rev = "{0}..{1}".format(git_rev, stop_rev)
    output = subprocess.check_output(['git', 'diff-tree', '--no-commit-id',
                                      '--name-only', '-r', git_rev],
                                     cwd=git_root)
    files = output.decode().splitlines()
    return files


def _get_base_folders(base_dir, changed_files):
    recipe_dirs = []
    for f in changed_files:
        # only consider files that come from folders
        if '/' in f:
            f = f.split('/')[0]
        try:
            find_recipe(os.path.join(base_dir, f))
            recipe_dirs.append(f)
        except IOError:
            pass
    return recipe_dirs


def git_changed_recipes(git_rev, stop_rev=None, git_root=''):
    """
    Get the list of files changed in a git revision and return a list of
    package directories that have been modified.

    git_rev: if stop_rev is not provided, this represents the changes
             introduced by the given git rev.  It is equivalent to
             git_rev=SOME_REV@{1} and stop_rev=SOME_REV

    stop_rev: when provided, this is the end of a range of revisions to
             consider.  git_rev becomes the start revision.  Note that the
             start revision is *one before* the actual start of examining
             commits for changes.  In other words:

             git_rev=SOME_REV@{1} and stop_rev=SOME_REV   => only SOME_REV
             git_rev=SOME_REV@{2} and stop_rev=SOME_REV   => two commits, SOME_REV and the
                                                             one before it
    """
    changed_files = _git_changed_files(git_rev, stop_rev=stop_rev, git_root=git_root)
    recipe_dirs = _get_base_folders(git_root, changed_files)
    return recipe_dirs


def _deps_to_version_dict(deps):
    d = {}
    for x in deps:
        x = x.strip().split()
        if len(x) == 3:
            d[x[0]] = (x[1], x[2])
        elif len(x) == 2:
            d[x[0]] = (x[1], 'any')
        else:
            d[x[0]] = ('any', 'any')
    return d


def get_build_deps(meta):
    build_reqs = meta.get_value('requirements/build')
    if not build_reqs:
        build_reqs = []
    return _deps_to_version_dict(build_reqs)


def get_run_test_deps(meta):
    run_reqs = meta.get_value('requirements/run')
    if not run_reqs:
        run_reqs = []
    test_reqs = meta.get_value('test/requires')
    if not test_reqs:
        test_reqs = []
    return _deps_to_version_dict(run_reqs + test_reqs)


_rendered_recipes = {}


def _get_or_render_metadata(meta_file_or_recipe_dir, worker):
    global _rendered_recipes
    worker = HashableDict(worker)
    if (meta_file_or_recipe_dir, worker) not in _rendered_recipes:
        _rendered_recipes[(meta_file_or_recipe_dir, worker)] = api.render(meta_file_or_recipe_dir,
                                                                platform=worker['platform'],
                                                                arch=worker['arch'])
    return _rendered_recipes[(meta_file_or_recipe_dir, worker)]


def add_recipe_to_graph(recipe_dir, graph, run, worker, conda_resolve,
                        recipes_dir=None):
    try:
        rendered = _get_or_render_metadata(recipe_dir, worker)
    except (IOError, SystemExit):
        log.debug('invalid recipe dir: %s - skipping', recipe_dir)
        return None

    metadata_tuples = rendered
    for (metadata, _, _) in metadata_tuples:
        name = package_key(run, metadata, worker['label'])

        if metadata.skip():
            return None

        graph.add_node(name, meta=metadata, worker=worker)
        add_dependency_nodes_and_edges(name, graph, run, worker, conda_resolve,
                                    recipes_dir=recipes_dir)

        # add the test equivalent at the same time.  This is so that expanding can find it.
        if run == 'build':
            add_recipe_to_graph(recipe_dir, graph, 'test', worker, conda_resolve,
                                recipes_dir=recipes_dir)
            test_key = package_key('test', metadata, worker['label'])
            graph.add_edge(test_key, name)
            upload_key = package_key('upload', metadata, worker['label'])
            graph.add_node(upload_key, meta=metadata, worker=worker)
            graph.add_edge(upload_key, test_key)

    return name


def construct_graph(recipes_dir, worker, run, conda_resolve, folders=(),
                    git_rev=None, stop_rev=None, matrix_base_dir=None):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    run: whether to use build or run/test requirements for the graph.  Avoids cycles.
          values: 'build' or 'test'.  Actually, only 'build' matters - otherwise, it's
                   run/test for any other value.
    '''
    matrix_base_dir = matrix_base_dir or recipes_dir
    if not os.path.isabs(recipes_dir):
        recipes_dir = os.path.normpath(os.path.join(os.getcwd(), recipes_dir))
    assert os.path.isdir(recipes_dir)

    if not folders:
        if not git_rev:
            git_rev = 'HEAD'
        folders = git_changed_recipes(git_rev, stop_rev=stop_rev,
                                      git_root=recipes_dir)
    graph = nx.DiGraph()
    for folder in folders:
        recipe_dir = os.path.join(recipes_dir, folder)
        add_recipe_to_graph(recipe_dir, graph, run, worker, conda_resolve,
                            recipes_dir)
    return graph


def _fix_any(value, config):
    value = re.sub('any(?:h[0-9a-f]{%d})?' % config.hash_length, '', value)
    return value


@conda_interface.memoized
def _installable(name, version, build_string, config, conda_resolve):
    """Can Conda install the package we need?"""
    ms = conda_interface.MatchSpec(" ".join([name, _fix_any(version, config),
                                             _fix_any(build_string, config)]))
    return conda_resolve.valid(ms, filter=conda_resolve.default_filter())


def _buildable(metadata, version, worker, recipes_dir=None):
    """Does the recipe that we have available produce the package we need?"""
    # best: metadata comes from a real recipe, and we have a path to it.  Version may still
    #    not match.
    recipes_dir = recipes_dir or os.getcwd()
    path = os.path.join(recipes_dir, metadata.name())
    if os.path.exists(metadata.meta_path):
        metadata_tuples = _get_or_render_metadata(metadata.meta_path, worker)
    # next best: matching name recipe folder in cwd
    elif os.path.isdir(path):
        metadata_tuples = _get_or_render_metadata(path, worker)
    else:
        return False

    # this is our target match
    ms = conda_interface.MatchSpec(" ".join([metadata.name(),
                                             _fix_any(version, metadata.config)]))
    for (m, _, _) in metadata_tuples:
        # this is what we have available from the recipe
        match_dict = {'name': m.name(),
                    'version': m.version(),
                    'build': _fix_any(m.build_id(), m.config), }
        if conda_interface.conda_43:
            match_dict = conda_interface.Dist(name=match_dict['name'],
                                              dist_name='-'.join((match_dict['name'],
                                                                  match_dict['version'],
                                                                  match_dict['build'])),
                                              version=match_dict['version'],
                                              build_string=match_dict['build'],
                                              build_number=int(m.build_number() or 0),
                                              channel=None)
        available = ms.match(match_dict)
        if available:
            break
    return m.meta_path if available else False


def add_dependency_nodes_and_edges(node, graph, run, worker, conda_resolve, recipes_dir=None):
    '''add build nodes for any upstream deps that are not yet installable

    changes graph in place.
    '''
    metadata = graph.node[node]['meta']
    deps = get_build_deps(metadata) if run == 'build' else get_run_test_deps(metadata)
    for dep, (version, build_str) in deps.items():
        dummy_meta = MetaData.fromdict({
            'package': {'name': dep,
                        'version': version},
            'build': {'string': build_str}})
        # version is passed literally here because constraints may make it an invalid version
        #    for metadata.
        dep_name = package_key('build', dummy_meta, worker['label'])
        dep_re = re.sub(r'anyh[0-9a-f]{%d}' % metadata.config.hash_length, '.*', dep_name)
        if sys.version_info.major < 3:
            dep_re = re.compile(dep_re.encode('unicode-escape'))
        else:
            dep_re = re.compile(dep_re)

        # we don't need worker info in _installable because it is already part of conda_resolve
        if not _installable(dep, version, build_str, dummy_meta.config, conda_resolve):
            nodes_in_graph = [dep_re.match(_n) for _n in graph.nodes()]
            node_in_graph = [_n for _n in nodes_in_graph if _n]
            if not node_in_graph:
                recipe_dir = _buildable(dummy_meta, version, worker, recipes_dir)
                if not recipe_dir:
                    raise ValueError("Dependency %s is not installable, and recipe (if "
                                     " available) can't produce desired version (%s).",
                                     dep, version)
                dep_name = add_recipe_to_graph(recipe_dir, graph, 'build', worker,
                                               conda_resolve, recipes_dir)
                if not dep_name:
                    raise ValueError("Tried to build recipe {0} as dependency, which is skipped "
                                     "in meta.yaml".format(recipe_dir))
            else:
                dep_name = node_in_graph[0].string

            graph.add_edge(node, dep_name)


def expand_run(graph, conda_resolve, worker, run, steps=0, max_downstream=5,
               recipes_dir=None, matrix_base_dir=None):
    """Apply the build label to any nodes that need (re)building or testing.

    "need rebuilding" means both packages that our target package depends on,
    but are not yet built, as well as packages that depend on our target
    package. For the latter, you can specify how many dependencies deep (steps)
    to follow that chain, since it can be quite large.

    If steps is -1, all downstream dependencies are rebuilt or retested
    """
    downstream = 0
    initial_nodes = len(graph.nodes())

    # for build, we get test automatically.  Give people the max_downstream in terms
    #   of packages, not tasks
    if run == 'build':
        max_downstream *= 2

    def expand_step(task_graph, full_graph, downstream):
        for node in task_graph.nodes():
            for predecessor in full_graph.predecessors(node):
                if max_downstream < 0 or (downstream - initial_nodes) < max_downstream:
                    add_recipe_to_graph(
                        os.path.dirname(full_graph.node[predecessor]['meta'].meta_path),
                        task_graph, run=run, worker=worker, conda_resolve=conda_resolve,
                        recipes_dir=recipes_dir)
                    downstream += 1
        return len(graph.nodes())

    # starting from our initial collection of dirty nodes, trace the tree down to packages
    #   that depend on the dirty nodes.  These packages may need to be rebuilt, or perhaps
    #   just tested.  The 'run' argument determines which.

    if steps != 0:
        if not recipes_dir:
            raise ValueError("recipes_dir is necessary if steps != 0.  "
                             "Please pass it as an argument.")
        # here we need to fully populate a graph that has the right build or run/test deps.
        #    We don't create this elsewhere because it is unnecessary and costly.

        # get all immediate subdirectories
        other_top_dirs = [d for d in os.listdir(recipes_dir)
                        if os.path.isdir(os.path.join(recipes_dir, d)) and
                        not d.startswith('.')]
        recipe_dirs = []
        for recipe_dir in other_top_dirs:
            try:
                find_recipe(os.path.join(recipes_dir, recipe_dir))
                recipe_dirs.append(recipe_dir)
            except IOError:
                pass

        # constructing the graph for build will automatically also include the test deps
        full_graph = construct_graph(recipes_dir, worker, 'build', folders=recipe_dirs,
                                     matrix_base_dir=matrix_base_dir, conda_resolve=conda_resolve)

        if steps >= 0:
            for step in range(steps):
                downstream = expand_step(graph, full_graph, downstream)
        else:
            while True:
                nodes = graph.nodes()
                downstream = expand_step(graph, full_graph, downstream)
                if nodes == graph.nodes():
                    break


def order_build(graph):
    '''
    Assumes that packages are in graph.
    Builds a temporary graph of relevant nodes and returns it topological sort.

    Relevant nodes selected in a breadth first traversal sourced at each pkg
    in packages.
    '''

    try:
        order = nx.topological_sort(graph, reverse=True)
    except nx.exception.NetworkXUnfeasible:
        raise ValueError("Cycles detected in graph: %s", nx.find_cycle(graph,
                                                                       orientation='ignore'))

    return order
