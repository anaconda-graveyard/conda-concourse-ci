#!/usr/bin/env python
from __future__ import print_function, division

import logging
import os
import subprocess

import networkx as nx
from conda_build import api, conda_interface
from conda_build.metadata import MetaData, find_recipe, build_string_from_metadata

from .build_matrix import expand_build_matrix, set_conda_env_vars

log = logging.getLogger(__file__)
CONDA_BUILD_CACHE = os.environ.get("CONDA_BUILD_CACHE")


def package_key(run, metadata, label):
    # get the build string from whatever conda-build makes of the configuration
    configuration = build_string_from_metadata(metadata)
    return "-".join([run, metadata.name(), configuration, label])


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


def add_recipe_to_graph(recipe_dir, graph, run, env_var_set, worker, conda_resolve,
                        recipes_dir=None):
    with set_conda_env_vars(env_var_set):
        rendered = api.render(recipe_dir, platform=worker['platform'],
                              arch=worker['arch'])
    # directories passed may not be valid recipes.  Skip them if they aren't
    if not rendered:
        return

    metadata, _, _ = rendered
    name = package_key(run, metadata, worker['label'])

    if metadata.skip():
        return None

    graph.add_node(name, meta=metadata, env=env_var_set, worker=worker)
    add_dependency_nodes_and_edges(name, graph, run, env_var_set, worker, conda_resolve,
                                   recipes_dir=recipes_dir)

    # add the test equivalent at the same time.  This is so that expanding can find it.
    if run == 'build':
        add_recipe_to_graph(recipe_dir, graph, 'test', env_var_set, worker, conda_resolve,
                            recipes_dir=recipes_dir)
        test_key = package_key('test', metadata, worker['label'])
        graph.add_edge(test_key, name)
        upload_key = package_key('upload', metadata, worker['label'])
        graph.add_node(upload_key, meta=metadata, env=env_var_set, worker=worker)
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
        env_var_sets = expand_build_matrix(recipe_dir, matrix_base_dir)

        for env_var_set in env_var_sets:
            add_recipe_to_graph(recipe_dir, graph, run, env_var_set, worker, conda_resolve,
                                recipes_dir)
    return graph


def _fix_any(value):
    if value == 'any':
        value = ""
    return value


def _installable(metadata, version, conda_resolve):
    """Can Conda install the package we need?"""
    return conda_resolve.valid(conda_interface.MatchSpec(" ".join([metadata.name(),
                                                                   _fix_any(version),
                                                                   _fix_any(metadata.build_id())])),
                               filter=conda_resolve.default_filter())


def _buildable(metadata, version, recipes_dir=None):
    """Does the recipe that we have available produce the package we need?"""
    # best: metadata comes from a real recipe, and we have a path to it.  Version may still
    #    not match.
    recipes_dir = recipes_dir or os.getcwd()
    path = os.path.join(recipes_dir, metadata.name())
    if os.path.exists(metadata.meta_path):
        recipe_metadata, _, _ = api.render(metadata.meta_path)
    # next best: matching name recipe folder in cwd
    elif os.path.isdir(path):
        recipe_metadata, _, _ = api.render(path)
    else:
        return False

    # this is our target match
    ms = conda_interface.MatchSpec(" ".join([metadata.name(),
                                             _fix_any(version)]))
    # this is what we have available from the recipe
    match_dict = {'name': recipe_metadata.name(),
                  'version': recipe_metadata.version(),
                  'build': _fix_any(metadata.build_number()), }
    available = ms.match(match_dict)
    return recipe_metadata.meta_path if available else False


def add_dependency_nodes_and_edges(node, graph, run, env_var_set, worker, conda_resolve,
                                   recipes_dir=None):
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
        if not _installable(dummy_meta, version, conda_resolve):
            if dep_name not in graph.nodes():
                recipe_dir = _buildable(dummy_meta, version, recipes_dir)
                if not recipe_dir:
                    raise ValueError("Dependency %s is not installable, and recipe (if "
                                        " available) can't produce desired version.", dep)
                dep_name = add_recipe_to_graph(recipe_dir, graph, 'build', env_var_set,
                                               worker, conda_resolve, recipes_dir)
                if not dep_name:
                    raise ValueError("Tried to build recipe {0} as dependency, which is skipped "
                                     "in meta.yaml".format(recipe_dir))
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
                        task_graph,
                        run=run, env_var_set=task_graph.node[node]['env'],
                        worker=worker, conda_resolve=conda_resolve, recipes_dir=recipes_dir)
                    downstream += 1
        return len(graph.nodes())

    # starting from our initial collection of dirty nodes, trace the tree down to packages
    #   that depend on the dirty nodes.  These packages may need to be rebuilt, or perhaps
    #   just tested.  The 'run' argument determines which.

    if steps != 0:
        if not recipes_dir:
            raise ValueError("recipes_dir is necessary if steps != 0.  Please pass it as an argument.")
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
