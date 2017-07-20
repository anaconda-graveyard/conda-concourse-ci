import os

from conda_build import api
from conda_build.metadata import MetaData
import networkx as nx
import pytest

from conda_concourse_ci import compute_build_graph
from .utils import make_recipe, test_config_dir, graph_data_dir, default_worker, test_data_dir

dummy_worker = {'platform': 'linux', 'arch': '64', 'label': 'linux',
                'connector': {'image': 'continuumio/conda-concourse-ci'}}


def test_get_build_deps(testing_metadata):
    assert (compute_build_graph.get_build_deps(testing_metadata) ==
            {'build_requirement': ("any", "any")})


def test_get_run_test_deps(testing_metadata):
    assert (compute_build_graph.get_run_test_deps(testing_metadata) ==
            {'run_requirement': ("1.0", 'any'), 'test_requirement': ("any", "any")})


def test_construct_graph(mocker, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = True
    g = compute_build_graph.construct_graph(graph_data_dir, worker=dummy_worker,
                                            run='build', folders=('b'),
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert set(g.nodes()) == set(['b-1.0-linux'])


def test_construct_graph_relative_path(testing_git_repo, testing_conda_resolve):
    g = compute_build_graph.construct_graph('.', dummy_worker, 'build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert set(g.nodes()) == {'test_dir_3-1.0-linux', 'test_dir_2-1.0-linux', 'test_dir_1-1.0-linux'}
    assert set(g.edges()) == {('test_dir_2-1.0-linux', 'test_dir_1-1.0-linux'),
                              ('test_dir_3-1.0-linux', 'test_dir_2-1.0-linux')}


def test_package_key(testing_metadata):
    assert (compute_build_graph.package_key(testing_metadata, 'linux') ==
            'test_package_key-1.0-python3.6-linux')
    assert (compute_build_graph.package_key(testing_metadata, 'linux', 'test') ==
            'c3itest-test_package_key-1.0-python3.6-linux')


def test_platform_specific_graph(mocker, testing_conda_resolve):
    """the recipes herein have selectors on dependencies.  We're making sure they work correctly.

    build:
      b -> a
      c -> b
      d -> c
      e -> d

    run:
      c -> a  # win
      e -> b  # win64
    """

    worker = {'platform': 'win', 'arch': '32', 'label': 'linux'}
    mocker.patch.object(compute_build_graph, '_installable')
    mocker.patch.object(compute_build_graph, '_buildable',
                lambda name, version, recipes_dir, worker, config: os.path.join(recipes_dir, name))
    compute_build_graph._installable.return_value = False
    g = compute_build_graph.construct_graph(graph_data_dir, worker,
                                            folders=('a', 'b', 'c', 'd', 'e'),
                                            run='build', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    # left depends on right
    deps = {('b-1.0-linux', 'a-1.0-linux'),
            ('c-1.0-linux', 'b-1.0-linux'),
            ('d-1.0-linux', 'c-1.0-linux'),
            ('e-1.0-linux', 'd-1.0-linux'),
            ('c-1.0-linux', 'a-1.0-linux'),
            }
    assert set(g.edges()) == deps
    worker['arch'] = '64'
    # this dependency is only present with a selector on win-64
    g = compute_build_graph.construct_graph(graph_data_dir, worker, folders=('a', 'b', 'c', 'd', 'e'),
                                            run='build', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    # left depends on right
    deps = {('b-1.0-linux', 'a-1.0-linux'),
            ('c-1.0-linux', 'b-1.0-linux'),
            ('d-1.0-linux', 'c-1.0-linux'),
            ('e-1.0-linux', 'd-1.0-linux'),
            ('c-1.0-linux', 'a-1.0-linux'),
            ('e-1.0-linux', 'b-1.0-linux'),
            }
    assert set(g.edges()) == deps


def test_run_test_graph(testing_conda_resolve):
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('a', 'b', 'c'),
                                            run='test', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert set(g.nodes()) == set(['c3itest-a-1.0-linux', 'c3itest-b-1.0-linux', 'c3itest-c-1.0-linux'])


def test_git_changed_recipes_head(testing_git_repo):
    assert (compute_build_graph.git_changed_recipes('HEAD') ==
            ['test_dir_3'])


def test_git_changed_recipes_earlier_rev(testing_git_repo):
    assert (compute_build_graph.git_changed_recipes('HEAD@{1}') ==
            ['test_dir_2'])


def test_git_changed_recipes_rev_range(testing_git_repo):
    assert (compute_build_graph.git_changed_recipes('HEAD@{3}', 'HEAD@{1}') ==
            ['test_dir_1', 'test_dir_2'])


def test_add_dependency_nodes_and_edges(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    compute_build_graph.add_dependency_nodes_and_edges('b-linux', testing_graph,
                                                       run='build', worker=dummy_worker,
                                                       conda_resolve=testing_conda_resolve)
    assert set(testing_graph.nodes()) == {'a-linux', 'b-linux', 'c3itest-c-linux'}


def test_buildable(monkeypatch, testing_metadata):
    config = testing_metadata.config
    assert compute_build_graph._buildable('somepackage', 'any', test_data_dir, dummy_worker, config)
    assert compute_build_graph._buildable('somepackage', '1.2.8', test_data_dir, dummy_worker, config)
    assert compute_build_graph._buildable('somepackage', '1.2.*', test_data_dir, dummy_worker, config)
    assert compute_build_graph._buildable('somepackage', '>=1.2', test_data_dir, dummy_worker, config)
    assert compute_build_graph._buildable('somepackage', '<2', test_data_dir, dummy_worker, config)
    assert compute_build_graph._buildable('somepackage', '>=1.2,<2', test_data_dir, dummy_worker, config)
    assert not compute_build_graph._buildable('somepackage', '5', test_data_dir, dummy_worker, config)
    assert not compute_build_graph._buildable('not_a_package', 'any', test_data_dir, dummy_worker, config)


def test_installable(testing_conda_resolve, testing_metadata):
    assert compute_build_graph._installable('a', "920", 'any', testing_metadata.config,
                                            testing_conda_resolve)
    assert compute_build_graph._installable('a', "920*", 'any', testing_metadata.config,
                                            testing_conda_resolve)

    # non-existent version
    assert not compute_build_graph._installable('a', '921', 'any', testing_metadata.config,
                                                testing_conda_resolve)

    # default build number is 0
    assert compute_build_graph._installable('a', '920', 'h68c14d1_0', testing_metadata.config,
                                            testing_conda_resolve)
    assert not compute_build_graph._installable('a', '920', 'h68c14d1_1', testing_metadata.config,
                                                testing_conda_resolve)

    # package not in index
    assert not compute_build_graph._installable('f', 'any', 'any', testing_metadata.config,
                                                testing_conda_resolve)


def test_expand_run_no_up_or_down(mocker, testing_graph, testing_conda_resolve):
    initial_length = len(testing_graph)
    # all packages are installable in the default index
    compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                   worker=dummy_worker, run='build')
    assert len(testing_graph) == initial_length


def test_expand_run_step_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('a',), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir,
                                   matrix_base_dir=test_config_dir,
                                   steps=1)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux'}
    assert set(g.edges()) == {('b-1.0-linux', 'a-1.0-linux')}


def test_expand_run_two_steps_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    # second expansion - one more layer out
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('a',), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir,
                                   matrix_base_dir=test_config_dir,
                                   steps=2)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux', 'c-1.0-linux'}


def test_expand_run_all_steps_down(mocker, testing_graph, testing_conda_resolve):
    """
    Should build/test/upload all of the recipes.
    Start with B
    B depends on A, so build A
    Step down the tree from B to C
    Step down the tree from C to D
    Step down the tree from D to E
    """
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('b',), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir,
                                   matrix_base_dir=test_config_dir,
                                   max_downstream=-1, steps=-1)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux', 'c-1.0-linux', 'd-1.0-linux', 'e-1.0-linux'}


def test_expand_run_all_steps_down_with_max(mocker, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('b',), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir,
                                   matrix_base_dir=test_config_dir,
                                   steps=-1, max_downstream=1)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux', 'c-1.0-linux'}


def test_expand_run_build_non_installable_prereq(mocker, testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    compute_build_graph._installable.return_value = False
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('b',), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux'}

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir, matrix_base_dir=test_config_dir,
                                   steps=1)
    assert set(g.nodes()) == {'a-1.0-linux', 'b-1.0-linux', 'c-1.0-linux'}


def test_order_build(testing_graph):
    order = compute_build_graph.order_build(testing_graph)
    assert order.index('b-linux') > order.index('a-linux')
    assert order.index('c3itest-c-linux') > order.index('b-linux')


def test_get_base_folders(testing_workdir):
    make_recipe('some_recipe')
    os.makedirs('not_a_recipe')
    with open(os.path.join('not_a_recipe', 'testfile'), 'w') as f:
        f.write('weee')

    changed_files = ['some_recipe/meta.yaml', 'not_a_recipe/testfile']
    assert (compute_build_graph._get_base_folders(testing_workdir, changed_files) ==
            ['some_recipe'])
    assert not compute_build_graph._get_base_folders(testing_workdir, changed_files[1:])


def test_deps_to_version_dict():
    deps = ['a', 'b 1.0', 'c 1.0 0']
    d = compute_build_graph._deps_to_version_dict(deps)
    assert d['a'] == ('any', 'any')
    assert d['b'] == ('1.0', 'any')
    assert d['c'] == ('1.0', '0')


def test_add_invalid_dir_to_graph(testing_graph, testing_conda_resolve):
    assert not compute_build_graph.add_recipe_to_graph(os.path.join(test_config_dir, 'uploads.d'),
                                                       testing_graph, run='build',
                                                       worker=default_worker,
                                                       conda_resolve=testing_conda_resolve)
    assert not compute_build_graph.add_recipe_to_graph('non-existent-dir',
                                                       testing_graph, run='build',
                                                       worker=default_worker,
                                                       conda_resolve=testing_conda_resolve)


def test_add_skipped_recipe(testing_graph, testing_conda_resolve):
    assert not compute_build_graph.add_recipe_to_graph(os.path.join(test_config_dir,
                                                                    'skipped_recipe'),
                                                       testing_graph, run='build',
                                                       worker=default_worker,
                                                       conda_resolve=testing_conda_resolve)


def test_cyclical_graph_error():
    g = nx.DiGraph()
    g.add_node('a')
    g.add_node('b')
    g.add_edge('a', 'b')
    g.add_edge('b', 'a')
    with pytest.raises(ValueError):
        compute_build_graph.order_build(g)


def test_resolve_cyclical_build_test_dependency():
    g = nx.DiGraph()
    g.add_node('build-a')
    g.add_node('build-b')
    g.add_node('test-a')
    g.add_node('test-b')
    # normal test after build dependencies
    g.add_edge('build-a', 'test-a')
    # this one will shift from depending on build-b to depending on test-a, which depends on build-b
    g.add_edge('build-b', 'test-b')
    # the build-time dependence of B on A.
    #     This one has to be removed.  build-b instead must depend on build-a
    g.add_edge('test-a', 'build-b')
    # the runtime dependency of A on B.  This one stays.
    g.add_edge('build-b', 'test-a')

    compute_build_graph.reorder_cyclical_test_dependencies(g)
    assert not ('test-a', 'build-b') in g.edges()
    assert not ('build-b', 'test-b') in g.edges()
    assert ('test-a', 'test-b') in g.edges()
    assert ('build-b', 'test-a') in g.edges()


def test_add_intradependencies():
    a_meta = MetaData.fromdict({'package': {'name': 'a', 'version': '1.0'}})
    b_meta = MetaData.fromdict({'package': {'name': 'b', 'version': '1.0'},
                                'requirements': {'build': ['a']}})
    g = nx.DiGraph()
    g.add_node('a', meta=a_meta)
    g.add_node('b', meta=b_meta)
    compute_build_graph.add_intradependencies(g)
    assert ('b', 'a') in g.edges()


def test_version_matching(testing_conda_resolve):
    g = compute_build_graph.construct_graph(os.path.join(test_data_dir, 'version_resolution'),
                                            dummy_worker,
                                            folders=('upstream-1.0', 'upstream-2.0', 'downstream'),
                                            run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert len(g.nodes()) == 4
    assert ('downstream-1.0-upstream1.0-linux', 'upstream-1.0.1-linux') in g.edges()
    assert ('downstream-1.0-upstream2.0-linux', 'upstream-2.0.2-linux') in g.edges()


def test_submodules(testing_submodule_commit):
    assert 'conda-feedstock' in compute_build_graph.git_changed_submodules('.')
    assert 'cb3-feedstock' in compute_build_graph.git_renamed_folders('.')


def test_new_submodules(testing_new_submodules):
    new_submodules = compute_build_graph.git_new_submodules('.')
    assert 'conda-env-feedstock' in new_submodules
    assert 'conda-verify' not in new_submodules
