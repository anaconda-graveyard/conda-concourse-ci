FROM centos:6.9
MAINTAINER Michael Sarahan <msarahan@continuum.io>

RUN mkdir -p bin && \
  LATEST_RELEASE=$(curl -L -s -H 'Accept: application/json' https://github.com/concourse/concourse/releases/latest) && \
  LATEST_VERSION=$(echo $LATEST_RELEASE | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/') && \
  ARTIFACT_URL="https://github.com/concourse/concourse/releases/download/$LATEST_VERSION/fly_linux_amd64" && \
  curl -L ${ARTIFACT_URL} -o bin/fly && chmod +x bin/fly

RUN yum install -y util-linux

RUN useradd -ms /bin/bash dev
WORKDIR /home/dev
USER dev

COPY install_miniconda.sh /home/dev
COPY Miniconda-* /home/dev
RUN ./install_miniconda.sh

RUN echo "export PATH=$PATH:~/miniconda/bin" >> .bashrc && \
    conda config --set add_pip_as_python_dependency False && \
    conda config --add channels msarahan && \
    conda config --add channels rdonnelly && \
    conda config --set anaconda_upload True

ENTRYPOINT [ "/usr/bin/tini", "--" ]
CMD [ "/bin/bash" ]
