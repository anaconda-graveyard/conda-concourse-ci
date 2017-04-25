import os

from conda_concourse_ci import uploads

import pytest
import yaml

from .utils import test_config_dir, default_worker


def test_get_upload_job_name():
    assert uploads.get_upload_job_name('frank', 'steve') == 'frank-steve'


def test_config_resources_and_task():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    types, resources, tasks = uploads._config_resources_and_task(config_vars)

    assert len(types) == 1
    # ensure that each type is hashable, because we keep a set of them
    hash(types[0])

    assert len(resources) == 1
    # ensure that each resource is hashable, because we keep a set of them
    hash(resources[0])

    assert len(tasks) == 1
    assert tasks[0]['get'] == 's3-config-base'


def test_base_task():
    task = uploads._base_task('frank', 'steve')
    assert task['task'] == 'steve'
    assert 'run' in task['config']
    assert len(task['config']['inputs']) == 1
    assert task['config']['inputs'][0]['name'] == 'frank'


def test_upload_anaconda():
    resource_types, resources, tasks = uploads.upload_anaconda("frank", 'steve', 'abc')
    assert not resource_types
    assert not resources
    assert len(tasks) == 1
    task = tasks[0]
    assert task['config']['run']['path'] == 'anaconda'
    assert task['config']['run']['args'][-1] == 'frank/steve'


def test_upload_anaconda_with_user():
    resource_types, resources, tasks = uploads.upload_anaconda("frank", 'steve', 'abc',
                                                               user="llama")
    assert {'--user', 'llama'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_anaconda_with_label():
    resource_types, resources, tasks = uploads.upload_anaconda("frank", 'steve', 'abc', label='dev')
    assert {'--label', 'dev'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_anaconda_with_user_and_label():
    resource_types, resources, tasks = uploads.upload_anaconda("frank", 'steve', 'abc',
                                                               user='llama', label='dev')
    assert {'--user', 'llama', '--label', 'dev'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_scp():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    resource_types, resources, tasks = uploads.upload_scp(s3_resource_name='frank',
                                                          package_path='steve',
                                                          server='someserver',
                                                          destination_path='abc/123',
                                                          auth_dict={'user': 'llama',
                                                                     'key_file': 'my_key'},
                                                          worker=default_worker,
                                                          config_vars=config_vars)
    assert len(resource_types) == 1
    hash(resource_types[0])
    assert resource_types[0]['source']['repository'] == "18fgsa/s3-resource-simple"

    assert len(resources) == 1
    hash(resources[0])
    assert resources[0]['source']['bucket'] == config_vars['aws-bucket']

    assert tasks[0]['get'] == 's3-config-base'
    assert tasks[1]['config']['run']['path'] == 'scp'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[1]['config']['run']['args']))
    assert {'llama@someserver:abc/123'}.issubset(set(tasks[1]['config']['run']['args']))
    assert tasks[2]['config']['run']['path'] == 'ssh'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[2]['config']['run']['args']))
    assert {'chmod 664 abc/123/steve'}.issubset(set(tasks[2]['config']['run']['args']))
    assert tasks[3]['config']['run']['path'] == 'ssh'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[3]['config']['run']['args']))
    assert {'conda index abc/123'}.issubset(set(tasks[3]['config']['run']['args']))


def test_upload_scp_with_port():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    resource_types, resources, tasks = uploads.upload_scp(s3_resource_name='frank',
                                                          package_path='steve',
                                                          server='someserver',
                                                          destination_path='abc/123',
                                                          auth_dict={'user': 'llama',
                                                                     'key_file': 'my_key'},
                                                          worker=default_worker,
                                                          config_vars=config_vars,
                                                          port=33)

    assert {'-P', 33}.issubset(set(tasks[1]['config']['run']['args']))
    assert {'-p', 33}.issubset(set(tasks[2]['config']['run']['args']))
    assert {'-p', 33}.issubset(set(tasks[3]['config']['run']['args']))


def test_upload_command_string():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    resource_types, resources, tasks = uploads.upload_commands(s3_resource_name='frank',
                                                               package_path='steve',
                                                               commands='abc {package}',
                                                               config_vars=config_vars)
    assert len(resource_types) == 1
    hash(resource_types[0])
    assert resource_types[0]['source']['repository'] == "18fgsa/s3-resource-simple"

    assert len(resources) == 1
    hash(resources[0])
    assert resources[0]['source']['bucket'] == config_vars['aws-bucket']

    assert tasks[0]['get'] == 's3-config-base'
    assert tasks[1]['config']['run']['path'] == 'abc'
    assert tasks[1]['config']['run']['args'] == ['frank/steve']


def test_upload_command_list():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    resource_types, resources, tasks = uploads.upload_commands(s3_resource_name='frank',
                                                               package_path='steve',
                                                               commands=['abc {package}',
                                                                         'wee'],
                                                               config_vars=config_vars)
    assert tasks[1]['config']['run']['path'] == 'abc'
    assert tasks[1]['config']['run']['args'] == ['frank/steve']
    assert tasks[2]['config']['run']['path'] == 'wee'


def test_get_upload_tasks(mocker):
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    mocker.patch.object(uploads, 'load_yaml_config_dir')
    uploads.load_yaml_config_dir.return_value = [{'token': 'abc'},
                                                 {'server': 'localhost'},
                                                 {'commands': 'weee'}]
    mocker.patch.object(uploads, 'upload_anaconda')
    uploads.upload_anaconda.return_value = [], [], []
    mocker.patch.object(uploads, 'upload_scp')
    uploads.upload_scp.return_value = [], [], []
    mocker.patch.object(uploads, 'upload_commands')
    uploads.upload_commands.return_value = [], [], []
    types, resources, upload_tasks = uploads.get_upload_tasks('frank', 'steve', 'somedir',
                                                              default_worker,
                                                              config_vars=config_vars)
    uploads.upload_anaconda.assert_called_once_with('frank', 'steve', token='abc')
    uploads.upload_scp.assert_called_once_with(s3_resource_name='frank', package_path='steve',
                                               worker=default_worker, config_vars=config_vars,
                                               server='localhost')
    uploads.upload_commands.assert_called_once_with('frank', 'steve', config_vars=config_vars,
                                                    commands='weee')

    uploads.load_yaml_config_dir.return_value = [{'bad': 'abc'}]
    with pytest.raises(ValueError):
        types, resources, upload_tasks = uploads.get_upload_tasks('frank', 'steve', 'somedir',
                                                                  default_worker,
                                                                  config_vars=config_vars)
