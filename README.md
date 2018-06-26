# rescape_graphene
Graphene helpers for rescape projects

To build:
Update the version in setup.py
Run to generate build:
python3 setup.py clean sdist bdist_wheel && twine upload
To distribute to testpypi site:
Upload package: twine upload --repository testpypi dist/*

For setup of testpypi see ~/.pypirc or create one according to the testpypi docs:
e.g.:
[distutils]
index-servers=
    pypi
    testpypi

[testpypi]
repository: https://test.pypi.org/legacy/
username: your username for pypi.org
