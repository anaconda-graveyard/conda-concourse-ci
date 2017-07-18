#!/bin/sh
submodules=$(git submodule | awk '{print $2}')
for submodule in ${submodules[*]}; do
    revision=$(git diff $1 $submodule | fgrep "Subproject" | head -n1 | awk '{print $3}')
    cd $submodule
    echo "$submodule" $(git diff $revision --name-only)
    cd ..
done
