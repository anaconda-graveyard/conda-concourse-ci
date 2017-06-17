FROM continuumio/miniconda

MAINTAINER Michael Sarahan <msarahan@continuum.io>

RUN conda update -qy --all && conda install -qy conda-build constructor anaconda-verify && conda clean -pty

ENTRYPOINT [ "/usr/bin/tini", "--" ]
CMD [ "/bin/bash" ]
