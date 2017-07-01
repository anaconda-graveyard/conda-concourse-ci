FROM centos:6.9
MAINTAINER Michael Sarahan <msarahan@continuum.io>

# minimal subset of build-essentials.  We provide our own toolchain, so we want to save the space
#    for that as much as possible.
RUN yum install -y make

RUN mkdir -p bin && \
  LATEST_RELEASE=$(curl -L -s -H 'Accept: application/json' https://github.com/concourse/concourse/releases/latest) && \
  LATEST_VERSION=$(echo $LATEST_RELEASE | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/') && \
  ARTIFACT_URL="https://github.com/concourse/concourse/releases/download/$LATEST_VERSION/fly_linux_amd64" && \
  curl -L ${ARTIFACT_URL} -o bin/fly && chmod +x bin/fly

ARG GITHUB_TOKEN

COPY install_miniconda.sh /build_scripts/
WORKDIR /build_scripts
RUN bash install_miniconda.sh ${GITHUB_TOKEN} && \
    mkdir -p /opt/share && \
    mkdir -p /opt/miniconda/conda-bld/work/linux-64 && \
    mkdir -p /opt/miniconda/conda-bld/work/linux-32 && \
    mkdir -p /opt/miniconda/conda-bld/work/noarch && \
    chmod -R 777 /opt && \
    useradd -m --uid 1000 dev



WORKDIR /home/dev
USER dev

RUN echo "export PATH=$PATH:~/bin" >> .bashrc && \
    conda config --set add_pip_as_python_dependency False && \
    conda config --add channels msarahan && \
    conda config --add channels rdonnelly && \
    conda config --set anaconda_upload True

ENTRYPOINT [ "/usr/bin/tini", "--" ]
CMD [ "/bin/bash" ]
