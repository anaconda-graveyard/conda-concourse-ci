#/bash/bin

# put pileline upstream via:
fly -t conda-concourse-server sp -p kais_test_r \
  -c ./pipeline16.yaml -l ~/Code/oss/automated-build/c3i_configurations/anaconda_public/config.yml
fly -t conda-concourse-server up -p kais_test_r

fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script0-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script0-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script0-on-winbuilder
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script1-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script1-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script1-on-winbuilder
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script2-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script2-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script2-on-winbuilder
echo "3 jobs triggered"
