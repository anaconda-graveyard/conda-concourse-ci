FROM centos:6.9
MAINTAINER Michael Sarahan <msarahan@continuum.io>

RUN echo "export PATH=$PATH:~/bin" >> ~/.bashrc
RUN echo "add_pip_as_python_dependency: False" >> ~/.condarc

# minimal subset of build-essentials.  We provide our own toolchain, so we want to save the space
#    for that as much as possible.
RUN yum install -y make

RUN mkdir -p bin && \
  LATEST_RELEASE=$(curl -L -s -H 'Accept: application/json' https://github.com/concourse/concourse/releases/latest) && \
  LATEST_VERSION=$(echo $LATEST_RELEASE | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/') && \
  ARTIFACT_URL="https://github.com/concourse/concourse/releases/download/$LATEST_VERSION/fly_linux_amd64" && \
  curl -L ${ARTIFACT_URL} -o bin/fly && chmod +x bin/fly

ARG GITHUB_TOKEN=local
ENV GITHUB_TOKEN ${GITHUB_TOKEN}

WORKDIR /build_scripts
COPY docker/install_miniconda.sh /build_scripts/
RUN bash install_miniconda.sh ${GITHUB_TOKEN} && \
    mkdir -p /opt/share && \
    mkdir -p /opt/miniconda/conda-bld/work/linux-64 && \
    mkdir -p /opt/miniconda/conda-bld/work/linux-32 && \
    mkdir -p /opt/miniconda/conda-bld/work/noarch && \
    chmod -R 777 /opt && \
    useradd -m --uid 1000 dev

RUN conda config --add channels msarahan
RUN conda config --add channels rdonnelly
RUN conda config --set anaconda_upload True

WORKDIR /home/dev
USER dev

ENTRYPOINT [ "/usr/bin/tini", "--" ]
CMD [ "/bin/bash" ]
