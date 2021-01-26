# Building GPU packages

Most of the information from [Build a CUDA (GPU) package](https://anaconda.atlassian.net/wiki/spaces/AD/pages/1155432453/Build+a+CUDA+GPU+package) holds and is a great start.

## atx-linuxgpu-02

For building GPU packages on this box, we use a number of docker images for the CUDA variants. There is now an updated Dockerfile to create the images in the same manner for all the CUDA versions. it is located in [pkg_build_cos6](./pkg_build_cos6). To build images from this, you need to provide the CUDA version:

```
sudo docker build -t build_cos6_cuda92 . --build-arg CUDA_VER=9.2
sudo docker build -t build_cos6_cuda100 . --build-arg CUDA_VER=10.0
sudo docker build -t build_cos6_cuda101 . --build-arg CUDA_VER=10.1
sudo docker build -t build_cos6_cuda102 . --build-arg CUDA_VER=10.2
```

## atx-wingpu-02

This is a bit different since we can not use Docker images. The supported CUDA versions that we build against for defaults are installed on the system. To build against a specific version, two things must be done prior to the build in the system's environment variables.

1. Set `CUDA_PATH` to the version you want to build against. I.E.:
    ```
    CUDA_PATH => C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v10.1
    ```
2. Ensure that the desired `CUDA_PATH\bin` is the **first** CUDA entry on the PATH. This makes sure that the desired `nvcc` is found. I.E.:
    ```
    PATH => C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v10.1\bin;...
    ```