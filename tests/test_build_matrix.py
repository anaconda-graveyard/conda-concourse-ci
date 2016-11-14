import os

from conda_concourse_ci import build_matrix as bm

test_data_dir = os.path.join(os.path.dirname(__file__), 'data')


# def test_expand_build_matrix():
#     # python version specified; ignores matrix for python
#     configurations = list(bm.expand_build_matrix('python_version_specified',
#                                             repo_base_dir=test_data_dir))
#     assert len(configurations) == 1

#     # python version not specified; uses matrix for python
#     # (python 2 + python 3) = 2
#     configurations = list(bm.expand_build_matrix('python_test',
#                                             repo_base_dir=test_data_dir))
#     assert len(configurations) == 2

#     # (python 2 + python 3) = 2
#     configurations = list(bm.expand_build_matrix('python_numpy_no_xx',
#                                             repo_base_dir=test_data_dir))
#     assert len(configurations) == 2

#     # (python 2 + python 3) * (numpy 1.10 + 1.11) = 4
#     configurations = list(bm.expand_build_matrix('python_numpy_xx',
#                                             repo_base_dir=test_data_dir))
#     assert len(configurations) == 4


def test_load_platforms():
    platforms = bm.load_platforms(os.path.join(test_data_dir, 'build_platforms.d'))
    assert len(platforms) == 3
    assert 'label' in platforms[0]
    assert 'platform' in platforms[0]
    assert 'arch' in platforms[0]


def test_set_conda_env_vars():
    env_dict = {"TEST_VAR": "value",
                "NONE_VAR": None,
                "LIST_VAR": ["value"],
                "PREVIOUS_VAR": "something else"}
    os.environ['PREVIOUS_VAR'] = 'something'
    with bm.set_conda_env_vars(env_dict):
        assert 'TEST_VAR' in os.environ
        assert os.environ['TEST_VAR'] == 'value'
        assert 'NONE_VAR' in os.environ
        assert os.environ['NONE_VAR'] == ''
        assert 'LIST_VAR' in os.environ
        assert os.environ['LIST_VAR'] == 'value'
        assert 'PREVIOUS_VAR' in os.environ
        assert os.environ['PREVIOUS_VAR'] == 'something else'
    assert 'TEST_VAR' not in os.environ
    assert 'NONE_VAR' not in os.environ
    assert 'LIST_VAR' not in os.environ
    assert 'PREVIOUS_VAR' in os.environ
    assert os.environ['PREVIOUS_VAR'] == 'something'
