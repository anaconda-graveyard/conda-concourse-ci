fname=$(find . -name Miniconda* -type f -exec ls -1t "{}" +; )
# this is Ray Donnelly's custom Miniconda, built with our new gcc toolchain
bash -x $fname -bfp /opt/miniconda
rm $fname
/opt/miniconda/bin/conda config --set show_channel_urls True
# update --all is pulling in replacements from defaults
# /opt/miniconda/bin/conda update --yes --all
/opt/miniconda/bin/conda config --add channels c3i_test
/opt/miniconda/bin/conda install --yes git conda-build curl anaconda-client
/opt/miniconda/bin/conda install --yes conda-concourse-ci
/opt/miniconda/bin/conda config --set add_pip_as_python_dependency False
/opt/miniconda/bin/conda config --set anaconda_upload True
/opt/miniconda/bin/conda clean -ptiy
