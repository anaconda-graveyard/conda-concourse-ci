class HashableDict(dict):
    """use hashable frozen dictionaries for resources and resource types so that they can be in sets
    """
    def __hash__(self):
        return hash(frozenset(self))
