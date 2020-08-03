import logging
import os

import pytest

from conda_concourse_ci import cli


def test_argparse_input():
    # calling with no arguments goes to look at sys.argv, which is our arguments to py.test.
    with pytest.raises((SystemExit, NotImplementedError)):
        cli.main()


def test_submit(mocker):
    mocker.patch.object(cli.execute, 'submit')
    args = ['submit', 'frank']
    cli.main(args)
    cli.execute.submit.assert_called_once_with(base_name='frank', config_root_dir='frank',
                                               debug=False, pipeline_file='plan_director.yml',
                                               pipeline_name='{base_name} plan director',
                                               public=True, src_dir=os.getcwd(),
                                               subparser_name='submit', pass_throughs=[])


def test_submit_one_off(mocker):
    mocker.patch.object(cli.execute, 'submit_one_off')
    args = ['one-off', 'frank', 'bzip2', '--config-root-dir', '../config']
    cli.main(args)
    cli.execute.submit_one_off.assert_called_once_with(
        pipeline_label='frank',
        config_root_dir=mocker.ANY,
        debug=False,
        public=True,
        recipe_root_dir=os.getcwd(),
        subparser_name='one-off',
        folders=['bzip2'],
        channel=None,
        variant_config_files=None,
        output_dir=None,
        platform_filters=None,
        worker_tags=None,
        push_branch=False,
        destroy_pipeline=False,
        clobber_sections_file=None,
        append_sections_file=None,
        pass_throughs=[],
        skip_existing=True,
        use_lock_pool=False,
        use_repo_access=False,
        use_staging_channel=False,
        automated_pipeline=False,
        branches=None,
        stage_for_upload=False,
        commit_msg=None,
        pr_num=None,
        pr_file=None,
        repository=None,
    )


def test_submit_batch(mocker):
    mocker.patch.object(cli.execute, 'submit_batch')
    args = ['batch', 'batch_file.txt', '--config-root-dir', '../config']
    cli.main(args)
    cli.execute.submit_batch.assert_called_once_with(
        batch_file='batch_file.txt',
        recipe_root_dir=os.getcwd(),
        config_root_dir=mocker.ANY,
        max_builds=6,
        poll_time=120,
        build_lookback=500,
        label_prefix='autobot_',
        debug=False,
        public=True,
        subparser_name='batch',
        channel=None,
        variant_config_files=None,
        output_dir=None,
        platform_filters=None,
        worker_tags=None,
        clobber_sections_file=None,
        append_sections_file=None,
        use_lock_pool=False,
        use_repo_access=False,
        use_staging_channel=False,
        pass_throughs=[],
        skip_existing=True,
    )


def test_submit_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['submit']
        cli.main(args)


def test_bootstrap(mocker):
    mocker.patch.object(cli.execute, 'bootstrap')
    args = ['bootstrap', 'frank']
    cli.main(args)
    cli.execute.bootstrap.assert_called_once_with(base_name='frank', debug=False,
                                                  subparser_name='bootstrap', pass_throughs=[])


def test_bootstrap_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['bootstrap']
        cli.main(args)


def test_examine(mocker):
    mocker.patch.object(cli.execute, 'compute_builds')
    args = ['examine', 'frank']
    cli.main(args)
    cli.execute.compute_builds.assert_called_once_with(base_name='frank', debug=False, folders=[],
                                                       git_rev='HEAD', matrix_base_dir=mocker.ANY,
                                                       max_downstream=5, output_dir='../output',
                                                       path='.', steps=0, stop_rev=None,
                                                       subparser_name='examine', test=False,
                                                       channel=None, variant_config_files=None,
                                                       platform_filters=None, worker_tags=None,
                                                       pass_throughs=[], skip_existing=True)


def test_examine_without_base_name_raises():
    with pytest.raises(SystemExit):
        args = ['examine']
        cli.main(args)


# not sure what the right syntax for this is yet.  TODO.
@pytest.mark.xfail
def test_logger_sets_debug_level(mocker):
    mocker.patch.object(cli.execute, 'submit')
    cli.main(['--debug', 'submit', 'frank'])
    assert logging.getLogger().isEnabledFor(logging.DEBUG)


def test_bad_command_raises():
    with pytest.raises(SystemExit):
        cli.main(['llama'])
