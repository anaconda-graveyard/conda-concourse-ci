TOKEN=$1

# this is Ray Donnelly's custom Miniconda, built with our new gcc toolchain
curl --header 'Authorization: token $TOKEN' \
     --header 'Accept: application/vnd.github.v3.raw' \
     --location https://github.com/ContinuumIO/automated-build/blob/master/bootstrap/Miniconda-4.3.x-Linux-cos6-x86_64.sh \
     -o Miniconda.sh

/bin/bash Miniconda.sh -b -p /opt/miniconda
rm Miniconda.sh
/opt/miniconda/bin/conda config --set show_channel_urls True
/opt/miniconda/bin/conda update --yes --all
/opt/miniconda/bin/conda install --yes -c conda-canary git conda-build curl anaconda-client
/opt/miniconda/bin/conda install --yes -c msarahan conda-concourse-ci
/opt/miniconda/bin/conda config --add channels rdonnelly
/opt/miniconda/bin/conda clean --tarballs --packages
