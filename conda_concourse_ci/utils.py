import os
import six
import yaml


class HashableDict(dict):
    """use hashable frozen dictionaries for signatures of packages"""
    def __hash__(self):
        return hash(frozenset(self))


def ensure_list(arg):
    if (isinstance(arg, six.string_types) or not hasattr(arg, '__iter__')):
        if arg:
            arg = [arg]
        else:
            arg = []
    return arg


def load_yaml_config_dir(platforms_dir):
    platforms = []
    for f in os.listdir(platforms_dir):
        if f.endswith('.yml'):
            with open(os.path.join(platforms_dir, f)) as buff:
                platforms.append(yaml.load(buff))
    return platforms
