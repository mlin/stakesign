#!/usr/bin/env python3
from os import path
from setuptools import setup, find_packages
from version import get_version

HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, "README.md")) as f:
    README = f.read()

setup(
    name="stakesign",
    version=get_version(),
    url="https://github.com/mlin/stakesign",
    description="Sign files via blockchain + put your money where your mouth is",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Mike Lin",
    author_email="dna@mlin.net",
    license="MIT",
    packages=find_packages(),
    entry_points={"console_scripts": ["stakesign = stakesign:main"]},
    python_requires=">=3.6",
    install_requires=[
        "importlib-metadata~=1.0",
        "python-dateutil~=2.0",
        "web3~=5.0",
        "pygit2~=1.0",
        "docker~=4.0",
    ],
)
