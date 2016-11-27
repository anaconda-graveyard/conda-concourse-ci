from conda_concourse_ci.utils import ensure_list, HashableDict

def test_ensure_list():
    a = ensure_list('abc')
    assert a == ['abc']
    a = ensure_list(['abc', '123'])
    assert a == ['abc', '123']
    a = ensure_list(None)
    assert a == []

def test_hashable_dict_is_hashable():
    a = HashableDict(somevar='abc')
    hash(a)
