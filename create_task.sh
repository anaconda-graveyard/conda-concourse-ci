#!/bin/sh

pwd

# debugging - this folder is automatically created when running with concourse
mkdir -p ci-tasks

cat << EOF > ci-tasks/generated.yml
---
resources:
- name: execute-tasks
  type: concourse-pipeline
  source:
    teams:
    - name: main

jobs:
- name: set-execute-tasks
  plan:
  - put: execute-tasks
    params:
      pipelines:
      - name: execute-task
        team: main
        config_file: ci-tasks/generated.yml
        # vars_files:
        # - path/to/optional/vars/file/1
        # - path/to/optional/vars/file/2
EOF

ls -la ci-tasks
