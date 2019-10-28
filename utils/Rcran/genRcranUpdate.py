#!/usr/bin/env python
# coding: utf-8

# requires ipython rpy2 matplotlib tzlocal pandas gitpython

from bs4 import BeautifulSoup
import rpy2.robjects as robjects
from rpy2.robjects import pandas2ri
import requests
import json
import math
import pandas as pd
import numpy as np
import re, os, time, shutil
from email.parser import BytesParser
from email import message_from_string
# Git stuff
import os
import git
import subprocess

do_max_pkg_cnt = 10
enabled_win32 = False
enable_skeleton_for_existing = False
show_just_unbuilt = False

CRAN_BASE = 'https://cran.r-project.org'
RrepositoryName = 'aggregateR'
RrepositoryURL = 'git@github.com:AnacondaRecipes/aggregateR.git'
RrepositoryURL2 = 'https://github.com/AnacondaRecipes/aggregateR.git'
#CRAN_BASE = 'https://cran.microsoft.com/snapshot/2018-01-01'
RecipeMaintainer = 'katietz'
Rver = '36'
Rfullver = '3.6.1'

batch_count_max=100
do_recursive = '' # '--dirty --recursive'

def is_noarch(name, acompiled):
    return acompiled[name] == False

def is_dependon(name, adepends):
    for dep in adepends:
        if name in dep:
            return True
    return False

def get_aggregateR_repo(rpath = './run', branch = 'latest_update'):
    if not os.path.exists(rpath):
        os.mkdir(rpath)
        print("Path {} does not exist creating".format(rpath))
    if not os.path.exists(rpath + '/aggregateR'):
        repo = git.Repo.clone_from('git@github.com:AnacondaRecipes/aggregateR.git', rpath + '/aggregateR')
    else:
        repo = git.Repo(rpath + '/aggregateR')
    if not repo.bare:
        print("Repo loaded successful at {}".format(rpath))
        g = repo.git
        try:
            g.checkout('HEAD', b=branch)
        except:
            print("{} already exists".format(branch))
        try:
            g.checkout(branch)
        except:
            print("{} already on branch".format(branch))
        try:
            o = repo.remotes.origin
            o.pull()
        except:
            print("pull failed")
    else:
        print("Repo not found at {}".format(rpath))

def is_repo_feedstock(feed, rpath = './run/aggregateR'):
    epath = rpath + '/' + feed
    return os.path.isdir(epath)

# The Microsoft CRAN time machine allows us to select a snapshot of CRAN at any day in time. For instance, 2018-01-01 is (in Microsoft's determination) the "official" snapshot date for R 3.4.3.

def get_anaconda_pkglist(rdata, arch, rchannel, ver, start_with = 'r'):
    """ Read from r channel architecture specific package list with specific version """
    pkgs = set(v['name'][2:] for v in rdata['packages'].values() if v['name'].startswith('r-') and v['build'].startswith('' + start_with + Rver))
    print('{} Anaconda R {} packages in {} found.'.format(len(pkgs), arch, rchannel))
    return pkgs

def build_anaconda_pkglist(rver, rchannel = 'r'):
    """ Get list of available packages from r or r_test channel for given version """
    pkgs = set()
    archs = ['noarch', 'linux-32', 'linux-64', 'win-32', 'win-64', 'osx-64']
    for arch in archs:
        rdata = {}
        if rchannel == 'r':
            url = 'https://repo.anaconda.com/pkgs/{}/{}/repodata.json'.format(rchannel, arch)
        else:
            url = 'https://conda.anaconda.org/{}/{}/repodata.json'.format(rchannel, arch)
        repodata = session.get(url)
        if repodata.status_code != 200:
            print('\n{} returned code {}'.format(url, page.status_code))
        else:
            rdata = json.loads(repodata.text)
            pkgs2 = get_anaconda_pkglist(rdata, arch, rchannel, rver)
            pkgs.update(pkgs2)
            # we don't look at mro packages

    print('{} Total Anaconda packages found in {}.'.format(len(pkgs), rchannel))
    # print(list(pkgs))
    return pkgs

