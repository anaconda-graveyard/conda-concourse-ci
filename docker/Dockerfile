FROM continuumio/miniconda3

MAINTAINER Michael Sarahan <msarahan@continuum.io>

RUN echo "export PATH=$PATH:~/bin" >> ~/.bashrc
RUN echo "add_pip_as_python_dependency: False" >> ~/.condarc
RUN conda config --add channels msarahan
RUN conda config --add channels rdonnelly
RUN conda config --set anaconda_upload True

# minimal subset of build-essentials.  We provide our own toolchain, so we want to save the space
#    for that as much as possible.
RUN apt-get install -y make

RUN conda update -qy --all && conda install -qy -c conda_build_test -c conda-canary -c msarahan conda-build conda-concourse-ci anaconda-client && conda clean -pty

RUN mkdir -p bin && \
  LATEST_RELEASE=$(curl -L -s -H 'Accept: application/json' https://github.com/concourse/concourse/releases/latest) && \
  LATEST_VERSION=$(echo $LATEST_RELEASE | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/') && \
  ARTIFACT_URL="https://github.com/concourse/concourse/releases/download/$LATEST_VERSION/fly_linux_amd64" && \
  curl -L ${ARTIFACT_URL} -o bin/fly && chmod +x bin/fly

ENTRYPOINT [ "/usr/bin/tini", "--" ]
CMD [ "/bin/bash" ]
