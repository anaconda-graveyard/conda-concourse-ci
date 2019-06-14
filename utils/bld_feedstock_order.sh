#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# echo "Will call bld_order in $DIR"
rm -f feedstocks.lst feedstock.tmp
for f in *feedstock; do
 echo "$f" >>feedstocks.tmp
done
cat feedstocks.tmp | tr '\n' ' ' >feedstocks.lst
$DIR/bld_order $* `cat feedstocks.lst`
rm -f feedstocks.tmp feedstock.lst
