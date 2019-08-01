#!/usr/bin/env python
# coding: utf-8

from bs4 import BeautifulSoup
import rpy2.robjects as robjects
from rpy2.robjects import pandas2ri
import requests
import json
import pandas as pd
import numpy as np
import re, os, time, shutil


# The Microsoft CRAN time machine allows us to select a snapshot of CRAN at any day in time. For instance, 2018-01-01 is (in Microsoft's determination) the "official" snapshot date for R 3.4.3.

def get_r_channel_rdata(arch):
   """ Read from r channel architecture specific information """
   rdata = {}
   url = "https://repo.anaconda.com/pkgs/r/" + arch + "/repodata.json"
   repodata = session.get(url)
   if repodata.status_code != 200:
       print('\n{} returned code {}'.format(url, page.status_code))
   else:
	   rdata = json.loads(repodata.text)
   return rdata;

def get_anaconda_pkglist(rdata, arch = 'linux-64', start_with = 'r', ver = '36'):
    """ Read from r channel architecture specific package list with specific version """
    pkgs = set(v['name'][2:] for v in rdata['packages'].values() if v['name'].startswith('r-') and v['build'].startswith('' + start_with + Rver))
    print('{} Anaconda R {} packages in {} found.'.format(len(pkgs), arch, start_with))
    return pkgs

CRAN_BASE = 'https://cran.r-project.org'
#CRAN_BASE = 'https://cran.microsoft.com/snapshot/2018-01-01'
RecipeMaintainer = 'katietz'
Rver = '36'
Rfullver = '3.6.1'
Rarch = 'linux-64'

batch_count_max=50

pandas2ri.activate()
readRDS = robjects.r['readRDS']
session = requests.Session()

get_ipython().run_line_magic('matplotlib', 'qt')


repodata = get_r_channel_rdata(Rarch)
anaconda_pkgs = get_anaconda_pkglist(repodata, arch = Rarch, ver = Rver)
anaconda_351_pkgs = anaconda_pkgs
anaconda_mro_pkgs = get_anaconda_pkglist(repodata, arch = Rarch, start_with = 'mro', ver = Rver)

repodata = get_r_channel_rdata("noarch")
anaconda_pkgs2 = get_anaconda_pkglist(repodata, arch = 'noarch', ver = Rver)
anaconda_mro_pkgs2 = get_anaconda_pkglist(repodata, arch = 'noarch', start_with = 'mro', ver = Rver)

anaconda_pkgs.update(anaconda_pkgs2)
anaconda_351_pkgs.update(anaconda_pkgs2)
anaconda_mro_pkgs.update(anaconda_mro_pkgs2)
print('{} Total Anaconda R packages found.'.format(len(anaconda_pkgs)))
# In[3]:


from binstar_client.utils.config import DEFAULT_URL, load_token
built_pkgs = set()

# In[61]:


from email.parser import BytesParser
from email import message_from_string

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

to_compile = []
stages = []
while len(candidates):
    can_do = candidates.superdepends.apply(lambda x: completed.issuperset(a.lower() for a in x))
    can_do = candidates.index[can_do]
    if len(can_do) == 0:
        break
    completed.update(a.lower() for a in can_do)
    to_compile.extend(can_do)
    stages.append(can_do)
    candidates = candidates.drop(can_do, 'index')
    if len(candidates) != 0:
        print("Remaining candidates {}".format(len(candidates)))


print("\nDump of to_compile: {}\n".format(len(to_compile)))
# print(*to_compile, sep=", ")
#print("\nDump of to_compile 10: {}\n".format(len(to_compile)))
# print(*to_compile, sep=", ")

# print("\nDump of items:\n")
# print(*items, sep=", ")

with open(f'./build-skeleton.sh', 'w') as bsd:
    bsd.write('#!/bin/bash\n\n')
    bsd.write('# do imports via conda skeleton cran\n\n')
    with open(f'./build-stage.sh', 'w') as bd:
        bd.write('#!/bin/bash\n\n')
        for i, stage in enumerate(stages):
                bd.write('# stage {}\n'.format(i))
                scount = len(stage)
                j = 0
                elno = 0
                while elno < scount:
                    bsd.write('conda skeleton cran --cran-url={} --output-suffix=-feedstock/recipe --recursive \\\n'.format(CRAN_BASE))
                    bsd.write('  --add-maintainer={} --update-policy=merge-keep-build-num --r-interp=r-base --use-noarch-generic \\\n'.format(RecipeMaintainer))
                    bd.write('c3i batch --R={} --max-builds=6 ./batch_stage-{}-{}.txt\n'.format(Rfullver, i, j))
                    with open(f'./batch_stage-{i}-{j}.txt', 'w') as fd:
                        el = 0
                        while elno < scount and el < batch_count_max:
                            p = stage[elno]
                            fd.write('r-' + p + '-feedstock')
                            fd.write('\n')
                            bsd.write(' ' + p)
                            elno += 1
                            el += 1
                    j += 1
                    bsd.write('\n')
                    bd.write('\n')
                bd.write('\n')
                print("State {} is splitted into {} parts".format(i, j))

print("Done.")
