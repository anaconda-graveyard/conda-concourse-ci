import os

import pytest
from pytest_mock import mocker

import conda_concourse_ci.compute_build_graph
from .utils import (testing_workdir, testing_git_repo, testing_graph, testing_conda_resolve,
                    testing_metadata, make_recipe, test_data_dir, default_meta, build_dict)

graph_data_dir = os.path.join(test_data_dir, 'graph_data')


def test_dirty(testing_graph):
    assert (conda_concourse_ci.compute_build_graph.dirty(testing_graph) ==
            {'b': build_dict})


def test_get_build_deps(testing_metadata):
    assert (conda_concourse_ci.compute_build_graph.get_build_deps(testing_metadata) ==
            {'build_requirement': "any"})


def test_get_run_test_deps(testing_metadata):
    assert (conda_concourse_ci.compute_build_graph.get_run_test_deps(testing_metadata) ==
            {'run_requirement': "1.0", 'test_requirement': "any"})


def test_construct_graph():
    g = conda_concourse_ci.compute_build_graph.construct_graph(graph_data_dir, 'some_os', 'somearch',
                                                               label='linux', folders=('b'),
                                                               matrix_base_dir=test_data_dir)
    assert set(g.nodes()) == set(['a-0-linux', 'b-0-linux', 'c-0-linux', 'd-0-linux'])
    assert not any([g.node[dirname]['build'] for dirname in ('a-0-linux', 'c-0-linux',
                                                             'd-0-linux')])
    assert g.node['b-0-linux']['build']
    assert set(g.edges()) == set([('b-0-linux', 'a-0-linux'), ('c-0-linux', 'b-0-linux'),
                                  ('d-0-linux', 'c-0-linux')])


def test_construct_graph_git_rev(testing_git_repo):
    g = conda_concourse_ci.compute_build_graph.construct_graph(testing_git_repo, 'some_os',
                                                               'somearch', label='linux',
                                                               matrix_base_dir=test_data_dir)
    assert set(g.nodes()) == set(['test_dir_3-0-linux', 'test_dir_2-0-linux', 'test_dir_1-0-linux'])
    assert g.node['test_dir_3-0-linux']['build']
    assert not any([g.node[dirname]['build'] for dirname in ('test_dir_1-0-linux',
                                                             'test_dir_2-0-linux')])
    assert set(g.edges()) == set([('test_dir_2-0-linux', 'test_dir_1-0-linux'),
                                  ('test_dir_3-0-linux', 'test_dir_2-0-linux')])
    g = conda_concourse_ci.compute_build_graph.construct_graph(testing_git_repo, 'some_os',
                                                               'somearch', label='linux',
                                                               git_rev="HEAD@{2}", stop_rev="HEAD",
                                                               matrix_base_dir=test_data_dir)
    assert set(g.nodes()) == set(['test_dir_3-0-linux', 'test_dir_2-0-linux', 'test_dir_1-0-linux'])
    assert all([g.node[dirname]['build'] for dirname in ('test_dir_2-0-linux',
                                                         'test_dir_3-0-linux')])
    assert set(g.edges()) == set([('test_dir_2-0-linux', 'test_dir_1-0-linux'),
                                  ('test_dir_3-0-linux', 'test_dir_2-0-linux')])


def test_construct_graph_relative_path(testing_git_repo):
    g = conda_concourse_ci.compute_build_graph.construct_graph('.', 'some_os', 'somearch',
                                                               label='linux',
                                                               matrix_base_dir=test_data_dir)
    assert set(g.nodes()) == set(['test_dir_3-0-linux', 'test_dir_2-0-linux', 'test_dir_1-0-linux'])
    assert g.node['test_dir_3-0-linux']['build']
    assert not any([g.node[dirname]['build'] for dirname in ('test_dir_1-0-linux',
                                                             'test_dir_2-0-linux')])
    assert set(g.edges()) == set([('test_dir_2-0-linux', 'test_dir_1-0-linux'),
                                  ('test_dir_3-0-linux', 'test_dir_2-0-linux')])


