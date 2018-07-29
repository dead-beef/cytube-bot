#!/usr/bin/env python3

import os
from setuptools import setup, find_packages


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(BASE_DIR, 'README.rst')) as fp:
        README = fp.read()
except IOError:
    README = ''

setup(name='cytube-bot',
      version='0.1.1',
      description='AsyncIO CyTube bot',
      long_description=README,
      classifiers=[
          'Development Status :: 4 - Beta',
          'Environment :: Web Environment',
          'Framework :: AsyncIO',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Topic :: Software Development :: Libraries :: Python Modules'
      ],
      keywords='cytube bot asyncio',
      url='https://github.com/dead-beef/cytube-bot',
      author='dead-beef',
      license='MIT',
      packages=find_packages(include=('cytube_bot*',)),
      install_requires=['websockets', 'requests'],
      extras_require={
          'proxy': ['pysocks'],
          'dev': [
              'pysocks',
              'pytest',
              'pytest-mock',
              'pytest-asyncio<=0.5.0',
              'coverage',
              'sphinx',
              'sphinx_rtd_theme',
              'twine',
              'wheel'
          ]
      },
      include_package_data=True,
      zip_safe=False)
