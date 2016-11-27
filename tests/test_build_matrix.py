import os

from conda_concourse_ci import build_matrix as bm
from .utils import test_config_dir

def test_load_yaml_config_dir():
    platforms = bm.load_yaml_config_dir(os.path.join(test_config_dir, 'build_platforms.d'))
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
