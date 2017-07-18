#!/bin/sh
new_submodules=$(git diff master --submodule=log | grep -F "(new submodule)" | awk '{print $2}')
for new_submodule in $new_submodules; do
    (
        cd $new_submodule || exit
        if find . -name 'meta.yaml' | grep -e '.' >/dev/null 2>&1; then
            echo $new_submodule
        fi
    )
done
