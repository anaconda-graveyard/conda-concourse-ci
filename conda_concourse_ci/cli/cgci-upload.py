import argparse

from dask import visualize
from distributed import LocalCluster, Client, progress

from .execute import collect_tasks, write_task_plan


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
                              "computing what to build"),
                        default=0),
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

    return parser.parse_args(parse_this)


def main(args=None):
    if not args:
        args = parse_args()
    else:
        args = parse_args(args)
    filter_dirty = any(args.packages) or not args._all

    outputs = get_dask_outputs(args.path, packages=args.packages, filter_dirty=filter_dirty,
                               git_rev=args.git_rev, stop_rev=args.stop_rev, steps=args.steps,
                               visualize=args.visualize, test=args.test)

    if args.visualize:
        # setattr(nx.drawing, 'graphviz_layout', nx.nx_pydot.graphviz_layout)
        # graphviz_graph = nx.draw_graphviz(graph, 'dot')
        # graphviz_graph.draw(args.visualize)
        visualize(*outputs, filename=args.visualize)  # create neat looking graph.
    else:
        # many threads, because this is just the dispatch.  Takes very little compute.
        # Only waiting for build complete.
        cluster = LocalCluster(n_workers=1, threads_per_worker=args.threads, nanny=False)
        client = Client(cluster)

        futures = client.persist(outputs)
        progress(futures)
