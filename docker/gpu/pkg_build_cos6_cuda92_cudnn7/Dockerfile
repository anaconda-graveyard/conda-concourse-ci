FROM nvidia/cuda:9.2-cudnn7-devel-centos6
MAINTAINER Jonathan J. Helmus <jjhelmus@gmail.com>

# Set the locale
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN yum update -y \
  yum install -y \
  gettext \
  libX11 \
  libXau \
  libXcb \
  libXdmcp \
  libXext \
  libXrender \
  libXt \
  mesa-libGL \
  mesa-libGLU \
  libXcomposite \
  libXcursor \
  libXi \
  libXtst \
  libXrandr \
  libXScrnSaver \
  alsa-lib \
  mesa-libEGL \
  pam \
  openssh-clients \
  patch \
  rsync \
  util-linux \
  wget \
  xorg-x11-server-Xvfb \
  chrpath \
  && yum clean all

WORKDIR /build_scripts
COPY install_miniconda.sh /build_scripts
RUN ./install_miniconda.sh

ENV PATH="/opt/conda/bin:${PATH}"

CMD [ "/bin/bash" ]
