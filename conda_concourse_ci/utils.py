import six


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
