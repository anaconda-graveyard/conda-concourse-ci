This helper utils can be used to autogenerate build scripts using:

- bash shell script using conda-build
- command shell batch file using conda-build

------------------------------------------------------------------------------

First step is preparing usage. Either work directly within this directory, or copy all files within that folder to a place you prefer.

You will need to run the following command to prepare:

 chmod 0755 bld_feedstock_order.sh
 gcc -o bld_order bld_order.c # you can use of course clang here too

------------------------------------------------------------------------------

The usage of this tool is the following:

  If you want to build build script for all folders within your current
    working directory, then use the bld_feedstock_order.sh shell script.
    otherwise you can invoke the bld_order executable directly and passing
    just the desired feedstock folder names.

  Eg:
   cd aggregateR/
   ../conda-concourse-ci/utils/bld_order rstudio-feedstock -R 3.6.0 -k shell \
     -o bld.sh

   will build the shell script bld.sh containing all required build steps
   in correct order.  The additional argument -R specifies the required
   version of R to be used.

   The script will look like as shown in [*1].

  The following options build_order tool supports:

  -h: display an quick overview about all available options
  -o file-name: specifies the output file name.
  -m file-name: specifies the meesage file name all output is redirected to
  -R R-version: specifies the required R version
  -c channel: adds channel to the command line where packages are searched.
              be aware that 'local' channel is automatically added.
  -k kind: specifies the kind of output generated. Right now tool supports
           the following output kinds:
           - shell : output bash shell script
           - bat   : output batch script
           - gexf  : output directed graph of build dependencies
                     The arguments -c, and -R have no meaning for this.

-----------------------------------------------------------------------------

Limitation:
 - This tool doesn't resolve jinja2 variables.
 - It needs to be rewritten to support better a python frontend
 - It searches dependency feedstocks just within current working directory.
   This could be easily extended to search also in additional specified places.
 - It does not output for now c3i compatible dependency files (trivial)


-----------------------------------------------------------------------------

[*1]:

 $ cat bld.sh
 #!/bin/bash

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  _r-mutex-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-base-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-base64enc-feedstock r-bitops-feedstock r-digest-feedstock r-evaluate-feedstock r-highr-feedstock r-jsonlite-feedstock r-mime-feedstock r-packrat-feedstock r-r6-feedstock r-rcpp-feedstock r-rjava-feedstock r-rjsonio-feedstock r-rstudioapi-feedstock r-sourcetools-feedstock r-xtable-feedstock r-yaml-feedstock || exit 1
conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-crayon-feedstock r-rlang-feedstock r-bh-feedstock r-xfun-feedstock r-dbi-feedstock r-clipr-feedstock r-backports-feedstock r-assertthat-feedstock r-ellipsis-feedstock r-generics-feedstock r-rappdirs-feedstock r-withr-feedstock r-glue-feedstock r-magrittr-feedstock r-stringi-feedstock r-pkgconfig-feedstock || exit 1
conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-fansi-feedstock r-bit-feedstock r-rematch-feedstock r-plogr-feedstock r-curl-feedstock r-utf8-feedstock r-sys-feedstock || exit 1

conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-catools-feedstock r-htmltools-feedstock r-markdown-feedstock r-pki-feedstock r-rcurl-feedstock r-rjdbc-feedstock r-rprojroot-feedstock r-stringr-feedstock r-xml2-feedstock r-later-feedstock r-hms-feedstock r-bit64-feedstock r-tinytex-feedstock r-config-feedstock r-forge-feedstock r-cli-feedstock || exit 1
 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-askpass-feedstock r-prettyunits-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-htmlwidgets-feedstock r-knitr-feedstock r-promises-feedstock r-openssl-feedstock r-blob-feedstock r-progress-feedstock r-pillar-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-httpuv-feedstock r-mongolite-feedstock r-odbc-feedstock r-profvis-feedstock r-rmarkdown-feedstock r-rsconnect-feedstock r-tibble-feedstock r-httr-feedstock r-r2d3-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-shiny-feedstock r-readr-feedstock r-forcats-feedstock r-cellranger-feedstock r-purrr-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-haven-feedstock r-miniui-feedstock r-readxl-feedstock r-tidyselect-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-dplyr-feedstock || exit 1

conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-dbplyr-feedstock r-tidyr-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  r-sparklyr-feedstock || exit 1

 conda-build --skip-existing --R 3,6,0 -c https://repo.continuum.io/pkgs/main -c local  rstudio-feedstock || exit 1 


