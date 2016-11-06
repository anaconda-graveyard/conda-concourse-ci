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

Usage
-----
This package is intended to be installed on some build worker - no label is important.  It computes
which recipes to build based on git differences by default, but packages can also be specified manually.
It then submits jobs back to the CI server for each build on potentially several worker labels.

The interface to this functionality is the ``cgci`` entry point:

.. code-block:: none

    usage: cgci [-h] [--all | --packages PACKAGES [PACKAGES ...]] [--steps STEPS]
                [--max-downstream MAX_DOWNSTREAM] [--git-rev GIT_REV]
                [--stop-rev STOP_REV] [--threads THREADS] [--visualize VISUALIZE]
                [--test]
                path

    positional arguments:
      path

    optional arguments:
      -h, --help            show this help message and exit
      --all                 Show/build all nodes in the graph, not just changed
                            ones
      --packages PACKAGES [PACKAGES ...], -p PACKAGES [PACKAGES ...]
                            Rather than determine tree from git, specify packages
                            to build
      --steps STEPS         Number of downstream steps to follow in the DAG when
                            computing what to test. Used for making sure that an
                            update does not break downstream packages. Set to -1
                            to follow the complete dependency tree.
      --max-downstream MAX_DOWNSTREAM
                            Limit the total number of downstream packages built.
                            Only applies if steps != 0.  Set to -1 for unlimited.
      --git-rev GIT_REV     start revision to examine. If stop not provided,
                            changes are THIS_VAL~1..THIS_VAL
      --stop-rev STOP_REV   stop revision to examine. When provided,changes are
                            git_rev..stop_rev
      --threads THREADS     dask scheduling threads. Effectively number of
                            parallel builds, though not all builds run on one
                            host.
      --visualize VISUALIZE
                            Output a PDF visualization of the package build graph,
                            and quit. Argument is output file name (png, pdf)
      --test                test packages (instead of building them)


The basic concept for where and how to use cgci is based around repositories of recipes.
These repositories must live on the concourse instance which is being used for CI, but can
be clones or mirrors of other git repos (github?)

This tool does not care if recipes are actual folders, or git submodules.  In such a
repository, create a ``.concourse-ci.yml`` file, with contents like:

.. code-block:: yaml

    before_script:
      # update the CI runner package that determines build orders and such
      - echo "Updating CI tool"
      - conda install -qy -c msarahan conda-concourse-ci
      - conda update -qy -c msarahan conda-concourse-ci

    # the first pass examines the difference in the repo from the given two commits
    determine_builds:
      script:
        - cgci .

    # this CI script is called once by each worker (by label) for each recipe.  The variables
    #    that it is called with changes, and those calls are done with the
    #    determine_builds target.
    build_recipe:
      script:
        # Replace this with a script.  concourse does not recognize multliline input.
        # https://concourse.com/concourse-org/concourse-ci-multi-runner/issues/166
        - if [ -n "$BUILD_RECIPE" ]; then conda build --token $ANACONDA_TOKEN $TEST_MODE $BUILD_RECIPE -c conda_concourse; fi


You'll also need some configuration to specify your platform and version matrix.  Create these folders:

* build_platforms.d
* test_platforms.d

In these folders, create any number of arbitrarily named .yaml files.  These files are expected to have the following keys:

* ``label``: this is the label used by Concourse CI to identify appropriate workers for your job
* ``platform``: the conda platform to build on.  Examples: win, osx, linux
* ``arch``: the architecture to build for.  Examples: 32, 64, armv7l, ppc64le

Create the ``versions.yml`` file in the root of your repository:

.. code-block:: yaml

    # labels here reflect environment variable names that conda-build recognizes.
    #    They are defined in the build environment directly, so no additional handling
    #    is necessary (though it does look a little ugly here)

    CONDA_PY:
      - 2.7
      - 3.5
    CONDA_NPY:
      - 1.11
    CONDA_PERL:
      - 5.20
    CONDA_LUA:
      - 5.2
    CONDA_R:
      - 3.3


Now, go to your repo's settings, and make sure that at least these secret environment variables are set:

* ``ANACONDA_TOKEN`` - obtain from https://docs.continuum.io/anaconda-cloud/managing-account#using-tokens
* ``CONCOURSE_PRIVATE_TOKEN`` - sign into your Concourse and go to http://your_concourse_server.com/profile/personal_access_tokens
* ``TRIGGER_TOKEN`` - obtain from Concourse project settings -> Triggers


Credits
---------
This package is derived from `the ProtoCI project
<https://github.com/continuumIO/protoci>`_, which played this role with Anaconda
Build workers.

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage

