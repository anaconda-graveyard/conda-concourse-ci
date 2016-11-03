import argparse
import logging

from dask import visualize
from distributed import LocalCluster, Client, progress

import conda_concourse_ci
from .execute import collect_tasks, write_tasks

log = logging.getLogger(__file__)


def parse_args(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    package_specs = parser.add_mutually_exclusive_group()
    package_specs.add_argument("--all", action='store_true', dest='_all',
                               help='Show/build all nodes in the graph, not just changed ones')
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


def build_cli(args=None):
    if not args:
        args = parse_args()
    else:
        args = parse_args(args)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    filter_dirty = any(args.packages) or not args._all

    plan, tasks = collect_tasks(args.path, packages=args.packages, filter_dirty=filter_dirty,
                                git_rev=args.git_rev, stop_rev=args.stop_rev,
                                steps=args.steps, max_downstream=args.max_downstream,
                                test=args.test, debug=args.debug)
    # this just writes the plan using the same code as writing the tasks.
    tasks.udpate({'plan': plan})
    write_tasks(tasks, output_folder=args.output_folder)

    log.info("Computed jobs:")
    log.info(tasks)
