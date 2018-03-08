FROM ppc64le/centos:7

RUN yum install -y \
  libX11 \
  libXau \
  libxcb \
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
  wget \
  bzip2 \
  xorg-x11-server-Xvfb \
  && yum clean all

WORKDIR /build_scripts
COPY install_miniconda.sh /build_scripts
RUN ./install_miniconda.sh

ENV PATH="/opt/conda/bin:${PATH}"
