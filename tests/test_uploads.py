import os

from conda_concourse_ci import uploads

import yaml
from conda_build import conda_interface

from .utils import test_config_dir, default_worker


def test_base_task():
    task = uploads._base_task('steve')
    assert task['task'] == 'steve'
    assert 'run' in task['config']
    assert len(task['config']['inputs']) == 1
    assert task['config']['inputs'][0]['name'] == 'output-artifacts'


def test_upload_anaconda():
    tasks = uploads.upload_anaconda('steve', 'abc')
    assert len(tasks) == 1
    task = tasks[0]
    assert task['config']['run']['path'] == 'anaconda'
    assert task['config']['run']['args'][-1] == 'steve'


def test_upload_anaconda_with_user():
    tasks = uploads.upload_anaconda('steve', 'abc', user="llama")
    assert {'--user', 'llama'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_anaconda_with_label():
    tasks = uploads.upload_anaconda('steve', 'abc', label='dev')
    assert {'--label', 'dev'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_anaconda_with_user_and_label():
    tasks = uploads.upload_anaconda('steve', 'abc', user='llama', label='dev')
    assert {'--user', 'llama', '--label', 'dev'}.issubset(set(tasks[0]['config']['run']['args']))


def test_upload_scp():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    tasks = uploads.upload_scp(package_path='steve', server='someserver',
                               destination_path='abc/123', auth_dict={'user': 'llama',
                                                                      'key_file': 'my_key'},
                               worker=default_worker, config_vars=config_vars)

    assert tasks[0]['config']['run']['path'] == 'scp'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[0]['config']['run']['args']))
    assert {'llama@someserver:abc/123'}.issubset(set(tasks[0]['config']['run']['args']))
    assert tasks[1]['config']['run']['path'] == 'ssh'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[1]['config']['run']['args']))
    assert {'chmod 664 abc/123/steve'}.issubset(set(tasks[1]['config']['run']['args']))
    assert tasks[2]['config']['run']['path'] == 'ssh'
    assert {'-i', 'config/uploads.d/my_key'}.issubset(set(tasks[2]['config']['run']['args']))
    assert {'conda index abc/123'}.issubset(set(tasks[2]['config']['run']['args']))


def test_upload_scp_with_port():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    tasks = uploads.upload_scp(package_path='steve', server='someserver',
                               destination_path='abc/123', auth_dict={'user': 'llama',
                                                                      'key_file': 'my_key'},
                               worker=default_worker, config_vars=config_vars, port=33)

    assert {'-P', 33}.issubset(set(tasks[0]['config']['run']['args']))
    assert {'-p', 33}.issubset(set(tasks[1]['config']['run']['args']))
    assert {'-p', 33}.issubset(set(tasks[2]['config']['run']['args']))


def test_upload_command_string():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    tasks = uploads.upload_commands(package_path='steve', commands='abc {package}',
                                    config_vars=config_vars)

    assert tasks[0]['config']['run']['path'] == 'abc'
    assert tasks[0]['config']['run']['args'] == ['steve']


def test_upload_command_list():
    with open(os.path.join(test_config_dir, 'config.yml')) as f:
        config_vars = yaml.load(f)
    tasks = uploads.upload_commands(package_path='steve', commands=['abc {package}', 'wee'],
                                    config_vars=config_vars)
    assert tasks[0]['config']['run']['path'] == 'abc'
    assert tasks[0]['config']['run']['args'] == ['steve']
    assert tasks[1]['config']['run']['path'] == 'wee'


def test_get_upload_tasks(mocker, testing_graph):
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
    uploads.get_upload_tasks(testing_graph, 'b-linux',
                             os.path.join(test_config_dir, 'uploads.d'),
                             config_vars, commit_id='abc123')
    subdir = conda_interface.subdir
    uploads.upload_anaconda.assert_called_once_with(
        'output-artifacts/abc123/{}/b-1.0-hd248202_0.tar.bz2'.format(subdir),
        token='abc')
    uploads.upload_scp.assert_called_once_with(
        package_path='output-artifacts/abc123/{}/b-1.0-hd248202_0.tar.bz2'.format(subdir),
        worker=default_worker, config_vars=config_vars, server='localhost')
    uploads.upload_commands.assert_called_once_with(
        'output-artifacts/abc123/{}/b-1.0-hd248202_0.tar.bz2'.format(subdir),
        config_vars=config_vars, commands='weee')

    # uploads.load_yaml_config_dir.return_value = [{'bad': 'abc'}]
    # with pytest.raises(ValueError):
    #     uploads.get_upload_tasks(testing_graph, 'somedir',
    #                             os.path.join(test_config_dir, 'uploads.d'),
    #                             config_vars, commit_id='abc123')
