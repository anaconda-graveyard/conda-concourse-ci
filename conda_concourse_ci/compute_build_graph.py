#!/usr/bin/env python
from __future__ import print_function, division

import logging
import os
import subprocess

import networkx as nx
from conda_build import api, conda_interface
from conda_build.metadata import MetaData
from conda_build.metadata import find_recipe, build_string_from_metadata

from .build_matrix import expand_build_matrix, set_conda_env_vars

log = logging.getLogger(__file__)
CONDA_BUILD_CACHE = os.environ.get("CONDA_BUILD_CACHE")


def _package_key(metadata, label):
    # get the build string from whatever conda-build makes of the configuration
    configuration = build_string_from_metadata(metadata)
    return "-".join([metadata.name(), configuration, label])


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
            try:
                recipe_dir = f.split('/')[0]
                find_recipe(os.path.join(base_dir, recipe_dir))
                recipe_dirs.append(recipe_dir)
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
        if len(x) == 2:
            d[x[0]] = x[1]
        else:
            d[x[0]] = 'any'
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


def construct_graph(recipes_dir, platform, arch, label, folders=(), deps_type='build',
                    git_rev=None, stop_rev=None, matrix_base_dir=None):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    deps_type: whether to use build or run/test requirements for the graph.  Avoids cycles.
          values: 'build' or 'test'.  Actually, only 'build' matters - otherwise, it's
                   run/test for any other value.
    '''
    g = nx.DiGraph()
    if not matrix_base_dir:
        matrix_base_dir = recipes_dir
    if not os.path.isabs(recipes_dir):
        recipes_dir = os.path.normpath(os.path.join(os.getcwd(), recipes_dir))
    assert os.path.isdir(recipes_dir)

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

    if not folders:
        if not git_rev:
            git_rev = 'HEAD'
        folders = git_changed_recipes(git_rev, stop_rev=stop_rev,
                                      git_root=recipes_dir)

    for rd in recipe_dirs:
        recipe_dir = os.path.join(recipes_dir, rd)
        env_var_sets = expand_build_matrix(recipe_dir, matrix_base_dir)

        for env_var_set in env_var_sets:
            with set_conda_env_vars(env_var_set):
                metadata, _, _ = api.render(recipe_dir, platform=platform, arch=arch)
            name = _package_key(metadata, label)

            run_dict = {'build': deps_type == 'build' and rd in folders,  # will be built and tested
                        'test': deps_type == 'test' and rd in folders,  # must be installable; will be tested
                        'install': False,  # must be installable, but is not necessarily tested
                        }
            if not metadata.skip():
                # since we have no dependency ordering without a graph, it is conceivable that we add
                #    recipe information after we've already added package info as just a dependency.
                #    This first clause is if we encounter a recipe for the first time.  Its else clause
                #    is when we encounter a recipe after we've already added a node based on a
                #    dependency that can (presumably) be downloaded.
                if name.split('-')[0] not in g.nodes():
                    g.add_node(name, meta=metadata, recipe=recipe_dir, **run_dict)
                else:
                    # when we add deps, we don't know what their build strings might be.  Base this
                    #    only on name, until we have more info to add
                    nx.relabel_nodes(g, {name.split('-')[0]: name}, copy=False)
                    g.node[name]['meta'] = metadata
                    g.node[name]['recipe'] = recipe_dir
            deps = get_build_deps(metadata) if deps_type == 'build' else get_run_test_deps(metadata)
            for dep, version in deps.items():
                if dep not in (node.split('-')[0] for node in g.nodes()):
                    # we fill in the rest of the metadata if we encounter a recipe for this package
                    g.add_node(dep, meta=MetaData.fromdict({
                        'package': {'name': dep,
                                    'version': version}
                        }))
                else:
                    dep = [node for node in g.nodes() if node.split('-')[0] == dep][0]
                g.node[dep]['install'] = True
                g.add_edge(name, dep)
    return g


def _fix_blank_versions(metadata):
    version = metadata.version()
    if version == 'any':
        version = ""
    return version


def _installable(metadata, conda_resolve):
    """Can Conda install the package we need?"""
    return conda_resolve.valid(conda_interface.MatchSpec(" ".join([metadata.name(),
                                                                   _fix_blank_versions(metadata)])),
                               filter=conda_resolve.default_filter())


def _buildable(metadata):
    """Does the recipe that we have available produce the package we need?"""
    available = False
    # best: metadata comes from a real recipe, and we have a path to it
    if os.path.exists(metadata.meta_path):
        recipe_metadata, _, _ = api.render(metadata.meta_path)
    # next best: matching name recipe folder in cwd
    elif os.path.isdir(metadata.name()):
        recipe_metadata, _, _ = api.render(metadata.name())
    else:
        return False

    # this is our target match
    match_dict = {'name': metadata.name(),
                    'version': _fix_blank_versions(metadata),
                    'build': metadata.build_number(), }
    # we don't care about version, so just make it match.
    if not match_dict['version']:
        match_dict['version'] = recipe_metadata.version()
    # this is what we have available from the recipe
    ms = conda_interface.MatchSpec(" ".join([recipe_metadata.name(),
                                             recipe_metadata.version()]))
    available = ms.match(match_dict)
    return available


def upstream_dependencies_needing_build(graph, conda_resolve):
    dirty_nodes = [node for node, value in graph.node.items() if any([
        value.get('build'), value.get('install'), value.get('test')])]
    for node in dirty_nodes:
        for successor in graph.successors_iter(node):
            version = graph.node[successor].get('meta').version()
            if not _installable(successor, version, conda_resolve):
                if _buildable(successor, version):
                    graph.node[successor]['build'] = True
                    dirty_nodes.append(successor)
                else:
                    raise ValueError("Dependency %s is not installable, and recipe (if available)"
                                     " can't produce desired version.", successor)
    return set(dirty_nodes)


def expand_run(graph, conda_resolve, run, steps=0, max_downstream=5):
    """Apply the build label to any nodes that need (re)building.  "need rebuilding" means
    both packages that our target package depends on, but are not yet built, as well as
    packages that depend on our target package.  For the latter, you can specify how many
    dependencies deep (steps) to follow that chain, since it can be quite large.

    If steps is -1, all downstream dependencies are rebuilt or retested
    """
    upstream_dependencies_needing_build(graph, conda_resolve)
    downstream = 0

    initial_dirty = len(dirty(graph))

    def expand_step(dirty_nodes, downstream):
        for node in dirty_nodes:
            for predecessor in graph.predecessors(node):
                if max_downstream < 0 or (downstream - initial_dirty) < max_downstream:
                    graph.node[predecessor][run] = True
                    downstream += 1
        return len(dirty(graph))

    # starting from our initial collection of dirty nodes, trace the tree down to packages
    #   that depend on the dirty nodes.  These packages may need to be rebuilt, or perhaps
    #   just tested.  The 'run' argument determines which.

    if steps >= 0:
        for step in range(steps):
            downstream = expand_step(dirty(graph), downstream)
    else:
        start_dirty_nodes = dirty(graph)
        while True:
            downstream = expand_step(start_dirty_nodes, downstream)
            new_dirty = dirty(graph)
            if start_dirty_nodes == new_dirty:
                break
            start_dirty_nodes = new_dirty

    return dirty(graph)


def dirty(graph):
    """
    Return a set of all dirty nodes in the graph.
    """
    # Reverse the edges to get true dependency
    return {n: v for n, v in graph.node.items() if v.get('build') or v.get('test')}


def order_build(graph, packages=None, level=0, filter_dirty=True):
    '''
    Assumes that packages are in graph.
    Builds a temporary graph of relevant nodes and returns it topological sort.

    Relevant nodes selected in a breadth first traversal sourced at each pkg
    in packages.

    Values expected for packages is one of None, sequence:
       None: build the whole graph
       empty sequence: build nodes marked dirty
       non-empty sequence: build nodes in sequence
    '''

    if not packages:
        packages = graph.nodes()
        if filter_dirty:
            packages = dirty(graph)
    tmp_global = graph.subgraph(packages)

    # copy relevant node data to tmp_global
    for n in tmp_global.nodes_iter():
        tmp_global.node[n] = graph.node[n]

    try:
        order = nx.topological_sort(tmp_global, reverse=True)
    except nx.exception.NetworkXUnfeasible:
        raise ValueError("Cycles detected in graph: %s", nx.find_cycle(tmp_global,
                                                                       orientation='ignore'))

    return tmp_global, order
