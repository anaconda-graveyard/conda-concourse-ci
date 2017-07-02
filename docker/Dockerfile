FROM centos:6.9
MAINTAINER Michael Sarahan <msarahan@continuum.io>

RUN mkdir -p bin && \
  LATEST_RELEASE=$(curl -L -s -H 'Accept: application/json' https://github.com/concourse/concourse/releases/latest) && \
  LATEST_VERSION=$(echo $LATEST_RELEASE | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/') && \
  ARTIFACT_URL="https://github.com/concourse/concourse/releases/download/$LATEST_VERSION/fly_linux_amd64" && \
  curl -L ${ARTIFACT_URL} -o bin/fly && chmod +x bin/fly

RUN yum install -y util-linux openssh-clients rsync wget patch

WORKDIR /build_scripts
COPY install_miniconda.sh /build_scripts
COPY Miniconda-* /build_scripts
RUN ./install_miniconda.sh

ENV PATH="/opt/miniconda/bin:${PATH}"

CMD [ "/bin/bash" ]
