"""
Classes for representing Concourse pipeline configuration items

These map to the schema's in https://concourse-ci.org/docs.html
"""


class Pipeline:
    """ configuration for a concourse pipeline. """
    # https://concourse-ci.org/pipelines.html
    jobs = []
    resources = []
    resource_types = []
    var_sources = []
    groups = []

    def add_job(self, name, plan=None, **kwargs):
        if plan is None:
            plan = []
        job = {"name": name, "plan": plan, **kwargs}
        self.jobs.append(job)

    def add_resource(self, name, type_, source, **kwargs):
        resource = {'name': name, 'type': type_, "source": source, **kwargs}
        self.resources.append(resource)

    def add_resource_type(self, name, type_, source, **kwargs):
        rtype = {'name': name, 'type': type_, "source": source, **kwargs}
        self.resource_types.append(rtype)

    def to_dict(self):
        out = {}
        attrs = ['jobs', 'resources', 'resource_types', 'var_sources', 'groups']
        for attr in attrs:
            items = getattr(self, attr)
            if not len(items):
                continue
            out[attr] = [v if isinstance(v, dict) else v.to_dict() for v in items]
        return out


class _DictBacked:
    """ Base class where attributes are stored in the _dict attribute """
    _dict = None

    def _ensure_dict_init(self):
        if self._dict is None:
            self.__dict__["_dict"] = {}

    def __getattr__(self, attr):
        self._ensure_dict_init()
        if attr not in self._dict:
            name = type(self).__name__
            raise AttributeError(f"'{name}' object has no attribute '{attr}'")
        return self._dict[attr]

    def __setattr__(self, attr, value):
        self._ensure_dict_init()
        self._dict[attr] = value

    def to_dict(self):
        return self._dict


class Resource(_DictBacked):
    """ configuration for a concourse resource. """
    # https://concourse-ci.org/resources.html

    def __init__(self, name, type_, source, **kwargs):
        self.name = name
        self.type = type_
        self.source = source
        for attr, value in kwargs.items():
            setattr(self, attr, value)


class ResourceType(_DictBacked):
    """ configuration for a concourse resource type. """
    # https://concourse-ci.org/resource-types.html

    def __init__(self, name, type_, source, **kwargs):
        self.name = name
        self.type = type_
        self.source = source
        for attr, value in kwargs.items():
            setattr(self, attr, value)


class Job(_DictBacked):
    """ configuration for a concourse job. """
    # https://concourse-ci.org/jobs.html

    def __init__(self, name, plan=None, **kwargs):
        self.name = name
        self.plan = plan
        if plan is None:
            self.plan = []
        for attr, value in kwargs.items():
            setattr(self, attr, value)
