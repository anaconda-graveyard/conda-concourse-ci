#!/bin/bash
set -euxo pipefail

# this is Ray Donnelly's custom Miniconda, built with our new gcc toolchain
fname="Miniconda3-4.3.22.dev3-Linux-x86.sh"
curl -LO https://repo.continuum.io/pkgs/misc/preview/$fname
bash -x $fname -bfp /opt/conda
rm $fname

/opt/conda/bin/conda config --set show_channel_urls True
# update --all is pulling in replacements from defaults
# /opt/conda/bin/conda update --yes --all
/opt/conda/bin/conda config --add channels c3i_test
/opt/conda/bin/conda install --yes --quiet git conda-build curl anaconda-client

# conda-install c3i dependencies, then pip-install c3i
/opt/conda/bin/conda install -y --quiet contextlib2 networkx setuptools six yaml
/opt/conda/bin/pip install https://github.com/conda/conda-concourse-ci/archive/master.zip

/opt/conda/bin/conda config --set add_pip_as_python_dependency False
/opt/conda/bin/conda config --set anaconda_upload True
/opt/conda/bin/conda clean -ptiy