def write_out_resheader(fd, has_wbuildpack):
    fd.write('resources:\n')
    if has_wbuildpack == True:
      fd.write('- name: rsync-build-pack\n')
      fd.write('  type: rsync-resource\n')
      fd.write('  source:\n')
      fd.write('    base_dir: /ci/build_pack\n')
      fd.write('    disable_version_path: true\n')
      fd.write('    private_key: ((common.intermediate-private-key))\n')
      fd.write('    server: bremen.corp.continuum.io\n')
      fd.write('    user: ci\n')


def write_out_reslinux64(fd, name):
    # resource for linux-64
    fd.write('- name: rsync_{}-on-linux_64\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_resosx64(fd, name):
    fd.write('- name: rsync_{}-on-osx\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_reswin64(fd, name):
    fd.write('- name: rsync_{}-on-winbuilder\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_reswin32(fd, name):
    fd.write('- name: rsync_{}-target_win-32-on-winbuilder\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_resfooter(fd):
    fd.write('resource_types:\n')
    fd.write('- name: rsync-resource\n')
    fd.write('  type: docker-image\n')
    fd.write('  source:\n')
    fd.write('    repository: conda/concourse-rsync-resource\n')
    fd.write('    tag: latest\n')

def write_out_pipeline_res(fd, j_comp, j_noa):
    write_out_resheader(fd, j_comp > 0)
    for x in range(0, j_comp):
        name = 'build_r_script{}'.format(x)
        write_out_reslinux64(fd, name)
        write_out_resosx64(fd, name)
        write_out_reswin64(fd, name)
        if enabled_win32 == True:
            write_out_reswin32(fd, name)
    for x in range(0, j_noa):
        name = 'build_r_script{}'.format(x+j_comp)
        write_out_reslinux64(fd, name)
    write_out_resfooter(fd)

def write_out_onwin32(fd, feedstocks, name):
    # job for windows
    fd.write('- name: {}-target_win-32-on-winbuilder\n'.format(name))
    fd.write('  plan:\n')
    fd.write('  - get: rsync-build-pack\n')
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --include\n')
    fd.write('      - windows_build_env_latest.zip\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'*\'\n')
    fd.write('      - -v\n')
    fd.write('  - task: build\n')
    fd.write('    config:\n')
    fd.write('      platform: windows\n')
    fd.write('      params:\n')
    fd.write('        GITHUB_TOKEN: ((common.recipe-repo-access-token))\n')
    fd.write('        GITHUB_USER: SA-PCR-RO\n')
    fd.write('      run:\n')
    fd.write('        path: cmd.exe\n')
    fd.write('        args:\n')
    fd.write('        - /c\n')
    fd.write('        - hostname&& mkdir build_env&& echo %CD%&& echo Extracting build environment&&\n')
    fd.write('          7z x ./rsync-build-pack/windows_build_env_latest.zip -o./build_env -y&&\n')
    fd.write('          echo Activating build environment&& call .\\build_env\\Scripts\\activate&&\n')
    fd.write('          echo Unpacking environment&& conda-unpack&& conda config --system --set\n')
    fd.write('          add_pip_as_python_dependency False&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/main&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/r&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/msys2&& conda info&& (echo machine github.com\n')
    fd.write('          login %GITHUB_USER% password %GITHUB_TOKEN% protocol https > %USERPROFILE%\_netrc\n')
    fd.write('          || exit 0)&& (echo machine github.com login %GITHUB_USER% password %GITHUB_TOKEN%\n')
    fd.write('          protocol https > %USERPROFILE%\_netrc || exit 0)&& (set CONDA_SUBDIR=win-32 ) &&\n')
    fd.write('          git clone {} &&\n'.format(RrepositoryURL2))
    fd.write('          cd aggregateR && git checkout latest_update && cd .. &&\n')
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write('          conda-build --no-test --no-anaconda-upload --no-error-overlinking --output-folder=output-artifacts\n')
    fd.write('          --cache-dir=output-source --stats-file=stats/{}8-on-winbuilder_1564756033.json\n'.format(name))
    fd.write('          --croot C:\\ci --skip-existing --R {} -c local -c r_test -m {}/conda_build_config.yaml\n'.format(Rfullver, RrepositoryName))
    # write the list of feedstocks ...
    fd.write(feedstocks)
    fd.write('          \n')
    fd.write('      inputs:\n')
    fd.write('      - name: rsync-build-pack\n')
    fd.write('      outputs:\n')
    fd.write('      - name: output-artifacts\n')
    fd.write('      - name: output-source\n')
    fd.write('      - name: stats\n')
    fd.write('  - put: rsync_{}-target_win-32-on-winbuilder\n'.format(name))
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --archive\n')
    fd.write('      - --no-perms\n')
    fd.write('      - --omit-dir-times\n')
    fd.write('      - --verbose\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.json*"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.*ml"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/.cache"\'\n')
    fd.write('      sync_dir: output-artifacts\n')
    fd.write('    get_params:\n')
    fd.write('      skip_download: true\n')

def write_out_onwin64(fd, feedstocks, name):
    # job for windows
    fd.write('- name: {}-on-winbuilder\n'.format(name))
    fd.write('  plan:\n')
    fd.write('  - get: rsync-build-pack\n')
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --include\n')
    fd.write('      - windows_build_env_latest.zip\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'*\'\n')
    fd.write('      - -v\n')
    fd.write('  - task: build\n')
    fd.write('    config:\n')
    fd.write('      platform: windows\n')
    fd.write('      params:\n')
    fd.write('        GITHUB_TOKEN: ((common.recipe-repo-access-token))\n')
    fd.write('        GITHUB_USER: SA-PCR-RO\n')
    fd.write('      run:\n')
    fd.write('        path: cmd.exe\n')
    fd.write('        args:\n')
    fd.write('        - /c\n')
    fd.write('        - hostname&& mkdir build_env&& echo %CD%&& echo Extracting build environment&&\n')
    fd.write('          7z x ./rsync-build-pack/windows_build_env_latest.zip -o./build_env -y&&\n')
    fd.write('          echo Activating build environment&& call .\\build_env\\Scripts\\activate&&\n')
    fd.write('          echo Unpacking environment&& conda-unpack&& conda config --system --set\n')
    fd.write('          add_pip_as_python_dependency False&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/main&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/r&& conda config --system --add default_channels\n')
    fd.write('          https://repo.anaconda.com/pkgs/msys2&& conda info&& (echo machine github.com\n')
    fd.write('          login %GITHUB_USER% password %GITHUB_TOKEN% protocol https > %USERPROFILE%\_netrc\n')
    fd.write('          || exit 0)&& (echo machine github.com login %GITHUB_USER% password %GITHUB_TOKEN%\n')
    fd.write('          protocol https > %USERPROFILE%\_netrc || exit 0)&&\n')
    fd.write('          git clone {} &&\n'.format(RrepositoryURL2))
    fd.write('          cd aggregateR && git checkout latest_update && cd .. &&\n')
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write('          conda-build --no-test --no-anaconda-upload --no-error-overlinking --output-folder=output-artifacts\n')
    fd.write('          --cache-dir=output-source --stats-file=stats/{}8-on-winbuilder_1564756033.json\n'.format(name))
    fd.write('          --croot C:\\ci --skip-existing --R {} -c local -c r_test -m {}/conda_build_config.yaml\n'.format(Rfullver, RrepositoryName))
    # write the list of feedstocks ...
    fd.write(feedstocks)
    fd.write('          \n')
    fd.write('      inputs:\n')
    fd.write('      - name: rsync-build-pack\n')
    fd.write('      outputs:\n')
    fd.write('      - name: output-artifacts\n')
    fd.write('      - name: output-source\n')
    fd.write('      - name: stats\n')
    fd.write('  - put: rsync_{}-on-winbuilder\n'.format(name))
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --archive\n')
    fd.write('      - --no-perms\n')
    fd.write('      - --omit-dir-times\n')
    fd.write('      - --verbose\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.json*"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.*ml"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/.cache"\'\n')
    fd.write('      sync_dir: output-artifacts\n')
    fd.write('    get_params:\n')
    fd.write('      skip_download: true\n')
    
def write_out_onlinux64(fd, feedstocks, name):
    # job for linux 64
    fd.write('- name: {}-on-linux_64\n'.format(name))
    fd.write('  plan:\n')
    fd.write('  - task: build\n')
    fd.write('    config:\n')
    fd.write('      platform: linux\n')
    fd.write('      image_resource:\n')
    fd.write('        type: docker-image\n')
    fd.write('        source:\n')
    fd.write('          repository: conda/c3i-linux-64\n')
    fd.write('          tag: latest\n')
    fd.write('      params:\n')
    fd.write('        GITHUB_TOKEN: ((common.recipe-repo-access-token))\n')
    fd.write('        GITHUB_USER: SA-PCR-RO\n')
    fd.write('      run:\n')
    fd.write('        path: sh\n')
    fd.write('        args:\n')
    fd.write('        - -exc\n')
    fd.write('        - conda update -y conda-build&& conda config --set add_pip_as_python_dependency\n')
    fd.write('          False&& conda config --add default_channels https://repo.anaconda.com/pkgs/main&&\n')
    fd.write('          conda config --add default_channels https://repo.anaconda.com/pkgs/r&& conda\n')
    fd.write('          info&& set +x&& echo machine github.com login $GITHUB_USER password $GITHUB_TOKEN\n')
    fd.write('          protocol https > ~/.netrc&& set -x &&\n')
    fd.write('          git clone {} &&\n'.format(RrepositoryURL2))
    fd.write('          cd aggregateR && git checkout latest_update && cd .. &&\n')
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write('          conda-build --no-anaconda-upload --error-overlinking --R {} -c local -c r_test\n'.format(Rfullver))
    fd.write('          --output-folder=output-artifacts --cache-dir=output-source --stats-file=stats/{}-on-linux_64_1564756033.json\n'.format(name))
    fd.write('          --skip-existing --croot . -m ./{}/conda_build_config.yaml\n'.format(RrepositoryName))
    # write the list of feedstocks ...
    fd.write(feedstocks)
    fd.write('          \n')
    fd.write('      outputs:\n')
    fd.write('      - name: output-artifacts\n')
    fd.write('      - name: output-source\n')
    fd.write('      - name: stats\n')
    fd.write('  - put: rsync_{}-on-linux_64\n'.format(name))
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --archive\n')
    fd.write('      - --no-perms\n')
    fd.write('      - --omit-dir-times\n')
    fd.write('      - --verbose\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.json*"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.*ml"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/.cache"\'\n')
    fd.write('      sync_dir: output-artifacts\n')
    fd.write('    get_params:\n')
    fd.write('      skip_download: true\n')

def write_out_onosx64(fd, feedstocks, name):
    # job for linux 64
    fd.write('- name: {}-on-osx\n'.format(name))
    fd.write('  plan:\n')
    fd.write('  - get: rsync-build-pack\n')
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --include\n')
    fd.write('      - osx_build_env_latest.zip\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'*\'\n')
    fd.write('      - -v\n')
    fd.write('  - task: build\n')
    fd.write('    config:\n')
    fd.write('      platform: darwin\n')
    fd.write('      params:\n')
    fd.write('        GITHUB_TOKEN: ((common.recipe-repo-access-token))\n')
    fd.write('        GITHUB_USER: SA-PCR-RO\n')
    fd.write('      run:\n')
    fd.write('        path: sh\n')
    fd.write('        args:\n')
    fd.write('        - -exc\n')
    fd.write('        - hostname&& pwd&& mkdir build_env&& unzip -o -q rsync-build-pack/osx_build_env_latest.zip\n')
    fd.write('          -d build_env&& source build_env/bin/activate&& conda-unpack&& conda init&&\n')
    fd.write('          source build_env/etc/profile.d/conda.sh&& conda config --set add_pip_as_python_dependency\n')
    fd.write('          False&& conda config --add default_channels https://repo.anaconda.com/pkgs/main&&\n')
    fd.write('          conda config --add default_channels https://repo.anaconda.com/pkgs/r&& conda\n')
    fd.write('          info&& set +x&& echo machine github.com login $GITHUB_USER password $GITHUB_TOKEN\n')
    fd.write('          protocol https > ~/.netrc&& set -x&& set +x&& echo machine github.com login\n')
    fd.write('          $GITHUB_USER password $GITHUB_TOKEN protocol https > ~/.netrc&& set -x&&\n')
    fd.write('          set +x&& echo machine github.com login $GITHUB_USER password $GITHUB_TOKEN\n')
    fd.write('          protocol https > ~/.netrc&& set -x&& set +x&& echo machine github.com login\n')
    fd.write('          $GITHUB_USER password $GITHUB_TOKEN protocol https > ~/.netrc&& set -x&&\n')
    fd.write('          git clone {} &&\n'.format(RrepositoryURL2))
    fd.write('          cd aggregateR && git checkout latest_update && cd .. &&\n')
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write('          conda-build --no-anaconda-upload --error-overlinking --output-folder=output-artifacts\n')
    fd.write('          --cache-dir=output-source --stats-file=stats/{}-on-osx_1564756033.json\n'.format(name))
    fd.write('          --skip-existing -c local -c r_test --R {} --croot . -m ./{}/conda_build_config.yaml\n'.format(Rfullver, RrepositoryName))
    # write the list of feedstocks ...
    fd.write(feedstocks)
    fd.write('          \n')
    fd.write('      inputs:\n')
    fd.write('      - name: rsync-build-pack\n')
    fd.write('      outputs:\n')
    fd.write('      - name: output-artifacts\n')
    fd.write('      - name: output-source\n')
    fd.write('      - name: stats\n')
    fd.write('  - put: rsync_{}-on-osx\n'.format(name))
    fd.write('    params:\n')
    fd.write('      rsync_opts:\n')
    fd.write('      - --archive\n')
    fd.write('      - --no-perms\n')
    fd.write('      - --omit-dir-times\n')
    fd.write('      - --verbose\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.json*"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/*.*ml"\'\n')
    fd.write('      - --exclude\n')
    fd.write('      - \'"**/.cache"\'\n')
    fd.write('      sync_dir: output-artifacts\n')
    fd.write('    get_params:\n')
    fd.write('      skip_download: true\n')

def write_fly_pipelines_exist(p_noarch, p_comp):
    ip = 0
    i = 0
    inoa = 0
    inoa_max = len(p_noarch)
    icom = 0
    icom_max = len(p_comp)
    lmax = inoa_max + icom_max
    while i < lmax:
        bld_icom = icom_max - icom
        bld_inoa = inoa_max - inoa
        inoa_jobs = math.floor((bld_inoa + 49) / 50)
        icom_jobs = math.floor((bld_icom + 9) / 10)
        bld_icom = min(bld_icom, icom_jobs * 10)
        bld_inoa = min(bld_inoa, inoa_jobs * 50)
        if inoa_jobs > 27:
            icom_jobs = 0
            if inoa_jobs > 30:
                inoa_jobs = 30
        max_cjobs = math.floor((30 - inoa_jobs + 2) / 3)
        if icom_jobs > max_cjobs:
            icom_jobs = max_cjobs
        bld_icom = min(bld_icom, icom_jobs * 10)
        bld_inoa = min(bld_inoa, inoa_jobs * 50)
        write_out_one_pipeline_exist(ip, icom, bld_icom, inoa, bld_inoa, icom_jobs, inoa_jobs, p_noarch, p_comp)
        i += bld_icom + bld_inoa
        icom += bld_icom
        inoa += bld_inoa
        ip += 1

def get_one_job_feedstocks(names, idx, sec, num, secmax):
    ret = ''
    idx += sec * secmax
    num -= sec * secmax
    num = min(num, secmax)
    idxmax = num + idx
    while idx < idxmax:
        p = names[idx]
        ret += '          {}/r-{}-feedstock\n'.format(RrepositoryName, p.lower())
        idx += 1
    return ret

def get_one_job_cran_names(names, idx, sec, num, secmax):
    ret = ''
    idx += sec * secmax
    num -= sec * secmax
    num = min(num, secmax)
    idxmax = num + idx
    while idx < idxmax:
        p = names[idx]
        ret += ' {}'.format(p)
        idx += 1
    return ret

def write_out_one_pipeline_exist(num, idx_comp, num_comp, idx_noa, num_noa, j_comp, j_noa, p_noarch, p_comp):
    if not os.path.exists('./exists'):
        os.mkdir('./exists')
    with open(f'./exists/p{num}.sh', 'w') as pd:
        pd.write('#/bash/bin\n\n')
        pd.write('# put pileline upstream via:\n')
        pd.write('fly -t conda-concourse-server sp -p kais_test_r \\\n')
        pd.write('  -c ./pipeline{}.yaml -l ~/Code/oss/automated-build/c3i_configurations/anaconda_public/config.yml\n'.format(num))
        pd.write('fly -t conda-concourse-server up -p kais_test_r\n')
        pd.write('\n')
        for x in range(0, j_comp):
            name = 'build_r_script{}'.format(x)
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-osx\n'.format(name))
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-linux_64\n'.format(name))
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-winbuilder\n'.format(name))
            if enabled_win32 == True:
                # windows 32-bit
                pd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-target_win-32-on_winbuilder\n'.format(name))
        for x in range(0, j_noa):
            name = 'build_r_script{}'.format(x + j_comp)
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-linux_64\n'.format(name))
        pd.write('echo "{} jobs triggered"\n'.format(j_comp + j_noa))
    
    with open(f'./exists/pipeline{num}.yaml', 'w') as fd:
        fd.write('groups: []\n')
        write_out_pipeline_res(fd, j_comp, j_noa)
        # write out the jobs ... first the compiled ones ...
        fd.write('jobs:\n')
        for x in range(0, j_comp):
            name = 'build_r_script{}'.format(x)
            cnames = get_one_job_cran_names(p_comp, idx_comp, x, num_comp, 10)
            if enable_skeleton_for_existing:
                call_skeleton_for(cnames, name)
            feedstocks = get_one_job_feedstocks(p_comp, idx_comp, x, num_comp, 10)
            write_out_onlinux64(fd, feedstocks, name)
            write_out_onosx64(fd, feedstocks, name)
            write_out_onwin64(fd, feedstocks, name)
            if enabled_win32 == True:
                write_out_onwin32(fd, feedstocks, name)
        for x in range(0, j_noa):
            name = 'build_r_script{}'.format(x + j_comp)
            cnames = get_one_job_cran_names(p_noarch, idx_noa, x, num_noa, 50)
            if enable_skeleton_for_existing:
                call_skeleton_for(cnames, name)
            feedstocks = get_one_job_feedstocks(p_noarch, idx_noa, x, num_noa, 50)
            write_out_onlinux64(fd, feedstocks, name)

def call_skeleton_for(names, ident):
    print("Generating skeleton files for ,{}': ...".format(ident))
    s = 'conda skeleton cran --cran-url={} --output-suffix=-feedstock/recipe {}'.format(CRAN_BASE, do_recursive)
    s += ' --add-maintainer={} --update-policy=merge-keep-build-num --r-interp=r-base --use-noarch-generic'.format(RecipeMaintainer)
    s += names

    os.chdir('./run/aggregateR')
    subprocess.call(s.split())
    os.chdir('../..')

pandas2ri.activate()
readRDS = robjects.r['readRDS']
session = requests.Session()

get_ipython().run_line_magic('matplotlib', 'auto')

anaconda_pkgs = build_anaconda_pkglist(rver = Rver)
# for testing we are also look into 'r_test' channel
tmp = build_anaconda_pkglist(rver = Rver, rchannel = 'r_test')
anaconda_pkgs.update(tmp)

built_pkgs = set()

# get the CRAN packages ...
pkgs = requests.get(CRAN_BASE + '/src/contrib/PACKAGES').text
items = [message_from_string(pkg) for pkg in pkgs.split('\n\n')]

def deps_set(dep):
    if dep is None:
        return emptyset
    return set(it.replace('(', ' (').strip().split()[0] for it in dep.split(',') if it.strip())


# We're only looking for the tarballs in the `/src/contrib` directory, so the easiest way to do that is to scrape the index page.

packages = set(item['package'] for item in items)
count_packages = len(packages)
for x in packages:
  for xx in anaconda_pkgs:
     s = x.lower()
     if s in xx.lower():
        count_packages -= 1
        break

print('{} CRAN R packages found, {} not found in defaults.'.format(len(packages), count_packages))

emptyset = set()
BASE_PACKAGES = {'R', 'base', 'compiler', 'datasets', 'graphics', 'grDevices', 'grid', 'methods',
                 'parallel', 'splines', 'stats', 'stats4', 'tcltk', 'tools', 'translations', 'utils'}
summary = {}
for data in items:
    deps = deps_set(data.get('depends')) | deps_set(data.get('imports')) | deps_set(data.get('linkingto'))
    record = {'compiled':data.get('needscompilation', 'no'), 'depends':deps - BASE_PACKAGES, 'version': data.get('version')}
    summary[data['package']] = record
    
summary = pd.DataFrame(summary).T
summary.index.name = 'name'
summary.reset_index(inplace=True)
summary.compiled = summary.compiled.str.lower() != 'no'

packages = set(summary['name'])

summary['valid'] = summary.depends.apply(lambda x: x.issubset(packages))
summary[~summary.valid]


all_supers = pd.Series([None] * len(summary), index=summary.name)
all_deps = pd.Series(summary.depends.values, index=summary.name)
all_compiled = pd.Series(summary.compiled.values, index=summary.name)

def compute_super(name):
    superdeps = all_supers[name]
    if superdeps is None:
        deps = all_deps[name]
        all_supers[name] = superdeps = deps.copy()
        for dep in deps:
            if dep in packages:
                superdeps.update(compute_super(dep))
    return superdeps
for name in summary.name:
    compute_super(name)
summary['superdepends'] = all_supers.values
summary['n_depends'] = summary.depends.apply(len)
summary['n_superdepends'] = summary.superdepends.apply(len)
summary


summary['valid'] = summary.superdepends.apply(lambda x: x.issubset(packages))
summary[~summary.valid]

if show_just_unbuilt:
    completed = built_pkgs | anaconda_pkgs
else:
    completed = built_pkgs

candidates = summary[summary.valid & ~summary.name.str.lower().isin(completed)].set_index('name')

# We need to checkout aggregateR repository and make sure paths are created
get_aggregateR_repo()

to_compile = []
stages = []
existings = []
while len(candidates):
    can_do = candidates.superdepends.apply(lambda x: completed.issuperset(a.lower() for a in x))
    can_do = candidates.index[can_do]
    if len(can_do) == 0:
        break
    cds = []
    eds = []
    for x in can_do:
        if is_repo_feedstock('r-' + x.lower() + '-feedstock'):
            eds.append(x)
        else:
            cds.append(x)
    candidates = candidates.drop(can_do, 'index')
    completed.update(a.lower() for a in can_do)
    to_compile.extend(can_do)
    stages.append(cds)
    existings.append(eds)
    if len(candidates) != 0:
        print("Remaining candidates {}".format(len(candidates)))

# build pkg list
p_noarch = []
p_comp = []
for i, stage in enumerate(existings):
    for x in stage:
        if is_noarch(x, all_compiled):
            p_noarch.append(x)
        else:
            p_comp.append(x)
    if len(p_noarch) > 0 or len(p_comp) > 0:
        break
print("Existing stage contains {} noarch and {} compiled packages".format(len(p_noarch), len(p_comp)))

# write out pipeline file
write_fly_pipelines_exist(p_noarch, p_comp)

print("Done.")

