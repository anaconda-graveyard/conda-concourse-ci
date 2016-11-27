import six


class HashableDict(dict):
    """use hashable frozen dictionaries for resources and resource types so that they can be in sets
    """
    def __hash__(self):
        return hash(frozenset(self))


def ensure_list(arg):
    if (isinstance(arg, six.string_types) or not hasattr(arg, '__iter__')):
        if arg:
            arg = [arg]
        else:
            arg = []
    return arg
