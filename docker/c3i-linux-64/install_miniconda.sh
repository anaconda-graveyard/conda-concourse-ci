#!/bin/bash
set -euxo pipefail

fname="Miniconda3-4.3.27-Linux-x86_64.sh"
curl -LO https://repo.continuum.io/miniconda/$fname
bash -x $fname -bfp /opt/conda

/opt/conda/bin/conda config --set show_channel_urls True
# update --all is pulling in replacements from defaults
# /opt/conda/bin/conda update --yes --all
/opt/conda/bin/conda install --yes --quiet git conda-build curl anaconda-client
/opt/conda/bin/conda install --yes --quiet conda-concourse-ci
/opt/conda/bin/conda config --set add_pip_as_python_dependency False
/opt/conda/bin/conda config --set anaconda_upload True
/opt/conda/bin/conda clean -ptiy
rm -rf Miniconda*