def test_platform_specific_graph():
    g = conda_concourse_ci.compute_build_graph.construct_graph(graph_data_dir, 'win', 32,
                                                               label='linux', folders=('a'),
                                                               deps_type='run_test',
                                                               matrix_base_dir=test_data_dir)
    assert set(g.edges()) == set([('a-0-linux', 'c-0-linux'), ('b-0-linux', 'c-0-linux'),
                                  ('c-0-linux', 'd-0-linux')])
    g = conda_concourse_ci.compute_build_graph.construct_graph(graph_data_dir, 'win', 64,
                                                               label='linux', folders=('a'),
                                                               deps_type='run_test',
                                                               matrix_base_dir=test_data_dir)
    assert set(g.edges()) == set([('a-0-linux', 'd-0-linux'), ('a-0-linux', 'c-0-linux'),
                                  ('b-0-linux', 'c-0-linux'), ('c-0-linux', 'd-0-linux')])


def test_run_test_graph():
    g = conda_concourse_ci.compute_build_graph.construct_graph(graph_data_dir, 'some_os', 'somearch',
                                                               label='linux', folders=('d'),
                                                               deps_type='run_test',
                                                               matrix_base_dir=test_data_dir)
    assert set(g.nodes()) == set(['a-0-linux', 'b-0-linux', 'c-0-linux', 'd-0-linux'])
    assert set(g.edges()) == set([('b-0-linux', 'c-0-linux'), ('c-0-linux', 'd-0-linux')])


def test_git_changed_recipes_head(testing_git_repo):
    assert (conda_concourse_ci.compute_build_graph.git_changed_recipes('HEAD') ==
            ['test_dir_3'])


def test_git_changed_recipes_earlier_rev(testing_git_repo):
    assert (conda_concourse_ci.compute_build_graph.git_changed_recipes('HEAD@{1}') ==
            ['test_dir_2'])


def test_git_changed_recipes_rev_range(testing_git_repo):
    assert (conda_concourse_ci.compute_build_graph.git_changed_recipes('HEAD@{3}', 'HEAD@{1}') ==
            ['test_dir_1', 'test_dir_2'])


def test_upstream_dependencies_needing_build(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    conda_concourse_ci.compute_build_graph._installable.return_value = False
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_buildable')
    conda_concourse_ci.compute_build_graph._buildable.return_value = True
    conda_concourse_ci.compute_build_graph.upstream_dependencies_needing_build(
        testing_graph, testing_conda_resolve)
    assert conda_concourse_ci.compute_build_graph.dirty(testing_graph) == {'a': build_dict,
                                                                        'b': build_dict}


def test_buildable(monkeypatch, testing_metadata):
    monkeypatch.chdir(test_data_dir)
    testing_metadata.meta['package']['name'] = 'somepackage'
    testing_metadata.meta['package']['version'] = 'any'
    assert conda_concourse_ci.compute_build_graph._buildable(testing_metadata)
    testing_metadata.meta['package']['version'] = '1.2.8'
    assert conda_concourse_ci.compute_build_graph._buildable(testing_metadata)
    testing_metadata.meta['package']['version'] = '5.2.9'
    assert not conda_concourse_ci.compute_build_graph._buildable(testing_metadata)
    testing_metadata.meta['package']['name'] = 'not_a_package'
    assert not conda_concourse_ci.compute_build_graph._buildable(testing_metadata)


def test_installable(testing_conda_resolve, testing_metadata):
    testing_metadata.meta['package']['name'] = 'a'
    testing_metadata.meta['package']['version'] = '920'
    assert conda_concourse_ci.compute_build_graph._installable(testing_metadata,
                                                               testing_conda_resolve)
    testing_metadata.meta['package']['version'] = '921'
    assert not conda_concourse_ci.compute_build_graph._installable(testing_metadata,
                                                                   testing_conda_resolve)
    testing_metadata.meta['package']['name'] = 'f'
    testing_metadata.meta['package']['version'] = '920'
    assert not conda_concourse_ci.compute_build_graph._installable(testing_metadata,
                                                                   testing_conda_resolve)


def test_expand_run_no_up_or_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_buildable')

    # all packages are installable in the default index
    conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve, 'build')
    assert len(conda_concourse_ci.compute_build_graph.dirty(testing_graph)) == 1


