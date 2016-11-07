import argparse
import contextlib
import logging
import os
import subprocess
import sys

import yaml

import conda_concourse_ci
from .compute_build_graph import git_changed_recipes
from .execute import collect_tasks, write_tasks, graph_to_plan_and_tasks

log = logging.getLogger(__file__)


def parse_args(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default='.',
                        help="path in which to examine/build/test recipes")
    package_specs = parser.add_mutually_exclusive_group()
    package_specs.add_argument('--packages', '-p',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree from git, specify packages to build")
    parser.add_argument('--steps',
                        type=int,
                        help=("Number of downstream steps to follow in the DAG when "
                              "computing what to test.  Used for making sure that an "
                              "update does not break downstream packages.  Set to -1 "
                              "to follow the complete dependency tree."),
                        default=0),
    parser.add_argument('--max-downstream',
                        default=5,
                        type=int,
                        help=("Limit the total number of downstream packages built.  Only applies "
                              "if steps != 0.  Set to -1 for unlimited."))
    parser.add_argument('--git-rev',
                        default='HEAD',
                        help=('start revision to examine.  If stop not '
                              'provided, changes are THIS_VAL~1..THIS_VAL'))
    parser.add_argument('--stop-rev',
                        default=None,
                        help=('stop revision to examine.  When provided,'
                              'changes are git_rev..stop_rev'))
    parser.add_argument('--test', action='store_true',
                        help='test packages (instead of building them)')
    parser.add_argument('--private', action='store_false',
                        help='hide build logs (overall graph still shown in Concourse web view)',
                        dest='public')
    parser.add_argument('--matrix-base-dir',
                        help='path to matrix configuration, if different from recipe path')
    parser.add_argument('--version', action='version',
        help='Show the conda-build version number and exit.',
        version='conda-concourse-ci %s' % conda_concourse_ci.__version__)
    parser.add_argument('--debug', action='store_true')

    sp = parser.add_subparsers(title='subcommands', dest='subparser_name')
    submit_parser = sp.add_parser('submit', help="submit plan director to configured server")
    submit_parser.add_argument('--plan-director-path', default='plan_director.yml',
                               help="path to plan_director.yml file containing director plan")
    sp.add_parser('bootstrap', help="create default configuration files to help you start")
    return parser.parse_args(parse_this)


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    git_current_rev = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                              cwd=path).rstrip()
    subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
    try:
        yield
    except:    # pragma: no cover
        raise  # pragma: no cover
    finally:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def submit(args):
    """submit task that will monitor changes and trigger other build tasks

    This gets the ball rolling.  Once submitted, you don't need to manually trigger
    builds.  This is creating the task that monitors git changes and triggers regeneration
    of the dynamic job.
    """
    config_path = os.path.join(os.path.dirname(args.plan_director_path), 'config', 'config.yml')
    config = yaml.load(open(config_path))
    # make sure we are logged in to the configured server
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'login',
                           '--concourse-url', config['concourse-url'],
                           '--username', config['concourse-user'],
                           '--password', config['concourse-password'],
                           '--team-name', config['concourse-team']])
    # set the new pipeline details
    subprocess.check_call(['fly', '-t', 'conda-concourse-server', 'sp',
                           '-c', args.plan_director_path,
                           '-p', 'plan_director', '-n', '-l', config_path])
    # unpause the pipeline
    subprocess.check_call(['fly', '-t', 'conda-concourse-server',
                           'up', '-p', 'plan_director'])


_initial_config_yml = {
    'aws-bucket': 'your-bucket-name',
    'aws-key-id': 'your-aws-key-id',
    'aws-secret-key': 'your-aws-secret-key',
    'concourse-url': 'your-concourse-server-url',
    'concourse-team': 'your-concourse-team',
    'concourse-user': 'your-concourse-user',
    'concourse-password': 'your-concourse-password',
    'recipe-repo': 'your-recipe-repo',
    # TODO: these need to be dynamically definable based on PR info
    'recipe-repo-commit': 'master',
}

_resource_types = [
    {'name': 'concourse-pipeline',
     'type': 'docker-image',
     'source': {
         'repository': 'robdimsdale/concourse-pipeline-resource',
         'tag': 'latest-final'
     }
     },
    {'name': 's3-simple',
     'type': 'docker-image',
     'source': {'repository': '18fgsa/s3-resource-simple'}
     },
]

