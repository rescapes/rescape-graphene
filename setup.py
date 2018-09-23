import os
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


class CleanCommand(setuptools.Command):
    """Custom clean command to tidy up the project root."""
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        os.system('rm -vrf ./build ./dist ./*.pyc ./*.tgz ./*.egg-info')


setuptools.setup(
    name="rescape-graphene",
    version="0.2.39",
    author="Andy Likuski",
    author_email="andy@likuski.org",
    description="Graphene helpers for rescape projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/calocan/rescape_graphene",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    cmdclass={
        'clean': CleanCommand,
    },
    install_requires=[
        'pyramda',
        'graphene',
        'graphene-django',
        'inflection',
        'deepmerge',
        'django-graphql-geojson',
        'djangorestframework',
        'djangorestframework-jwt',
        'psycopg2-binary',
        'django-graphql-jwt',
        'utils',
        'simplejson',
        'jsonfield',
        'rescape-python-helpers'
    ]
)
