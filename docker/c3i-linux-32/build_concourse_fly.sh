#!/bin/bash

set -euxo pipefail

OLDDIR="${PWD}"
CONCOURSE_FLY_VERSION="3.3.0"
GO_VERSION="1.8.3"
SCRATCH_DIR="/tmp/$(date +%s)"

# Create a scratch workspace
mkdir "${SCRATCH_DIR}"; cd $_

# Download and setup 32 bit go
wget https://storage.googleapis.com/golang/go${GO_VERSION}.linux-386.tar.gz
tar -xf go${GO_VERSION}.linux-386.tar.gz
export GOROOT=${PWD}/go

# Clone source code
export GOPATH=${PWD}/concourse
git clone https://github.com/concourse/concourse.git
cd concourse

# We want to build a specific version of fly
git checkout "v${CONCOURSE_FLY_VERSION}"
git submodule update --init --recursive
cd src/github.com/concourse/fly

# The dependencies should already be present, but just in case
${GOROOT}/bin/go get -v

# Go!
${GOROOT}/bin/go build -ldflags "-X github.com/concourse/fly/version.Version=${CONCOURSE_FLY_VERSION}"
cp fly /bin/fly
chmod +x /bin/fly

# Delete intermediate stuff
cd "${OLDDIR}"
rm -fr "${SCRATCH_DIR}"
