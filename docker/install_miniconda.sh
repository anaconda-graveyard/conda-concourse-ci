# this is Ray Donnelly's custom Miniconda, built with our new gcc toolchain
fname=$(ls -t Miniconda* | head -1)

/bin/bash $fname -b -p /opt/miniconda
rm $fname
/opt/miniconda/bin/conda config --set show_channel_urls True
/opt/miniconda/bin/conda update --yes --all
/opt/miniconda/bin/conda install --yes -c conda-canary git conda-build curl anaconda-client
/opt/miniconda/bin/conda install --yes -c msarahan conda-concourse-ci
/opt/miniconda/bin/conda config --add channels rdonnelly
/opt/miniconda/bin/conda clean --tarballs --packages
