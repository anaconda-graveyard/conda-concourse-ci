import fnmatch
import os

import six

import yaml

from conda_build.utils import HashableDict  # NOQA


def ensure_list(arg):
    if (isinstance(arg, six.string_types) or not hasattr(arg, '__iter__')):
        if arg:
            arg = [arg]
        else:
            arg = []
    return arg


def load_yaml_config_dir(platforms_dir, platform_filters):
    platforms = []
    for f in os.listdir(platforms_dir):
        if f.endswith('.yml') and any(fnmatch.fnmatch(f, pat) for pat in platform_filters):
            with open(os.path.join(platforms_dir, f)) as buff:
                platforms.append(yaml.load(buff, Loader=yaml.BaseLoader))
    return platforms
