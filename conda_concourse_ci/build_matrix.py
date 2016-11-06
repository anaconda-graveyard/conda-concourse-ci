from __future__ import print_function, division
import contextlib
from itertools import product
import os

from conda_build.api import render
import six
import yaml


def load_platforms(platforms_dir):
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


def _filter_environment_with_metadata(build_recipe, version_dicts):
    def del_key(version_dicts, key):
        if key == 'python':
            key = 'py'
        elif key == 'numpy':
            key = 'npy'
        elif key == 'r-base':
            key = 'r'
        del version_dicts['CONDA_' + key.upper()]
        return version_dicts

    with set_conda_env_vars(version_dicts):
        metadata, _, _ = render(build_recipe)

    for name in (u'numpy', u'python', u'perl', u'lua', u'r-base'):
        for req in metadata.get_value('requirements/run'):
            if hasattr(req, 'decode'):
                req = req.decode('utf-8')
            req_parts = req.split(u' ')
            if req_parts[0] == name:
                # logic here: if a version is provided, then ignore the build matrix - except
                #   numpy.  If numpy has x.x, that is the only way that it is considered part
                #   of the build matrix.
                #
                # Break = keep the recipe (since we don't fall through to del_key for this name)
                if len(req_parts) > 1:
                    if name == 'numpy' and 'x.x' in req_parts:
                        break
                    # we have a version specified for something other than numpy.  This means
                    #    we are overriding our build matrix.  Do not consider this variable.
                    #    Ignore coverage because Python optimizes the continue out, and it is never
                    #    covered.
                    continue   # pragma: no cover
                # fall through for numpy when it does not have any associated x.x
                if name == 'numpy':
                    continue
                break
        else:
            version_dicts = del_key(version_dicts, name)

    return version_dicts


def expand_build_matrix(build_recipe, repo_base_dir):
    versions_file = os.path.join(repo_base_dir, 'versions.yml')
    with open(versions_file) as f:
        dicts = yaml.load(f)
    if (not os.path.isabs(build_recipe) and not
            os.path.isdir(os.path.join(os.getcwd(), build_recipe))):
        build_recipe = os.path.join(repo_base_dir, build_recipe)
    if os.path.isdir(build_recipe):
        dicts = _filter_environment_with_metadata(build_recipe, dicts)
    # ensure that all values are strings, not floats
    for k, v in dicts.items():
        dicts[k] = [str(x) for x in v]

    # http://stackoverflow.com/a/5228294/1170370
    # end result is a collection of dicts, like [{'CONDA_PY': 2.7, 'CONDA_NPY': 1.11},
    #                                            {'CONDA_PY': 3.5, 'CONDA_NPY': 1.11}]
    return (dict(six.moves.zip(dicts, x)) for x in product(*dicts.values()))
