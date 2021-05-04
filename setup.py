#!/usr/bin/env python3

from setuptools import setup

setup(name="simple-cdd",
      version="0.6.5",
      description="create custom debian-installer CDs",
      long_description="""simple-cdd is a limited though relatively easy tool to create a customized debian-installer CD.

it includes simple mechanisms to create "profiles" that define common system
configurations, which can be selected during system installation. simple-cdd
also makes it easy to build CDs with language and country settings
pre-configured.

this can be used to create a crude "Custom Debian Distribution" using packages
from Debian, with pre-configuration of packages that use debconf.  custom
configuration scripts can be specified to handle packages that don't support
debconf pre-configuration.

testing CD images with qemu is also made simple with a provided script.
""",
      author="Vagrant Cascadian",
      author_email="vagrant@debian.org",
      url="http://anonscm.debian.org/gitweb/?p=collab-maint/simple-cdd.git;a=summary",
      requires=["debian"],
      license="GPL-2",
      platforms="any",
      packages=["simple_cdd", "simple_cdd/tools"],
      # scripts=["build-simple-cdd"],
)
