#!/bin/bash
submodules=$(git submodule | awk '{print $2}')
for submodule in $submodules; do
    revision=$(git diff "$submodule" | grep -F "Subproject" | head -n1 | awk '{print $3}')
    (
        if [[ -n "$revision" ]] ; then
            cd "$submodule" || exit
            echo "$submodule" "$(git diff "$revision" --name-only)"
        fi
    )
done
