#!/usr/bin/env python
# coding: utf-8

# requires ipython rpy2 matplotlib tzlocal pandas

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

def write_out_resources(fd, cnt_jobs):
    fd.write('resources:\n')
    fd.write('- name: rsync-build-pack\n')
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/build_pack\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')
    for x in range(0, cnt_jobs):
        name = 'build_r_script{}'.format(x)
        # resource for linux-64
        fd.write('- name: rsync_{}-on-linux_64\n'.format(name))
        fd.write('  type: rsync-resource\n')
        fd.write('  source:\n')
        fd.write('    base_dir: /ci/ktietz/artifacts\n')
        fd.write('    disable_version_path: true\n')
        fd.write('    private_key: ((common.intermediate-private-key))\n')
        fd.write('    server: bremen.corp.continuum.io\n')
        fd.write('    user: ci\n')
        # resource for osx-64
        fd.write('- name: rsync_{}-on-osx\n'.format(name))
        fd.write('  type: rsync-resource\n')
        fd.write('  source:\n')
        fd.write('    base_dir: /ci/ktietz/artifacts\n')
        fd.write('    disable_version_path: true\n')
        fd.write('    private_key: ((common.intermediate-private-key))\n')
        fd.write('    server: bremen.corp.continuum.io\n')
        fd.write('    user: ci\n')
        # resource for windows 64
        fd.write('- name: rsync_{}-on-winbuilder\n'.format(name))
        fd.write('  type: rsync-resource\n')
        fd.write('  source:\n')
        fd.write('    base_dir: /ci/ktietz/artifacts\n')
        fd.write('    disable_version_path: true\n')
        fd.write('    private_key: ((common.intermediate-private-key))\n')
        fd.write('    server: bremen.corp.continuum.io\n')
        fd.write('    user: ci\n')
        if enabled_win32 == True:
            # windows 32-bit
            fd.write('- name: rsync_{}-target_win-32-on-winbuilder\n'.format(name))
            fd.write('  type: rsync-resource\n')
            fd.write('  source:\n')
            fd.write('    base_dir: /ci/ktietz/artifacts\n')
            fd.write('    disable_version_path: true\n')
            fd.write('    private_key: ((common.intermediate-private-key))\n')
            fd.write('    server: bremen.corp.continuum.io\n')
            fd.write('    user: ci\n')

    fd.write('resource_types:\n')
    fd.write('- name: rsync-resource\n')
    fd.write('  type: docker-image\n')
    fd.write('  source:\n')
    fd.write('    repository: conda/concourse-rsync-resource\n')
    fd.write('    tag: latest\n')

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
    fd.write('          --croot C:\\ci --skip-existing --R 3.6.1 -c local -c r_test -m {}/conda_build_config.yaml\n'.format(RrepositoryName))
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
    fd.write('          conda update -y -n base conda && conda update -y --all &
&\n')
    fd.write('          conda-build --no-test --no-anaconda-upload --no-error-overlinking --output-folder=output-artifacts\n')
    fd.write('          --cache-dir=output-source --stats-file=stats/{}8-on-winbuilder_1564756033.json\n'.format(name))
    fd.write('          --croot C:\\ci --skip-existing --R 3.6.1 -c local -c r_test -m {}/conda_build_config.yaml\n'.format(RrepositoryName))
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
    fd.write('          conda update -y -n base conda && conda update -y --all &
&\n')
    fd.write('          conda-build --no-anaconda-upload --error-overlinking --R 3.6.1 -c local -c r_test\n')
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

def bld_feedstocks_lines(stages, no):
    rslt = ''
    cnt = do_max_pkg_cnt
    for i, stage in enumerate(stages):
        scount = len(stage)
        j = 0
        elno = no * do_max_pkg_cnt
        while elno < scount and cnt > 0:
            p = stage[elno]
            rslt += '         {}/r-{}-feedstock\n'.format(RrepositoryName, p.lower())
            elno += 1
            cnt -= 1
        if cnt == 0 or elno >= scount:
            break
    # end for
    return rslt

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
    fd.write('          conda update -y -n base conda && conda update -y --all &
&\n')
    fd.write('          conda-build --no-anaconda-upload --error-overlinking --output-folder=output-artifacts\n')
    fd.write('          --cache-dir=output-source --stats-file=stats/{}-on-osx_1564756033.json\n'.format(name))
    fd.write('          --skip-existing -c local -c r_test --R 3.6.1 --croot . -m ./{}/conda_build_config.yaml\n'.format(RrepositoryName))
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

def write_out_bld_job_fly_trigger(cnt_jobs):
    # write out 
    with open(f'./pipeline-build-stage.sh', 'w') as fd:
        fd.write('#!/bin/bash\n\n')
        fd.write('# put pileline upstream via:\n')
        fd.write('#  fly -t conda-concourse-server sp -p kais_test_r\n')
        fd.write('#     -c pipeline-build-stage.yaml -l ...anaconda_public/config.yml\n')
        fd.write('fly -t conda-concourse-server up -p kais_test_r\n')
        fd.write('\n')
        for x in range(0, cnt_jobs):
            name = 'build_r_script{}'.format(x)
            fd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-osx\n'.format(name))
            fd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-linux_64\n'.format(name))
            fd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-on-winbuilder\n'.format(name))
            if enabled_win32 == True:
                # windows 32-bit
                fd.write('fly -t conda-concourse-server trigger-job -j kais_test_r/{}-target_win-32-on_winbuilder\n'.format(name))
        fd.write('echo "{} jobs triggered"\n'.format(cnt_jobs))

def write_out_bld_job(stages, cnt_jobs):
    # write out 
    with open(f'./pipeline-build-stage.yaml', 'w') as fd:
        fd.write('groups: []\n')
        write_out_resources(fd, cnt_jobs)
        # write out the jobs
        fd.write('jobs:\n')
        for x in range(0, cnt_jobs):
            name = 'build_r_script{}'.format(x)
            feedstocks = bld_feedstocks_lines(stages, no = x)
            write_out_onlinux64(fd, feedstocks, name)
            write_out_onosx64(fd, feedstocks, name)
            write_out_onwin64(fd, feedstocks, name)
            if enabled_win32 == True:
                write_out_onwin32(fd, feedstocks, name)

def write_out_bld_script(stages, jcnt, mode = 'sh'):
    cnt = jcnt
    comment_line = '#'
    sep_line = ' \\\n    '
    if mode != 'sh':
        comment_line = 'REM'
        sep_line = ' '
    with open(f'./build-stage.{mode}', 'w') as bd:
        if mode == 'sh':
            bd.write('#!/bin/bash\n\n')
        for i, stage in enumerate(stages):
            bd.write('{} stage {}\n'.format(comment_line, i))
            scount = len(stage)
            j = 0
            elno = 0
            while elno < scount and (cnt == -1 or cnt > 0):
                # Write out build steps ...
                bd.write('conda-build --skip-existing -c https://repo.continuum.io/pkgs/main --R={}{}'.format(Rfullver, sep_line))
                el = 0
                while elno < scount and el < batch_count_max and (cnt == -1 or cnt > 0):
                    p = stage[elno]
                    bd.write(' r-' + p.lower() + '-feedstock{}'.format(sep_line))
                    elno += 1
                    el += 1
                    if cnt != -1:
                        cnt -= 1
                j += 1
                # terminate lines ...
                bd.write('\n')
            bd.write('\n')
            print("State {} is splitted into {} parts".format(i, j))
            if cnt == 0:
                break
        # end for

def call_skeleton_cmds(stages, jcnt):
    os.chdir('./run/aggregateR')
    cnt = jcnt
    for i, stage in enumerate(stages):
        scount = len(stage)
        j = 0
        elno = 0
        while elno < scount and cnt > 0:
            # Write out skeleton creation ...
            bsd = 'conda skeleton cran --cran-url={} --output-suffix=-feedstock/recipe {}'.format(CRAN_BASE, do_recursive)
            bsd += ' --add-maintainer={} --update-policy=merge-keep-build-num --r-interp=r-base --use-noarch-generic'.format(RecipeMaintainer)
            el = 0
            while elno < scount and el < batch_count_max and cnt > 0:
                p = stage[elno]
                bsd += ' ' + p
                elno += 1
                el += 1
                cnt -= 1
            print("Call: {}".format(bsd))
            subprocess.call(bsd.split())
            j += 1
        print("State {} is splitted into {} parts".format(i, j))
        if cnt == 0:
            break
    # end for
    os.chdir('../..')

def get_stage_out_count(stages):
    rslt = 0
    for i, stage in enumerate(stages):
       cnt = len(stage)
       rslt += cnt
       if cnt != 0:
            break
    return rslt
       
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
print('{} CRAN R packages found, {} not found in defaults.'.format(len(packages), len(packages-anaconda_pkgs)))

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
summary

packages = set(summary['name'])

summary['valid'] = summary.depends.apply(lambda x: x.issubset(packages))
summary[~summary.valid]


all_supers = pd.Series([None] * len(summary), index=summary.name)
all_deps = pd.Series(summary.depends.values, index=summary.name)
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

completed = built_pkgs | anaconda_pkgs
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
    candidates = candidates.drop(can_do, 'index')
    cds = []
    for x in can_do:
        if is_repo_feedstock('r-' + x.lower() + '-feedstock'):
            existings.append(x)
            print("{} exists already in repo".format(x))
        else:
            cds.append(x)
    completed.update(a.lower() for a in can_do)
    to_compile.extend(can_do)
    stages.append(cds)
    if len(candidates) != 0:
        print("Remaining candidates {}".format(len(candidates)))

print("{} element(s) are already present in repo".format(len(existings)))
cnt_items = get_stage_out_count(stages)
cnt_jobs = math.floor((cnt_items / do_max_pkg_cnt))+1
print('In total there are {} feedstocks found to be built in {} job(s)\n'.format(cnt_items, cnt_jobs))
if cnt_jobs > 10:
    print('too much jobs!!!!! lowered to 10\n')
    cnt_jobs = 10
    cnt_items = cnt_jobs * do_max_pkg_cnt

#write out pipeline file
write_out_bld_job(stages, cnt_jobs)
write_out_bld_job_fly_trigger(cnt_jobs)

# write scripts ...
write_out_bld_script(stages, cnt_items, mode = 'sh')
write_out_bld_script(stages, cnt_items, mode = 'bat')

call_skeleton_cmds(stages, cnt_items)

print("Done.")

