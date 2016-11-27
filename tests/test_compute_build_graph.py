import os

from conda_build import api
import networkx as nx
import pytest
from pytest_mock import mocker

from conda_concourse_ci import compute_build_graph
from .utils import (testing_workdir, testing_git_repo, testing_graph, testing_conda_resolve,
                    testing_metadata, make_recipe, test_config_dir, graph_data_dir, default_worker, test_data_dir)

dummy_worker = {'platform': 'someos', 'arch': 'somearch', 'label': 'linux',
                'connector': {'image': 'msarahan/conda-concourse-ci'}}


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
    assert set(g.nodes()) == set(['build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux'])


def test_construct_graph_relative_path(testing_git_repo, testing_conda_resolve):
    g = compute_build_graph.construct_graph('.', dummy_worker, 'build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert set(g.nodes()) == set(['build-test_dir_3-0-linux', 'test-test_dir_3-0-linux', 'upload-test_dir_3-0-linux',
                                  'build-test_dir_2-0-linux', 'test-test_dir_2-0-linux', 'upload-test_dir_2-0-linux',
                                  'build-test_dir_1-0-linux', 'test-test_dir_1-0-linux', 'upload-test_dir_1-0-linux'])
    assert set(g.edges()) == set([('build-test_dir_2-0-linux', 'build-test_dir_1-0-linux'),
                                  ('build-test_dir_3-0-linux', 'build-test_dir_2-0-linux'),
                                  ('test-test_dir_2-0-linux', 'build-test_dir_2-0-linux'),
                                  ('test-test_dir_3-0-linux', 'build-test_dir_3-0-linux'),
                                  ('test-test_dir_1-0-linux', 'build-test_dir_1-0-linux'),
                                  ('upload-test_dir_2-0-linux', 'test-test_dir_2-0-linux'),
                                  ('upload-test_dir_3-0-linux', 'test-test_dir_3-0-linux'),
                                  ('upload-test_dir_1-0-linux', 'test-test_dir_1-0-linux')])


def test_package_key(testing_metadata):
    assert (compute_build_graph.package_key('build', testing_metadata, 'linux') ==
            'build-test_package_key-1-linux')


