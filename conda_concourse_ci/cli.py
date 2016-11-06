import argparse
import contextlib
import logging
import subprocess

import conda_concourse_ci
from .compute_build_graph import git_changed_recipes
from .execute import collect_tasks, write_tasks

log = logging.getLogger(__file__)


def parse_args(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
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
    parser.add_argument('--threads',
                        default=50,
                        help=('dask scheduling threads.  Effectively number of parallel builds, '
                              'though not all builds run on one host.'))
    parser.add_argument('--visualize',
                        help=('Output a PDF visualization of the package build graph, and quit.  '
                              'Argument is output file name (pdf)'),
                        default="")
    parser.add_argument('--test', action='store_true',
                        help='test packages (instead of building them)')
    parser.add_argument('--version', action='version',
        help='Show the conda-build version number and exit.',
        version='conda-concourse-ci %s' % conda_concourse_ci.__version__)
    parser.add_argument('--debug', action='store_true')

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


def build_cli(args=None):
    if not args:
        args = parse_args()
    else:
        args = parse_args(args)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    checkout_rev = args.stop_rev or args.git_rev
    folders = args.packages
    if not folders:
        folders = git_changed_recipes(args.git_rev, args.stop_rev, git_root=args.path)

    with checkout_git_rev(checkout_rev, args.path):
        plan, tasks = collect_tasks(args.path, folders=folders, steps=args.steps,
                                    max_downstream=args.max_downstream, test=args.test)
    # this just writes the plan using the same code as writing the tasks.
    tasks.udpate({'plan': plan})
    write_tasks(tasks, output_folder=args.output_folder)

    log.info("Computed jobs:")
    log.info(tasks)
