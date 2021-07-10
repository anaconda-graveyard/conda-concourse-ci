# Set environment variables during runtime.
ARG CUDA_VER
ARG CENTOS_VER=7
FROM nvidia/cuda:${CUDA_VER}-devel-centos${CENTOS_VER}
MAINTAINER Anthony DiPietro <adipietro@anaconda.com>

# build stages use these, re-set them.
ARG CUDA_VER
ARG CENTOS_VER=7
ENV CUDA_VER=${CUDA_VER} \
    CENTOS_VER=${CENTOS_VER}

# Set the locale
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# Set path to CUDA install (this is a symlink to /usr/local/cuda-${CUDA_VER})
ENV CUDA_HOME /usr/local/cuda

# Symlink CUDA headers that were moved from $CUDA_HOME/include to /usr/include
# in CUDA 10.1.
RUN for HEADER_FILE in cublas_api.h cublas.h cublasLt.h cublas_v2.h cublasXt.h nvblas.h; do \
    if [[ ! -f "${CUDA_HOME}/include/${HEADER_FILE}" ]]; \
      then ln -s "/usr/include/${HEADER_FILE}" "${CUDA_HOME}/include/${HEADER_FILE}"; \
    fi; \
    done

RUN yum update -y && \
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
