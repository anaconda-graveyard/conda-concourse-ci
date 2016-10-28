#!/bin/sh

pwd

# debugging - this folder is automatically created when running with concourse
mkdir -p ci-tasks

cat << EOF > ci-tasks/plan.yml
---
resource_types:
# This allows us to upload/download multiple files to s3 at once
- name: s3-simple
  type: docker-image
  source:
    repository: 18fgsa/s3-resource-simple

resources:
- name: s3-intermediary
  type: s3-simple
  trigger: true
  source:
    bucket: {{aws-bucket}}
    access_key_id: {{aws-key-id}}
    secret_access_key: {{aws-secret-key}}
    options:
      - "--exclude '*'"
      - "--include 'c*'"

jobs:
- name: execute-tasks
  plan:
  - get: s3-intermediary
  - aggregate:
    - task: linux
      file: s3-intermediary/ci-tasks/linux.yml
    - task: windows
      file: s3-intermediary/ci-tasks/win.yml
EOF


cat <<EOF > ci-tasks/linux.yml
---
platform: linux

image_resource:
  type: docker-image
  source: {repository: busybox}

run:
  path: echo
  args: [hello world from linux]
EOF

cat <<EOF > ci-tasks/win.yml
---
platform: linux

image_resource:
  type: docker-image
  source: {repository: busybox}

run:
  path: echo
  args: [hello world from win]
EOF

ls -la ci-tasks
