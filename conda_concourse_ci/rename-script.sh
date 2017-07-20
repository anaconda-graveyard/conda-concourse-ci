#!/bin/bash
new_submodules=$(git diff HEAD~1 | grep -F 'rename to' | awk '{print $3}')
for new_submodule in $new_submodules; do
    (
        cd "$new_submodule" || exit
        if find . -name 'meta.yaml' | grep -e '.' >/dev/null 2>&1; then
            echo "$new_submodule"
        fi
    )
done
