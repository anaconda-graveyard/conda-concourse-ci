# this is Ray Donnelly's custom Miniconda, built with our new gcc toolchain
fname="Miniconda3-4.3.22.dev3-Linux-x86_64.sh"
curl -LO https://repo.continuum.io/pkgs/misc/preview/$fname
bash -x $fname -bfp /opt/conda

/opt/conda/bin/conda config --set show_channel_urls True
# update --all is pulling in replacements from defaults
# /opt/conda/bin/conda update --yes --all
/opt/conda/bin/conda config --add channels c3i_test
/opt/conda/bin/conda install --yes git conda-build curl anaconda-client
/opt/conda/bin/conda install --yes conda-concourse-ci conda-tracker
/opt/conda/bin/conda config --set add_pip_as_python_dependency False
/opt/conda/bin/conda config --set anaconda_upload True
/opt/conda/bin/conda clean -ptiy
rm -rf Miniconda*
