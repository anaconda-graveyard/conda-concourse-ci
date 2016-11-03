#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

setup(
    name='conda_concourse_ci',
    version='0.1.0',
    description="Drive Concourse CI for conda recipe repos",
    author="Continuum Analytics",
    author_email='conda@continuum.io',
    url='https://github.com/conda/conda_concourse_ci',
    packages=[
        'conda_concourse_ci',
    ],
    package_dir={'conda_concourse_ci':
                 'conda_concourse_ci'},
    entry_points={
        'console_scripts': [
            'c3i=conda_concourse_ci.cli:build_cli'
        ]
    },
    include_package_data=True,
    license="BSD license",
    zip_safe=False,
    keywords='conda_concourse_ci',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)
