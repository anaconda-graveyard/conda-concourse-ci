import argparse
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tarfile

import boto3
import yaml

import conda_concourse_ci
from .compute_build_graph import git_changed_recipes
from .execute import collect_tasks, write_tasks, graph_to_plan_and_tasks

log = logging.getLogger(__file__)
bootstrap_path = os.path.join(os.path.dirname(__file__), 'bootstrap')


def parse_args(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    sp = parser.add_subparsers(title='subcommands', dest='subparser_name')
    examine_parser = sp.add_parser('examine', help='examine path for changed recipes')
    examine_parser.add_argument('--folders',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree from git, specify folders to build")
    examine_parser.add_argument("path", default='.', nargs='?',
                        help="path in which to examine/build/test recipes")
    examine_parser.add_argument('--steps',
                        type=int,
                        help=("Number of downstream steps to follow in the DAG when "
                              "computing what to test.  Used for making sure that an "
                              "update does not break downstream packages.  Set to -1 "
                              "to follow the complete dependency tree."),
                        default=0),
    examine_parser.add_argument('--max-downstream',
                        default=5,
                        type=int,
                        help=("Limit the total number of downstream packages built.  Only applies "
                              "if steps != 0.  Set to -1 for unlimited."))
    examine_parser.add_argument('--git-rev',
                        default='HEAD',
                        help=('start revision to examine.  If stop not '
                              'provided, changes are THIS_VAL~1..THIS_VAL'))
    examine_parser.add_argument('--stop-rev',
                        default=None,
                        help=('stop revision to examine.  When provided,'
                              'changes are git_rev..stop_rev'))
    examine_parser.add_argument('--test', action='store_true',
                        help='test packages (instead of building them)')
    examine_parser.add_argument('--private', action='store_false',
                        help='hide build logs (overall graph still shown in Concourse web view)',
                        dest='public')
    examine_parser.add_argument('--matrix-base-dir',
                        help='path to matrix configuration, if different from recipe path')
    examine_parser.add_argument('--version', action='version',
        help='Show the conda-build version number and exit.',
        version='conda-concourse-ci %s' % conda_concourse_ci.__version__)

    submit_parser = sp.add_parser('submit', help="submit plan director to configured server")
    submit_parser.add_argument('--plan-director-path', default='plan_director.yml',
                               help="path to plan_director.yml file containing director plan")
    sp.add_parser('bootstrap', help="create default configuration files to help you start")
    return parser.parse_args(parse_this)


def get_current_git_rev(path):
    return subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                   cwd=path).rstrip()


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    checkout_ok = False
    try:
        git_current_rev = get_current_git_rev(path)
        subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
        checkout_ok = True
    except subprocess.CalledProcessError:    # pragma: no cover
        log.warn("failed to check out git revision.  "
                 "Source may not be a git repo (that's OK, "
                 "but you need to specify --folders.)")  # pragma: no cover
    yield
    if checkout_ok:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def submit(args):
    """submit task that will monitor changes and trigger other build tasks

    This gets the ball rolling.  Once submitted, you don't need to manually trigger
    builds.  This is creating the task that monitors git changes and triggers regeneration
    of the dynamic job.
    """
    root = os.path.dirname(args.plan_director_path)
    config_folder = os.path.join(root, 'config')
    config_path = os.path.join(config_folder, 'config.yml')
    with open(os.path.join(config_path)) as src:
        data = yaml.load(src)

    for root, dirnames, files in os.walk(config_folder):
        for f in files:
            local_path = os.path.join(root, f)
            remote_path = local_path.replace(config_folder, 'config')
            upload_to_s3(local_path, remote_path, bucket=data['aws-bucket'],
                         key_id=data['aws-key-id'], secret_key=data['aws-secret-key'],
                         region_name=data['aws-region-name'])

    # make sure we are logged in to the configured server
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'login',
                           '--concourse-url', data['concourse-url'],
                           '--username', data['concourse-user'],
                           '--password', data['concourse-password'],
                           '--team-name', data['concourse-team']])
    # set the new pipeline details
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'sp',
                           '-c', args.plan_director_path,
                           '-p', 'plan_director', '-n', '-l', config_path])
    # unpause the pipeline
    subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                           'up', '-p', 'plan_director'])
    # trigger the job to actually run
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'tj', '-j',
                           'plan_director/collect-tasks'])


