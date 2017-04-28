===============================
Conda Concourse CI
===============================


.. image:: https://img.shields.io/travis/conda/conda-concourse-ci.svg
           :target: https://travis-ci.org/conda/conda-concourse-ci
           :alt: Travis CI build status

.. image:: https://codecov.io/gh/conda/conda-concourse-ci/branch/master/graph/badge.svg
           :target: https://codecov.io/gh/conda/conda-concourse-ci
           :alt: code coverage
           
.. image:: https://landscape.io/github/conda/conda-concourse-ci/master/landscape.svg?style=flat
           :target: https://landscape.io/github/conda/conda-concourse-ci/master
           :alt: Code Health


Drive Concourse CI for conda recipe repos

* Free software: BSD 3-clause license

Features
--------

* Determine changed conda recipes from either the most recent commit, or from a range of commits
* Trigger additional build jobs to a concourse CI server based on those changes

Requirements
------------

* an s3 store, used as intermediate storage
* a git repository of recipes

Setup
-----

This package requires some configuration before starting. First, create
configuration files. These can be anywhere, and since they'll contain sensitive
access information, it's probably best that you don't check them into a public
repository. To get a basic skeleton setup, run the ``c3i bootstrap`` command
where you want your configuration to live. From here:

    - set your passwords and access keys in config/config.yml
    - edit target build and test platforms in config/*_platforms.d. Note that
      'connector' key is optional.
    - upload
    - Finally, submit this configuration with 'c3i submit'. This sends your
      configuration files to your s3 bucket, establishing the foundation which
      future builds will customize (git commit, for example)

Usage
-----
This package is intended to be installed on some build worker - no label is important.  It computes
which recipes to build based on git differences by default, but packages can also be specified manually.
It then submits jobs back to the CI server for each build on potentially several worker labels.

The interface to this functionality is the ``c3i`` entry point:

.. code-block:: none

    usage: c3i [-h] [--path PATH] [--packages PACKAGES [PACKAGES ...]]
              [--steps STEPS] [--max-downstream MAX_DOWNSTREAM]
              [--git-rev GIT_REV] [--stop-rev STOP_REV] [--test] [--private]
              [--matrix-base-dir MATRIX_BASE_DIR] [--version] [--debug]
              {submit,bootstrap} ...

    optional arguments:
      -h, --help            show this help message and exit
      --path PATH           path in which to examine/build/test recipes
      --packages PACKAGES [PACKAGES ...], -p PACKAGES [PACKAGES ...]
                            Rather than determine tree from git, specify packages
                            to build
      --steps STEPS         Number of downstream steps to follow in the DAG when
                            computing what to test. Used for making sure that an
                            update does not break downstream packages. Set to -1
                            to follow the complete dependency tree.
      --max-downstream MAX_DOWNSTREAM
                            Limit the total number of downstream packages built.
                            Only applies if steps != 0. Set to -1 for unlimited.
      --git-rev GIT_REV     start revision to examine. If stop not provided,
                            changes are THIS_VAL~1..THIS_VAL
      --stop-rev STOP_REV   stop revision to examine. When provided,changes are
                            git_rev..stop_rev
      --test                test packages (instead of building them)
      --private             hide build logs (overall graph still shown in
                            Concourse web view)
      --matrix-base-dir MATRIX_BASE_DIR
                            path to matrix configuration, if different from recipe
                            path
      --version             Show the conda-build version number and exit.
      --debug

    subcommands:
      {submit,bootstrap}
        submit              submit plan director to configured server
        bootstrap           create default configuration files to help you start


The basic concept for where and how to use c3i is based around repositories of recipes.
These repositories must live on the concourse instance which is being used for CI, but can
be clones or mirrors of other git repos (github?)

The configuration you submit creates a pipeline that monitors your specified git recipe repository.  When
new commits come in, it triggers c3i to examine repository changes.  c3i writes the updated plan for these
changes, and that plan is used to set a new pipeline for the build/test tasks.

FAQ/Issues
----------

- error setting version: RequestTimeTooSkewed: The difference between the request time and the current time is too large.

This happens with virtual machines that are suspended and reopened later.  Restarting the docker container or VM that is running your concourse server is often a fix.

Credits
---------
This package is derived from `the ProtoCI project
<https://github.com/continuumIO/protoci>`_, which played this role with Anaconda
Build workers.

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage

