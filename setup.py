import os
import sys
from setuptools import setup, find_packages

PACKAGE_NAME = 'featuretools_ta1'
MINIMUM_PYTHON_VERSION = 3, 6


def check_python_version():
    """Exit when the Python version is too low."""
    if sys.version_info < MINIMUM_PYTHON_VERSION:
        sys.exit("Python {}.{}+ is required.".format(*MINIMUM_PYTHON_VERSION))


def read_package_variable(key):
    """Read the value of a variable from the package without importing."""
    module_path = os.path.join(PACKAGE_NAME, '__init__.py')
    with open(module_path) as module:
        for line in module:
            parts = line.strip().split(' ')
            if parts and parts[0] == key:
                return parts[-1].strip("'")
    assert False, "'{0}' not found in '{1}'".format(key, module_path)


check_python_version()


setup(
    name=PACKAGE_NAME,
    version=read_package_variable('__version__'),
    description='Primitives using Featuretools, an open source feature engineering platform',
    author=read_package_variable('__author__'),
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    install_requires=[
        'featuretools==v0.1.20.d3m.2018.4.18',
        'd3m==v2018.4.18',
        'typing'
    ],
    url='https://gitlab.datadrivendiscovery.org/MIT-FeatureLabs/ta1-primitives',
    dependency_links=[
        'git+https://github.com/Featuretools/featuretools.git@v0.1.20.d3m.2018.4.18#egg=featuretools-0.1.20',
    ],
    entry_points={
        'd3m.primitives': [
            'featuretools_ta1.DFS = featuretools_ta1.dfs:DFS',
            'featuretools_ta1.Imputer = featuretools_ta1.imputer:Imputer',
            'featuretools_ta1.RFClassifierFeatureSelector = featuretools_ta1.rf_clf_selector:RFClassifierFeatureSelector',
            'featuretools_ta1.RFRegressorFeatureSelector = featuretools_ta1.rf_reg_selector:RFRegressorFeatureSelector',
        ],
    },
)