def _copy_yaml_if_not_there(path):
    original = os.path.join(bootstrap_path, path)
    try:
        os.makedirs(os.path.dirname(path))
    except:
        pass
    # write config
    if not os.path.isfile(path):
        print("writing new file: ")
        print(path)
        shutil.copyfile(original, path)


def bootstrap():
    """Generate template files and folders to help set up CI for a new location"""
    _copy_yaml_if_not_there('config/config.yml')
    # create platform.d folders
    for run_type in ('build', 'test'):
        if not os.path.exists('config/{0}_platforms.d'.format(run_type)):
            _copy_yaml_if_not_there('config/{0}_platforms.d/example.yml'.format(run_type))
    if not os.path.exists('config/uploads.d'):
        _copy_yaml_if_not_there('config/uploads.d/anaconda-example.yml')
        _copy_yaml_if_not_there('config/uploads.d/scp-example.yml')
        _copy_yaml_if_not_there('config/uploads.d/custom-example.yml')
    # create basic versions.yml files
    _copy_yaml_if_not_there('config/versions.yml')
    # create initial plan that runs c3i to determine further plans
    #    This one is safe to overwrite, as it is dynamically generated.
    shutil.copyfile(os.path.join(bootstrap_path, 'plan_director.yml'), 'plan_director.yml')
    # advise user on what to edit and how to submit this job
    print("""Greetings, earthling.

Wrote bootstrap config files into 'config' folder.

Overview:
    - set your passwords and access keys in config/config.yml
    - edit target build and test platforms in config/*_platforms.d.  Note that 'connector' key is
      optional.
    - edit config/versions.yml to your liking.  Defaults should work out of the box.
    - Finally, submit this configuration with 'c3i submit'
""")


def archive_tasks_and_recipes(task_folder, recipe_root, recipe_folders, version):
    filename = 'tasks-and-recipes-{0}.tar.bz2'.format(version)
    with tarfile.TarFile(filename, 'w') as tar:
        tar.add(task_folder)
        for folder in recipe_folders:
            tar.add(os.path.join(recipe_root, folder))

    # this move into output is because that's the folder that concourse finds output in
    dest = os.path.join(task_folder, filename)
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(filename, dest)


def upload_to_s3(local_location, remote_location, bucket, key_id, secret_key,
                 region_name='us-west-2'):
    s3 = boto3.resource('s3', aws_access_key_id=key_id,
                        aws_secret_access_key=secret_key,
                        region_name=region_name)

    bucket = s3.Bucket(bucket)
    bucket.upload_file(local_location, remote_location)


def build_cli(args):
    checkout_rev = args.stop_rev or args.git_rev
    folders = args.folders
    if not folders:
        folders = git_changed_recipes(args.git_rev, args.stop_rev, git_root=args.path)
    if not folders:
        print("No folders specified to build, and nothing changed in git.  Exiting.")
        return
    matrix_base_dir = args.matrix_base_dir or args.path

    with checkout_git_rev(checkout_rev, args.path):
        task_graph = collect_tasks(args.path, folders=folders, steps=args.steps,
                                   max_downstream=args.max_downstream, test=args.test,
                                   matrix_base_dir=matrix_base_dir)
        try:
            repo_commit = get_current_git_rev(args.path)
        except subprocess.CalledProcessError:
            repo_commit = 'master'

    # this file is created and updated by the semver resource
    with open('version/version') as f:
        version = f.read().rstrip()
    plan, tasks = graph_to_plan_and_tasks(os.path.abspath(args.path), task_graph,
                                          version, matrix_base_dir=matrix_base_dir,
                                          public=args.public)

    output_folder = 'output'
    write_tasks(tasks, output_folder)
    try:
        os.makedirs(output_folder)
    except:
        pass
    with open(os.path.join(matrix_base_dir, 'config.yml')) as src:
        data = yaml.load(src)
    data['recipe-repo-commit'] = repo_commit
    data['version'] = version
    with open(os.path.join(output_folder, 'plan.yml'), 'w') as f:
        f.write(plan)
    print(os.getcwd())
    with open(os.path.join('config-out', 'config.yml'), 'w') as f:
        yaml.dump(data, f)
    archive_tasks_and_recipes(output_folder, args.path, folders, version)


def main(args=None):
    if not args:
        args = parse_args()
    else:
        args = parse_args(args)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.subparser_name == 'submit':
        submit(args)
    elif args.subparser_name == 'bootstrap':
        bootstrap()
    elif args.subparser_name == 'examine':
        build_cli(args)
    else:
        raise ValueError("Unrecognized subcommand to c3i: %s", args.subparser_name)
