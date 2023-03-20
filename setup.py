from setuptools import setup, find_packages
from pathlib import Path

with Path(__file__).parent.joinpath('requirements.txt').open() as f:
	requirements = [line.strip() for line in f.readlines()]

setup(
    name='MDNPC',
    python_requires='==3.7',
    version='1.0',
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,
)
