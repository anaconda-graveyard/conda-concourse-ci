#!/bin/bash
set -euxo pipefail

fname="Miniconda3-latest-Linux-x86_64.sh"
curl -LO https://repo.continuum.io/miniconda/$fname
bash -x $fname -bfp /opt/conda

/opt/conda/bin/conda config --set show_channel_urls True

# update --all is pulling in replacements from defaults
# /opt/conda/bin/conda update --yes --all
/opt/conda/bin/conda update --yes --quiet --all

# install compilers so that we don't need to download them for each build.  It's effectively caching.
#    Ignore gfortran to save some space, though.  It's not used commonly enough to warrant caching.
/opt/conda/bin/conda install --yes --quiet conda git conda-build curl anaconda-client gcc_linux-64 gxx_linux-64 pip

/opt/conda/bin/conda config --set add_pip_as_python_dependency False
/opt/conda/bin/conda clean -ay
/opt/conda/bin/conda init bash

mkdir -p /opt/conda/pkgs

rm -rf Miniconda*
