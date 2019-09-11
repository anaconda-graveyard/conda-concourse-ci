#!/bin/bash
set -euxo pipefail

curl -L https://repo.anaconda.com/pkgs/misc/conda-execs/conda-latest-linux-64.exe -o conda
chmod +x conda

# install compilers so that we don't need to download them for each build.  It's effectively caching.
#    Ignore gfortran to save some space, though.  It's not used commonly enough to warrant caching.
./conda create -p /opt/conda --yes conda git conda-build curl anaconda-client gcc_linux-64 gxx_linux-64 pip
./conda clean -ay
/opt/conda/bin/pip install https://github.com/conda/conda-concourse-ci/archive/master.zip
/opt/conda/bin/conda init bash
rm conda
