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

do_submodul='          cd aggregate && git submodule update --init && cd .. &&\n'
do_cb1='          conda-build --no-anaconda-upload --no-error-overlinking --output-folder=output-artifacts\n'

RrepositoryName = 'aggregate'
RrepositoryURL = 'git@github.com:AnacondaRecipes/aggregate.git'
RrepositoryURL2 = 'https://github.com/AnacondaRecipes/aggregate.git'
RecipeMaintainer = 'katietz'
PYver = '38'

batch_count_max=100
do_recursive = '' # '--dirty --recursive'
do_python = '--python=3.8'

def is_noarch(name, acompiled):
    return acompiled[name] == False

def is_dependon(name, adepends):
    for dep in adepends:
        if name in dep:
            return True
    return False

def get_aggregate_repo(rpath = './run'):
    if not os.path.exists(rpath):
        os.mkdir(rpath)
        print("Path {} does not exist creating".format(rpath))
    if not os.path.exists(rpath + '/aggregate'):
        repo = git.Repo.clone_from('git@github.com:AnacondaRecipes/aggregate.git', rpath + '/aggregate')
    else:
        repo = git.Repo(rpath + '/aggregate')
    if not repo.bare:
        print("Repo loaded successful at {}".format(rpath))
        g = repo.git
        try:
            g.checkout('master')
        except:
            print("'master' already on branch")
    else:
        print("Repo not found at {}".format(rpath))

def is_repo_feedstock(feed, rpath = './run/aggregate'):
    epath = rpath + '/' + feed
    return os.path.isdir(epath)

def get_anaconda_pkglist(rdata, arch, rchannel, ver, start_with = 'py'):
    """ Read from r channel architecture specific package list with specific version """
    pystr = start_with + ver
    pkgs = set(v['name'] for v in rdata['packages'].values() if v['build'].find(pystr) >= 0)
    print('{} Anaconda {}-packages in {} found.'.format(len(pkgs), arch, rchannel))
    return pkgs

def build_anaconda_pkglist(rver, rchannel = 'main'):
    """ Get list of available packages from r or r_test channel for given version """
    pkgs = set()
    deps = []
    archs = ['noarch', 'linux-32', 'linux-64', 'win-32', 'win-64', 'osx-64']
    for arch in archs:
        rdata = {}
        if rchannel == 'r' or rchannel == 'main':
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
        pystr = 'py' + rver
        print(' {} {}:\n'.format(arch, pystr))
        for v in rdata['packages'].values():
            bn = v['build']
            if bn.find(pystr) >= 0:
                nn = v['name']
                if is_feedstock_exists(nn + '-feedstock'):
                    if not find_in_deps(nn, deps):
                       deps.append(v)
                       print(' {} # {}'.format(nn, bn))
                    else:
                       print(' {}* # {}'.format(nn, bn))
                else:
                    print("{} does not exists in repository".format(nn))
    print('{} Total Anaconda packages found in {}.'.format(len(pkgs), rchannel))
    # print(deps)
    return pkgs, deps

