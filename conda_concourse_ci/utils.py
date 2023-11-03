import fnmatch
import os

import six

import yaml

from conda_build.utils import HashableDict  # NOQA
from jinja2 import Environment, FileSystemLoader


def ensure_list(arg):
    if isinstance(arg, six.string_types) or not hasattr(arg, "__iter__"):
        if arg:
            arg = [arg]
        else:
            arg = []
    return arg


def load_yaml_config_dir(platforms_dir, platform_filters, build_config_vars):
    platforms = []
    # for f in os.listdir(platforms_dir):
    #     if f.endswith('.yml') and any(fnmatch.fnmatch(f[:-len('.yml')], pat) for pat in platform_filters):
    #         with open(os.path.join(platforms_dir, f)) as buff:
    #             env = Environment(loader=DictLoader({'platform.yml': buff.read()}), trim_blocks=True,
    #                               lstrip_blocks=True)
    #             rendered = env.get_template('platform.yml').render(**build_config_vars)
    #             platforms.append(yaml.load(rendered, Loader=yaml.BaseLoader))
    print("Using the following c3i build config vars:\n{}".format(build_config_vars))
    for f in os.listdir(platforms_dir):
        if (
            f.endswith(".yml")
            and os.sep not in f
            and any(fnmatch.fnmatch(f[: -len(".yml")], pat) for pat in platform_filters)
        ):
            path = os.path.join(platforms_dir, f)
            env = Environment(
                loader=FileSystemLoader(os.path.dirname(path)),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            rendered = env.get_template(os.path.basename(path)).render(
                **build_config_vars
            )
            platforms.append(yaml.load(rendered, Loader=yaml.BaseLoader))

    return platforms
