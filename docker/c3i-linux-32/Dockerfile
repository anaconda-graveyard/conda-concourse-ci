FROM conda/centos6-32-minimal-base:6.9
MAINTAINER Michael Sarahan <msarahan@continuum.io>

# locales
RUN yum reinstall -y glibc-common \
  && yum clean all

# Set the locale
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN yum install -y \
  bzip2 \
  libX11 \
  libXau \
  libXcb \
  libXdmcp \
  libXext \
  libXrender \
  libXt \
  mesa-libGL \
  mesa-libGLU \
  openssh-clients \
  patch \
  rsync \
  util-linux \
  which \
  wget \
  && yum clean all

WORKDIR /build_scripts
COPY install_miniconda.sh /build_scripts
RUN ./install_miniconda.sh

ENV PATH="/opt/conda/bin:${PATH}"

COPY build_concourse_fly.sh /build_scripts
RUN ./build_concourse_fly.sh

ENTRYPOINT [ "linux32" ]
CMD [ "/bin/bash" ]
