FROM amazonlinux:2

# Set the locale
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

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
    git \
    wget \
    curl \
    rsync \
    vim \
    patch \
    tar

RUN wget https://graviton-rpms.s3.amazonaws.com/installers/build_AR_1/Miniconda3-py38_4.9.2-Linux-aarch64.sh && \
    bash Miniconda3-py38_4.9.2-Linux-aarch64.sh -bfp /opt/conda && \
    /opt/conda/bin/conda config --set show_channel_urls True && \
    /opt/conda/bin/conda config --set add_pip_as_python_dependency False && \
    /opt/conda/bin/conda config --add channels aarch64-staging && \
    /opt/conda/bin/conda install --yes --quiet conda-build anaconda-client && \
    /opt/conda/bin/conda clean -ay && \
    /opt/conda/bin/conda init bash && \
    rm -rf Miniconda*

ENV PATH="/opt/conda/bin:${PATH}"

CMD [ "/bin/bash" ]