def test_platform_specific_graph(mocker, testing_conda_resolve):
    """the recipes herein have selectors on dependencies.  We're making sure they work correctly.

    build:
      b -> a
      c -> b
      d -> c
      e -> d

    run:
      d -> e     (intentionally circular, though cycle split between build and test, so OK)
      a -> c  # win
      a -> d  # win64
    """

    worker = {'platform': 'win', 'arch': '32', 'label': 'linux'}
    mocker.patch.object(compute_build_graph, '_installable')
    mocker.patch.object(compute_build_graph, '_buildable',
                        lambda meta, version, recipes_dir: os.path.join(recipes_dir, meta.name()))
    compute_build_graph._installable.return_value = False
    compute_build_graph._buildable
    g = compute_build_graph.construct_graph(graph_data_dir, worker,
                                            folders=('a', 'b', 'c', 'd', 'e'),
                                            run='test', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    deps = {('build-b-0-linux', 'build-a-0-linux'),
            ('build-c-0-linux', 'build-b-0-linux'),
            ('build-d-0-linux', 'build-c-0-linux'),
            ('build-e-0-linux', 'build-d-0-linux'),
            # run deps
            ('test-d-0-linux', 'build-e-0-linux'),
            ('test-a-0-linux', 'build-c-0-linux'),
            # test deps on builds
            ('test-a-0-linux', 'build-a-0-linux'),
            ('test-b-0-linux', 'build-b-0-linux'),
            ('test-c-0-linux', 'build-c-0-linux'),
            ('test-d-0-linux', 'build-d-0-linux'),
            ('test-e-0-linux', 'build-e-0-linux'),
            # uploads for the builds
            ('upload-a-0-linux', 'test-a-0-linux'),
            ('upload-b-0-linux', 'test-b-0-linux'),
            ('upload-c-0-linux', 'test-c-0-linux'),
            ('upload-d-0-linux', 'test-d-0-linux'),
            ('upload-e-0-linux', 'test-e-0-linux'),
    }
    assert set(g.edges()) == deps
    worker['arch'] = '64'
    g = compute_build_graph.construct_graph(graph_data_dir, worker, folders=('a'),
                                            run='test', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    deps.add(('test-a-0-linux', 'build-d-0-linux'))
    assert set(g.edges()) == deps

def test_construct_graph_raises_when_dep_neither_installable_or_buildable(mocker, testing_graph,
                                                                          testing_conda_resolve):
    mocker.patch.object(compute_build_graph, '_installable')
    mocker.patch.object(compute_build_graph, '_buildable')
    compute_build_graph._installable.return_value = False
    compute_build_graph._buildable.return_value = False
    with pytest.raises(ValueError):
        compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('b'), run='build',
                                            matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)

def test_run_test_graph(testing_conda_resolve):
    g = compute_build_graph.construct_graph(graph_data_dir, dummy_worker,
                                            folders=('a', 'b', 'c'),
                                            run='test', matrix_base_dir=test_config_dir,
                                            conda_resolve=testing_conda_resolve)
    assert set(g.nodes()) == set(['test-a-0-linux', 'test-b-0-linux', 'test-c-0-linux'])


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
    mocker.patch.object(compute_build_graph, '_buildable')
    compute_build_graph._buildable.return_value = os.path.join(graph_data_dir, 'a')
    compute_build_graph.add_dependency_nodes_and_edges('build-b-0-linux', testing_graph,
                                                            'build', {}, dummy_worker,
                                                            testing_conda_resolve)
    assert set(testing_graph.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                                          'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                                          'test-c-0-linux'}


def test_buildable(monkeypatch, testing_metadata):
    monkeypatch.chdir(test_data_dir)
    testing_metadata.meta['package']['name'] = 'somepackage'
    testing_metadata.meta['package']['version'] = 'any'
    assert compute_build_graph._buildable(testing_metadata, 'any')
    testing_metadata.meta['package']['version'] = '1.2.8'
    assert compute_build_graph._buildable(testing_metadata, '1.2.8')
    assert compute_build_graph._buildable(testing_metadata, '1.2.*')
    testing_metadata.meta['package']['version'] = '5.2.9'
    assert not compute_build_graph._buildable(testing_metadata, '5.2.9')
    testing_metadata.meta['package']['name'] = 'not_a_package'
    assert not compute_build_graph._buildable(testing_metadata, '5.2.9')

    a, _, _ = api.render(os.path.join(graph_data_dir, 'a'))
    assert compute_build_graph._buildable(a, '1.0', graph_data_dir)


def test_installable(testing_conda_resolve, testing_metadata):
    testing_metadata.meta['package']['name'] = 'a'
    testing_metadata.meta['package']['version'] = '920'
    testing_metadata.meta['build']['string'] = 'any'
    assert compute_build_graph._installable(testing_metadata, "920", testing_conda_resolve)
    assert compute_build_graph._installable(testing_metadata, "920*", testing_conda_resolve)

    # non-existent version
    testing_metadata.meta['package']['version'] = '921'
    assert not compute_build_graph._installable(testing_metadata, '921', testing_conda_resolve)

    # default build number is 0
    testing_metadata.meta['package']['version'] = '920'
    testing_metadata.meta['build']['string'] = '0'
    assert compute_build_graph._installable(testing_metadata, '920', testing_conda_resolve)
    testing_metadata.meta['package']['version'] = '920'
    testing_metadata.meta['build']['string'] = '1'
    assert not compute_build_graph._installable(testing_metadata, '920', testing_conda_resolve)

    # package not in index
    testing_metadata.meta['package']['name'] = 'f'
    assert not compute_build_graph._installable(testing_metadata, '920', testing_conda_resolve)


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
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux'}
    assert set(g.edges()) == {('test-a-0-linux', 'build-a-0-linux'),
                              ('build-b-0-linux', 'build-a-0-linux'),
                              ('test-b-0-linux', 'build-b-0-linux'),
                              ('upload-a-0-linux', 'test-a-0-linux'),
                              ('upload-b-0-linux', 'test-b-0-linux'),
                              }


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
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                              'build-c-0-linux', 'test-c-0-linux', 'upload-c-0-linux'}


def test_expand_run_all_steps_down(mocker, testing_graph, testing_conda_resolve):
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
                                   steps=-1)
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                              'build-c-0-linux', 'test-c-0-linux', 'upload-c-0-linux',
                              'build-d-0-linux', 'test-d-0-linux', 'upload-d-0-linux',
                              'build-e-0-linux', 'test-e-0-linux', 'upload-e-0-linux'}


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
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                              'build-c-0-linux', 'test-c-0-linux', 'upload-c-0-linux'}


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
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux'}

    compute_build_graph.expand_run(g, testing_conda_resolve,
                                   run='build', worker=dummy_worker,
                                   recipes_dir=graph_data_dir, matrix_base_dir=test_config_dir,
                                   steps=1)
    assert set(g.nodes()) == {'build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                              'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                              'build-c-0-linux', 'test-c-0-linux', 'upload-c-0-linux'}


def test_order_build(testing_graph):
    order = compute_build_graph.order_build(testing_graph)
    assert order == ['build-a-0-linux', 'test-a-0-linux', 'upload-a-0-linux',
                     'build-b-0-linux', 'test-b-0-linux', 'upload-b-0-linux',
                     'test-c-0-linux']


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
                                                       testing_graph, 'build',
                                                       {}, default_worker, testing_conda_resolve)
    assert not compute_build_graph.add_recipe_to_graph('non-existent-dir',
                                                       testing_graph, 'build',
                                                       {}, default_worker, testing_conda_resolve)


def test_add_skipped_recipe(testing_graph, testing_conda_resolve):
    assert not compute_build_graph.add_recipe_to_graph(os.path.join(test_config_dir, 'skipped_recipe'),
                                                       testing_graph, 'build',
                                                       {}, default_worker, testing_conda_resolve)


def test_cyclical_graph_error():
    g = nx.DiGraph()
    g.add_node('a')
    g.add_node('b')
    g.add_edge('a', 'b')
    g.add_edge('b', 'a')
    with pytest.raises(ValueError):
        compute_build_graph.order_build(g)
