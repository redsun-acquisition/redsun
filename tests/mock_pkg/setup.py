from setuptools import setup, find_packages

setup(
    name="mock_pkg",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        'plugins': [
            'mock-pkg = manifest.yaml',
        ],
    },
    package_data={
        'mock_pkg': ['manifest.yaml'],
    },
)
