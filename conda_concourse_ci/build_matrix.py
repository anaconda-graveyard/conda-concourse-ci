from __future__ import print_function, division
import contextlib
from itertools import product
import os

import six
import yaml


def load_yaml_config_dir(platforms_dir):
    platforms = []
    for f in os.listdir(platforms_dir):
        if f.endswith('.yml'):
            with open(os.path.join(platforms_dir, f)) as buff:
                platforms.append(yaml.load(buff))
    return platforms


@contextlib.contextmanager
def set_conda_env_vars(env_dict):
    backup_dict = os.environ.copy()
    for env_var, value in env_dict.items():
        if isinstance(value, list):
            value = value[0]
        if not value:
            value = ""
        os.environ[env_var] = str(value)

    yield

    # ensure that cruft isn't left
    for key in env_dict:
        if key not in backup_dict:
            backup_dict[key] = None

    for env_var, value in backup_dict.items():
        if not value:
            del os.environ[env_var]
        else:
            os.environ[env_var] = value


def expand_build_matrix(build_recipe, repo_base_dir):
    versions_file = os.path.join(repo_base_dir, 'versions.yml')
    with open(versions_file) as f:
        dicts = yaml.load(f)
    if (not os.path.isabs(build_recipe) and not
            os.path.isdir(os.path.join(os.getcwd(), build_recipe))):
        build_recipe = os.path.join(repo_base_dir, build_recipe)
    # ensure that all values are strings, not floats
    for k, v in dicts.items():
        dicts[k] = [str(x) for x in v]

    # http://stackoverflow.com/a/5228294/1170370
    # end result is a collection of dicts, like [{'CONDA_PY': 2.7, 'CONDA_NPY': 1.11},
    #                                            {'CONDA_PY': 3.5, 'CONDA_NPY': 1.11}]
    return (dict(six.moves.zip(dicts, x)) for x in product(*dicts.values()))