def find_in_deps(bn, deps):
    for v in deps:
       n = v['name']
       if n == bn:
         return True
    return False

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
    fd.write('    base_dir: /ci/ktietz/artifacts_py\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_resosx64(fd, name):
    fd.write('- name: rsync_{}-on-osx\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts_py\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_reswin64(fd, name):
    fd.write('- name: rsync_{}-on-winbuilder\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts_py\n')
    fd.write('    disable_version_path: true\n')
    fd.write('    private_key: ((common.intermediate-private-key))\n')
    fd.write('    server: bremen.corp.continuum.io\n')
    fd.write('    user: ci\n')

def write_out_reswin32(fd, name):
    fd.write('- name: rsync_{}-target_win-32-on-winbuilder\n'.format(name))
    fd.write('  type: rsync-resource\n')
    fd.write('  source:\n')
    fd.write('    base_dir: /ci/ktietz/artifacts_py\n')
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
        name = 'build_py_script{}'.format(x)
        write_out_reslinux64(fd, name)
        write_out_resosx64(fd, name)
        write_out_reswin64(fd, name)
        if enabled_win32 == True:
            write_out_reswin32(fd, name)
    for x in range(0, j_noa):
        name = 'build_py_script{}'.format(x+j_comp)
        write_out_reslinux64(fd, name)
    write_out_resfooter(fd)

def write_out_onwin32(fd, feedstocks, name, feedstocks_git):
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
    write_submodule(fd, feedstocks_git)
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write(do_cb1)
    fd.write('          {}\n'.format(do_python))
    fd.write('          --cache-dir=output-source --stats-file=stats/{}8-on-winbuilder_1564756033.json\n'.format(name))
    fd.write('          --croot C:\\ci --skip-existing -c local -m {}/conda_build_config.yaml\n'.format(RrepositoryName))
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

def write_submodule(fd, feedstocks_git):
    if feedstocks_git != '':
        fd.write('          cd aggregate && git submodule update --init \n')
        fd.write(feedstocks_git)
        fd.write('          && cd .. &&\n')

def write_out_onwin64(fd, feedstocks, name, feedstocks_git):
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
    write_submodule(fd, feedstocks_git)
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write(do_cb1)
    fd.write('          {}\n'.format(do_python))
    fd.write('          --cache-dir=output-source --stats-file=stats/{}8-on-winbuilder_1564756033.json\n'.format(name))
    fd.write('          --croot C:\\ci --skip-existing -c local -m {}/conda_build_config.yaml\n'.format(RrepositoryName))
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
    
def write_out_onlinux64(fd, feedstocks, name, feedstocks_git):
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
    write_submodule(fd, feedstocks_git)
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write(do_cb1)
    fd.write('          {}\n'.format(do_python))
    fd.write('          -c local --output-folder=output-artifacts --cache-dir=output-source --stats-file=stats/{}-on-linux_64_1564756033.json\n'.format(name))
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

def write_out_onosx64(fd, feedstocks, name, feedstocks_git):
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
    write_submodule(fd, feedstocks_git)
    fd.write('          conda update -y -n base conda && conda update -y --all &&\n')
    fd.write(do_cb1)
    fd.write('          {}\n'.format(do_python))
    fd.write('          --cache-dir=output-source --stats-file=stats/{}-on-osx_1564756033.json\n'.format(name))
    fd.write('          --skip-existing -c local --croot . -m ./{}/conda_build_config.yaml\n'.format(RrepositoryName))
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

def write_fly_pipelines(p_noarch, p_comp, stageno):
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
        write_out_one_pipeline_exist(ip, icom, bld_icom, inoa, bld_inoa, icom_jobs, inoa_jobs, p_noarch, p_comp, stageno)
        i += bld_icom + bld_inoa
        icom += bld_icom
        inoa += bld_inoa
        ip += 1

def get_one_job_feedstocks(names, idx, sec, num, secmax):
    ret = ''
    ret_git = ''
    idx += sec * secmax
    num -= sec * secmax
    num = min(num, secmax)
    idxmax = num + idx
    while idx < idxmax:
        p = names[idx]
        ret += '          {}/{}-feedstock/recipe/meta.yaml\n'.format(RrepositoryName, p.lower())
        if is_feedstock_submodule(p.lower() + '-feedstock'):
          ret_git += '          {}-feedstock\n'.format(p.lower())
        idx += 1
    return ret, ret_git

def is_feedstock_submodule(feedstock):
    p = './run/aggregate/{}/.git'.format(feedstock)
    return os.path.exists(p)

def is_feedstock_exists(feedstock):
    p = './run/aggregate/{}'.format(feedstock)
    return os.path.exists(p)

def write_out_one_pipeline_exist(num, idx_comp, num_comp, idx_noa, num_noa, j_comp, j_noa, p_noarch, p_comp, stageno):
    if not os.path.exists('./pybld'):
        os.mkdir('./pybld')
    with open(f'./pybld/p{stageno}_{num}.sh', 'w') as pd:
        pd.write('#/bash/bin\n\n')
        pd.write('# put pileline upstream via:\n')
        pd.write('fly -t conda-concourse-server sp -p kais_test_py \\\n')
        pd.write('  -c ./pipeline{}_{}.yaml -l ~/Code/oss/automated-build/c3i_configurations/anaconda_public/config.yml\n'.format(stageno, num))
        pd.write('fly -t conda-concourse-server up -p kais_test_py\n')
        pd.write('\n')
        for x in range(0, j_comp):
            name = 'build_py_script{}'.format(x)
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_py/{}-on-osx\n'.format(name))
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_py/{}-on-linux_64\n'.format(name))
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_py/{}-on-winbuilder\n'.format(name))
            if enabled_win32 == True:
                # windows 32-bit
                pd.write('fly -t conda-concourse-server trigger-job -j kais_test_py/{}-target_win-32-on_winbuilder\n'.format(name))
        for x in range(0, j_noa):
            name = 'build_py_script{}'.format(x + j_comp)
            pd.write('fly -t conda-concourse-server trigger-job -j kais_test_py/{}-on-linux_64\n'.format(name))
        pd.write('echo "{} jobs triggered"\n'.format(j_comp + j_noa))
    
    with open(f'./pybld/pipeline{stageno}_{num}.yaml', 'w') as fd:
        fd.write('groups: []\n')
        write_out_pipeline_res(fd, j_comp, j_noa)
        # write out the jobs ... first the compiled ones ...
        fd.write('jobs:\n')
        for x in range(0, j_comp):
            name = 'build_py_script{}'.format(x)
            feedstocks, feedstocks_git = get_one_job_feedstocks(p_comp, idx_comp, x, num_comp, 10)
            write_out_onlinux64(fd, feedstocks, name, feedstocks_git)
            write_out_onosx64(fd, feedstocks, name, feedstocks_git)
            write_out_onwin64(fd, feedstocks, name, feedstocks_git)
            if enabled_win32 == True:
                write_out_onwin32(fd, feedstocks, name, feedstocks_git)
        for x in range(0, j_noa):
            name = 'build_py_script{}'.format(x + j_comp)
            feedstocks, feedstocks_git = get_one_job_feedstocks(p_noarch, idx_noa, x, num_noa, 50)
            write_out_onlinux64(fd, feedstocks, name, feedstocks_git)

def in_stages(stages, n):
  for s in stages:
    if n in s:
       return True
  return False

pandas2ri.activate()
readRDS = robjects.r['readRDS']
session = requests.Session()

get_ipython().run_line_magic('matplotlib', 'auto')

# Fetch repro for further analyzis required!!
get_aggregate_repo()

anaconda_pkgs,deps37 = build_anaconda_pkglist(rver = '37', rchannel = 'main')
pkg38, deps38 = build_anaconda_pkglist(rver = '38', rchannel = 'main')

stages = []

lend = len(deps37)
print("found {} python packages".format(lend))
changed = True
while changed == True:
   stage = []
   changed = False
   for v in deps37:
     n = v['name']
     if not in_stages(stages, n):
       dep = v['depends']
       hasdep = False
       for d in dep:
          dn = d.split()[0]
          if not in_stages(stages,dn):
            for vv in deps37:
              na = vv['name']
              if na != n and na == dn:
                hasdep = True
                break
            if hasdep:
              break
       if n in stage:
          hasdep = True
       if hasdep == False:
         changed=True
         stage.append(n)
   if len(stage) > 0:
     stages.append(stage)
p_noarch = []
i = 1
for st in stages:
  print("stage {}\n====\n".format(i))
  print(*st)
  write_fly_pipelines(p_noarch, st, i)
  i += 1

print("{} stage".format(len(stages)))
print("Done.")