_resources = [
    {'name': 'c3i-source',
     'type': 'git',
     'source': {'uri': 'https://github.com/msarahan/conda-concourse-ci.git'}
     },
    {'name': 's3-tasks',
     'type': 's3-simple',
     'bucket': '{{aws-bucket}}',
     'access_key_id': '{{aws-key-id}}',
     'secret_access_key': '{{aws-secret-key}}',
     'options': [
         "--exclude '*'",
         "--include 'ci-tasks'"
     ]
     },
    {'name': 's3-config',
     'type': 's3-simple',
     'bucket': '{{aws-bucket}}',
     'access_key_id': '{{aws-key-id}}',
     'secret_access_key': '{{aws-secret-key}}',
     'options': [
         "--exclude '*'",
         "--include 'config'"
     ]
     },
    {'name': 'execute-tasks',
     'type': 'concourse-pipeline',
     'source': {
         'target': '{{concourse-url}}',
         'teams': [
             {'name': '{{concourse-team}}',
              'username': '{{concourse-user}}',
              'password': '{{concourse-password}}'
              }
         ]
     },
     }
]

_jobs = [
    {'name': 'collect-tasks',
     'public': True,
     'serial': True,
     'plan': [
         {'get': 'c3i-source'},
         {'get': 's3-config'},
         {'task': 'install-run-c3i',
          'config': {
              'platform': 'linux',
              'image_resource': {
                  'type': 'docker-image',
                  'source': {'repository': 'busybox'}
              },
              'inputs': [
                  {'name': 's3-config/config'}
              ],
              'run': {
                  'path': 'c3i .'
              }
          }
          },
         {'put': 's3-tasks'},
         {'put': 'execute-tasks',
          'params': {
              'pipelines': [
                  {'name': 'execute',
                   'team': '{{concourse-team}}',
                   'config_file': 's3-tasks/ci-tasks/plan.yml',
                   'vars_files': ['s3-config/config/config.yml'],
                   }
              ]
          }}
     ]
     }

]

_bootstrap_plan_yml = {
    'resource_types': _resource_types,
    'resources': _resources,
    'jobs': _jobs
}

_initial_version_yml = {
    'CONDA_PY': ['2.7', '3.5'],
    'CONDA_NPY': ['1.11'],
    'CONDA_PERL': ['5.20'],
    'CONDA_LUA': ['5.2'],
    'CONDA_R': ['3.3'],
}

_example_platform = {
    'label': 'centos5-64',
    'platform': 'linux',
    'arch': '64',
    # this key is optional
    'connector': {
        'image_resource':
        {'type': 'docker-image',
         'source': {'repository': 'busybox'}}}
}


def bootstrap():
    """Generate template files and folders to help set up CI for a new location"""
    try:
        os.makedirs('config')
    except:
        pass
    # write config
    with open('config/config.yml', 'w') as f:
        yaml.dump(_initial_config_yml, f)
    # create platform.d folders
    for run_type in ('build', 'test'):
        folder = os.path.join('config', '{0}_platforms.d'.format(run_type))
        try:
            os.makedirs(folder)
        except:
            pass
        with open(os.path.join(folder, 'example.yml'), 'w') as f:
            yaml.dump(_example_platform, f)
    # create basic versions.yml files
    with open('config/versions.yml', 'w') as f:
        yaml.dump(_initial_version_yml, f)
    # create initial plan that runs c3i to determine further plans
    with open('plan_director.yml', 'w') as f:
        yaml.dump(_bootstrap_plan_yml, f)
    # advise user on what to edit and how to submit this job
    print("""Greetings, earthling.

Wrote bootstrap config files into 'config' folder.

Overview:
    - set your passwords and access keys in config/config.yml
    - edit target build and test platforms in config/*_platforms.d.  Note that 'connector' key is optional.
    - edit config/versions.yml to your liking.  Defaults should work out of the box.
    - Finally, submit this configuration with 'c3i submit'
""")

def build_cli(args):
    checkout_rev = args.stop_rev or args.git_rev
    folders = args.packages
    if not folders:
        folders = git_changed_recipes(args.git_rev, args.stop_rev, git_root=args.path)
    if not folders:
        print("No folders specified to build, and nothing changed in git.  Exiting.")
        sys.exit(0)

    with checkout_git_rev(checkout_rev, args.path):
        task_graph = collect_tasks(args.path, folders=folders, steps=args.steps,
                                    max_downstream=args.max_downstream, test=args.test,
                                   matrix_base_dir=args.matrix_base_dir)
    plan, tasks = graph_to_plan_and_tasks(task_graph, args.public)
    # this just writes the plan using the same code as writing the tasks.
    tasks.update({'plan': plan})
    write_tasks(tasks)


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
    else:
        build_cli(args)
