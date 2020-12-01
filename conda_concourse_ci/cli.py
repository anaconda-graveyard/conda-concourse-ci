import argparse
import logging
import os

from conda_build.conda_interface import cc_conda_build

from conda_concourse_ci import __version__, execute


def parse_args(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--version', action='version',
        help='Show the conda-build version number and exit.',
        version='conda-concourse-ci %s' % __version__)
    sp = parser.add_subparsers(title='subcommands', dest='subparser_name')
    examine_parser = sp.add_parser('examine', help='examine path for changed recipes')
    examine_parser.add_argument('base_name',
                                help="name of your project, to distinguish it from other projects")
    examine_parser.add_argument("path", default='.', nargs='?',
                        help="path in which to examine/build/test recipes")
    examine_parser.add_argument('--folders', default=[], nargs="+",
                        help="Rather than determine tree from git, specify folders to build")
    examine_parser.add_argument('--steps', type=int,
                        help=("Number of downstream steps to follow in the DAG when "
                              "computing what to test.  Used for making sure that an "
                              "update does not break downstream packages.  Set to -1 "
                              "to follow the complete dependency tree."),
                        default=0),
    examine_parser.add_argument('--max-downstream', default=5, type=int,
                        help=("Limit the total number of downstream packages built.  Only applies "
                              "if steps != 0.  Set to -1 for unlimited."))
    examine_parser.add_argument('--git-rev',
                        default='HEAD',
                        help=('start revision to examine.  If stop not '
                              'provided, changes are THIS_VAL~1..THIS_VAL'))
    examine_parser.add_argument('--stop-rev', default=None,
                        help=('stop revision to examine.  When provided,'
                              'changes are git_rev..stop_rev'))
    examine_parser.add_argument('--test', action='store_true',
                        help='test packages (instead of building AND testing them)')
    examine_parser.add_argument('--matrix-base-dir',
                                help='path to matrix configuration, if different from recipe path',
                                default=cc_conda_build.get('matrix_base_dir'))
    examine_parser.add_argument('--output-dir', help="folder where output plan and recipes live",
                                default='../output')
    examine_parser.add_argument('--channel', '-c', action='append',
                                help="Additional channel to use when building packages")
    examine_parser.add_argument('--platform-filter', '-p', action='append',
                                help="glob pattern(s) to filter build platforms.  For example, "
                                "linux* will build all platform files whose filenames start with "
                                "linux",
                                dest='platform_filters')
    examine_parser.add_argument('--worker-tag', '-t', action='append',
                                help="set worker tag(s) to limit where jobs will run.  Applies "
                                "to all jobs.  For finer control, use extra/worker_tags in "
                                "meta.yaml with selectors.",
                                dest='worker_tags')
    examine_parser.add_argument(
        '-m', '--variant-config-files',
        action="append",
        help="""Additional variant config files to add.  These yaml files can contain
        keys such as `c_compiler` and `target_platform` to form a build matrix."""
    )
    examine_parser.add_argument(
        '--no-skip-existing', help="Do not skip existing builds",
        dest="skip_existing", action="store_false"
    )
    submit_parser = sp.add_parser('submit', help="submit plan director to configured server")
    submit_parser.add_argument('base_name',
                               help="name of your project, to distinguish it from other projects")
    submit_parser.add_argument('--pipeline-name', help="name for the submitted pipeline",
                               default='{base_name} plan director')
    submit_parser.add_argument('--pipeline-file', default='plan_director.yml',
                               help="path to pipeline .yml file containing plan")
    submit_parser.add_argument('--config-root-dir',
                               help="path containing build-config.yml (optional), config.yml and matrix definitions")

    submit_parser.add_argument('--src-dir', help="folder where git repo of source code lives",
                               default=os.getcwd())
    submit_parser.add_argument('--private', action='store_false',
                        help='hide build logs (overall graph still shown in Concourse web view)',
                        dest='public')

    bootstrap_parser = sp.add_parser('bootstrap',
                                     help="create default configuration files to help you start")
    bootstrap_parser.add_argument('base_name',
                            help="name of your project, to distinguish it from other projects")

    one_off_parser = sp.add_parser('one-off',
                                   help="submit local recipes and plan to configured server")
    one_off_parser.add_argument('pipeline_label',
                                help="name of your project, to distinguish it from other projects")
    one_off_parser.add_argument('--build-config', nargs="+",
                                help=("Specify VAR=VAL to override values defined in build-config.yml"))
    one_off_parser.add_argument('folders', nargs="+",
                                help=("Specify folders, relative to --recipe-root-dir, to upload "
                                      "and build"))
    one_off_parser.add_argument('--automated-pipeline',
                                action='store_true',
                                default=False,
                                help="Flag to run this one_off command as an automated pipeline. Default is False",
                                )
    one_off_parser.add_argument(
        '--branches',
        nargs='+',
        default=None,
        help=(
            "Only used when --automated_pipeline is specified. "
            "List of repository branches that recipes will be pulled from. "
            "Either pass in one branch or n number of branches where "
            "n is equal to the number of recipes you are building. "
            "The default is to use the 'automated-build' branch. "
            "Specific this option after the list of folders to avoid "
            "confusing which arguments are folders and which are branches, "
            "for example: "
            "c3i one-off pipeline_label folder1 folder2 --branches branch1 branch2"
        )
    )
    one_off_parser.add_argument(
        "--pr-num",
        action="store",
        help="The PR number on which to make a comment when using the automated pipeline"
    )
    one_off_parser.add_argument(
        "--repository",
        action="store",
        help="The git repo where the PR lives. This should look like: Org/Repo"
    )
    one_off_parser.add_argument(
        "--pr-file",
        action="store",
        help="File added to the git repo by the PR"
    )
    one_off_parser.add_argument(
        '--stage-for-upload', action='store_true',
        help="create job that stages package for upload as part of the pipeline")
    one_off_parser.add_argument(
        '--push-branch', action='store_true',
        help="create a job that push the branch(es) used for the build to master")
    one_off_parser.add_argument(
        '--destroy-pipeline', action='store_true',
        help="destroys the pipeline once the review branch has been merged, "
        "the artifacts have been staged, and the reciepe repo has been updated. "
        "This requires --stage-for-upload and --push-branch options.")
    one_off_parser.add_argument(
        '--commit-msg', action='store',
        help=("git commit message to record when packages are uploaded, "
              "required when --stage-for-upload specified"))
    one_off_parser.add_argument('--recipe-root-dir', default=os.getcwd(),
                                help="path containing recipe folders to upload")
    one_off_parser.add_argument('--config-root-dir',
                                help="path containing config.yml and matrix definitions",
                                default=cc_conda_build.get('matrix_base_dir'))
    one_off_parser.add_argument('--private', action='store_false',
                        help='hide build logs (overall graph still shown in Concourse web view)',
                        dest='public')
    one_off_parser.add_argument('--channel', '-c', action='append',
                                help="Additional channel to use when building packages")
    one_off_parser.add_argument('--platform-filter', '-p', action='append',
                                help="glob pattern(s) to filter build platforms.  For example, "
                                "linux* will build all platform files whose filenames start with "
                                "linux", dest='platform_filters')
    one_off_parser.add_argument('--worker-tag', '-t', action='append',
                                help="set worker tag(s) to limit where jobs will run.  Applies "
                                "to all jobs.  For finer control, use extra/worker_tags in "
                                "meta.yaml with selectors.",
                                dest='worker_tags')
    one_off_parser.add_argument(
        '-m', '--variant-config-files',
        action="append",
        help="""Additional variant config files to add.  These yaml files can contain
        keys such as `c_compiler` and `target_platform` to form a build matrix."""
    )
    one_off_parser.add_argument('--output-dir', help=("folder where output plan and recipes live."
                                "Defaults to temp folder.  Set to something to save output."))
    one_off_parser.add_argument(
        '--append-file',
        help="""Append data in meta.yaml with fields from this file.  Jinja2 is not done
        on appended fields""",
        dest='append_sections_file',
    )
    one_off_parser.add_argument(
        '--clobber-file',
        help="""Clobber data in meta.yaml with fields from this file.  Jinja2 is not done
        on clobbered fields.""",
        dest='clobber_sections_file',
    )
    one_off_parser.add_argument(
        '--no-skip-existing', help="Do not skip existing builds",
        dest="skip_existing", action="store_false"
    )
    one_off_parser.add_argument(
        '--use-repo-access',
        help="Pass the repo access credentials to the workers",
        action="store_true",
    )

    one_off_parser.add_argument(
        '--use-staging-channel',
        help="Uploads built packages to staging channel",
        action="store_true",
    )
    one_off_parser.add_argument(
        '--dry-run',
        action="store_true",
        help=(
            "Dry run, prepare concourse plan and files but do not submit. "
            "Best used with the --output-dir option so the output can be inspected"
        ),
    )

    batch_parser = sp.add_parser('batch', help="submit a batch of one-off jobs.")
    batch_parser.add_argument(
        'batch_file',
        help="""File describing batch job.  Each lines defines a seperate
        one-off job.  List one or more folders on each line.  Job specific
        arguments can be specified after a ';' using param=value, multiple
        arguments are seperated by a ','.  For example:

            recipe-feedstock; channel=conda-forge,clobber_sections_file=clobber.yaml
        """)

    # batch specific arguments
    batch_parser.add_argument(
        '--max-builds', default=6, type=int,
        help=("maximum number of activate builds allowed before starting a new"
              "job, default is 6"))
    batch_parser.add_argument(
        '--poll-time', default=120, type=int,
        help=("time in seconds between checking concourse server for active "
              "builds, default is 120 seconds."))
    batch_parser.add_argument(
        '--build-lookback', default=500, type=int,
        help="number of builds to examine for active builds, default is 500")
    batch_parser.add_argument(
        '--label-prefix', default='autobot_',
        help="prefix for pipeline labels, default is autobot_")

    # one-off arguments
    batch_parser.add_argument('--recipe-root-dir', default=os.getcwd(),
                                help="path containing recipe folders to upload")
    batch_parser.add_argument('--config-root-dir',
                                help="path containing config.yml and matrix definitions",
                                default=cc_conda_build.get('matrix_base_dir'))
    batch_parser.add_argument('--private', action='store_false',
                        help='hide build logs (overall graph still shown in Concourse web view)',
                        dest='public')
    batch_parser.add_argument('--channel', '-c', action='append',
                                help="Additional channel to use when building packages")
    batch_parser.add_argument('--platform-filter', '-p', action='append',
                                help="glob pattern(s) to filter build platforms.  For example, "
                                "linux* will build all platform files whose filenames start with "
                                "linux", dest='platform_filters')
    batch_parser.add_argument('--worker-tag', '-t', action='append',
                                help="set worker tag(s) to limit where jobs will run.  Applies "
                                "to all jobs.  For finer control, use extra/worker_tags in "
                                "meta.yaml with selectors.",
                                dest='worker_tags')
    batch_parser.add_argument(
        '-m', '--variant-config-files',
        action="append",
        help="""Additional variant config files to add.  These yaml files can contain
        keys such as `c_compiler` and `target_platform` to form a build matrix."""
    )
    batch_parser.add_argument('--output-dir', help=("folder where output plan and recipes live."
                              "Defaults to temp folder.  Set to something to save output."))
    batch_parser.add_argument(
        '--append-file',
        help="""Append data in meta.yaml with fields from this file.  Jinja2 is not done
        on appended fields""",
        dest='append_sections_file',
    )
    batch_parser.add_argument(
        '--clobber-file',
        help="""Clobber data in meta.yaml with fields from this file.  Jinja2 is not done
        on clobbered fields.""",
        dest='clobber_sections_file',
    )
    batch_parser.add_argument(
        '--no-skip-existing', help="Do not skip existing builds",
        dest="skip_existing", action="store_false"
    )
    batch_parser.add_argument(
        '--use-repo-access',
        help="Pass the repo access credentials to the workers",
        action="store_true",
    )
    batch_parser.add_argument(
        '--use-staging-channel',
        help="Uploads built packages to staging channel",
        action="store_true",
    )
    rm_parser = sp.add_parser('rm', help='remove pipelines from server')
    rm_parser.add_argument('pipeline_names', nargs="+",
                           help=("Specify pipeline names on server to remove"))
    rm_parser.add_argument('--config-root-dir',
                           help="path containing config.yml and matrix definitions",
                           default=cc_conda_build.get('matrix_base_dir'))
    rm_parser.add_argument('--do-it-dammit', '-y', help="YOLO", action="store_true")

    pause_parser = sp.add_parser('pause', help='pause pipelines on the server')
    pause_parser.add_argument('pipeline_names', nargs="+",
                           help=("Specify pipeline names on server to pause"))
    pause_parser.add_argument('--config-root-dir',
                           help="path containing config.yml and matrix definitions",
                           default=cc_conda_build.get('matrix_base_dir'))
    pause_parser.add_argument('--do-it-dammit', '-y', help="YOLO", action="store_true")

    unpause_parser = sp.add_parser('unpause', help='pause pipelines on the server')
    unpause_parser.add_argument('pipeline_names', nargs="+",
                           help=("Specify pipeline names on server to pause"))
    unpause_parser.add_argument('--config-root-dir',
                           help="path containing config.yml and matrix definitions",
                           default=cc_conda_build.get('matrix_base_dir'))
    unpause_parser.add_argument('--do-it-dammit', '-y', help="YOLO", action="store_true")

    trigger_parser = sp.add_parser('trigger', help='trigger (failed) jobs of a pipeline')
    trigger_parser.add_argument('pipeline_names', nargs='+',
                           help=("Specify pipeline names to trigger"))
    trigger_parser.add_argument('--config-root-dir',
                           help="path containing config.yml and matrix definitions",
                           default=cc_conda_build.get('matrix_base_dir'))
    trigger_parser.add_argument('--all', dest="trigger_all",
                           action="store_true", help="trigger all jobs")

    abort_parser = sp.add_parser('abort', help='abort jobs of a pipeline')
    abort_parser.add_argument('pipeline_names', nargs='+',
                           help=("Specify pipeline names to abort"))
    abort_parser.add_argument('--config-root-dir',
                           help="path containing config.yml and matrix definitions",
                           default=cc_conda_build.get('matrix_base_dir'))

    return parser.parse_known_args(parse_this)


def main(args=None):
    if not args:
        args, pass_throughs = parse_args()
    else:
        args, pass_throughs = parse_args(args)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.subparser_name == 'submit':
        args_dict = args.__dict__
        if not args_dict.get('config_root_dir'):
            args_dict['config_root_dir'] = args_dict['base_name']
        execute.submit(pass_throughs=pass_throughs, **args_dict)
    elif args.subparser_name == 'bootstrap':
        execute.bootstrap(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'examine':
        execute.compute_builds(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'one-off':
        execute.submit_one_off(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'batch':
        execute.submit_batch(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'rm':
        execute.rm_pipeline(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'pause':
        execute.pause_pipeline(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'unpause':
        execute.unpause_pipeline(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'trigger':
        execute.trigger_pipeline(pass_throughs=pass_throughs, **args.__dict__)
    elif args.subparser_name == 'abort':
        execute.abort_pipeline(pass_throughs=pass_throughs, **args.__dict__)
    else:
        # this is here so that if future subcommands are added, you don't forget to add a bit
        #     here to enable them.
        raise NotImplementedError("Command {} is not implemented".format(args.subparser_name))