def test_expand_run_step_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, 'upstream_dependencies_needing_build')
    conda_concourse_ci.compute_build_graph.upstream_dependencies_needing_build.return_value = set(['b'])
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build', steps=1)
    assert dirty == {'b': build_dict, 'c': build_dict}


def test_expand_run_two_steps_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, 'upstream_dependencies_needing_build')
    conda_concourse_ci.compute_build_graph.upstream_dependencies_needing_build.return_value = set(['b'])
    # second expansion - one more layer out
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build', steps=2)
    assert dirty == {'b': build_dict, 'c': build_dict, 'd': build_dict}


def test_expand_run_all_steps_down(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, 'upstream_dependencies_needing_build')
    conda_concourse_ci.compute_build_graph.upstream_dependencies_needing_build.return_value = set(['b'])
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build', steps=-1)
    assert dirty == {'b': build_dict, 'c': build_dict, 'd': build_dict, 'e': build_dict}


def test_expand_run_all_steps_down_with_max(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, 'upstream_dependencies_needing_build')
    conda_concourse_ci.compute_build_graph.upstream_dependencies_needing_build.return_value = set(['b'])
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build', steps=-1, max_downstream=1)
    assert dirty == {'b': build_dict, 'c': build_dict}


def test_expand_raises_when_neither_installable_or_buildable(mocker, testing_graph,
                                                             testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_buildable')
    conda_concourse_ci.compute_build_graph._installable.return_value = False
    conda_concourse_ci.compute_build_graph._buildable.return_value = False
    with pytest.raises(ValueError):
        conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                       'build')


def test_expand_run_build_non_installable_prereq(mocker, testing_graph, testing_conda_resolve):
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_installable')
    mocker.patch.object(conda_concourse_ci.compute_build_graph, '_buildable')
    conda_concourse_ci.compute_build_graph._installable.return_value = False
    conda_concourse_ci.compute_build_graph._buildable.return_value = True
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build')
    assert dirty == {'a': build_dict, 'b': build_dict}
    dirty = conda_concourse_ci.compute_build_graph.expand_run(testing_graph, testing_conda_resolve,
                                                           'build', steps=1)
    assert dirty == {'a': build_dict, 'b': build_dict, 'c': build_dict}



def test_order_build_no_filter(testing_graph):
    g, order = conda_concourse_ci.compute_build_graph.order_build(testing_graph,
                                                               filter_dirty=False)
    assert order == ['a', 'b', 'c', 'd', 'e']

    with pytest.raises(ValueError):
        testing_graph.add_edge('a', 'd')
        conda_concourse_ci.compute_build_graph.order_build(testing_graph, filter_dirty=False)


def test_order_build(testing_graph):
    g, order = conda_concourse_ci.compute_build_graph.order_build(testing_graph)
    assert order == ['b']


def test_get_base_folders(testing_workdir):
    make_recipe('some_recipe')
    os.makedirs('not_a_recipe')
    with open(os.path.join('not_a_recipe', 'testfile'), 'w') as f:
        f.write('weee')

    changed_files = ['some_recipe/meta.yaml', 'not_a_recipe/testfile']
    assert (conda_concourse_ci.compute_build_graph._get_base_folders(testing_workdir, changed_files) ==
            ['some_recipe'])
    assert not conda_concourse_ci.compute_build_graph._get_base_folders(testing_workdir, changed_files[1:])
