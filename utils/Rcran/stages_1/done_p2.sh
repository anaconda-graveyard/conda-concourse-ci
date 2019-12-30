#/bash/bin

# put pileline upstream via:
fly -t conda-concourse-server sp -p kais_test_r \
  -c ./pipeline2.yaml -l ~/Code/oss/automated-build/c3i_configurations/anaconda_public/config.yml
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
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script3-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script3-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script3-on-winbuilder
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script4-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script4-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script4-on-winbuilder
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script5-on-osx
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script5-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script5-on-winbuilder
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script6-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script7-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script8-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script9-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script10-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script11-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script12-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script13-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script14-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script15-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script16-on-linux_64
fly -t conda-concourse-server trigger-job -j kais_test_r/build_r_script17-on-linux_64
echo "18 jobs triggered"
