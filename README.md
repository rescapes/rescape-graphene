# rescape_graphene
Graphene helpers for rescape projects

To build:
Update the version in setup.py
Run to generate build:
Update the version with bumpversion, which can't seem to look it up itself but udpates setup.py
git commit . -m "Version update" && git push
bumpversion --current-version {look in setup.py} patch setup.py
python3 setup.py clean sdist bdist_wheel
To distribute to testpypi site:
Upload package:
twine upload dist/*

git commit . -m "Version update" && git push && bumpversion --current-version {look in setup.py} patch setup.py && python3 setup.py clean sdist bdist_wheel && twine upload dist/*

For setup of testpypi see ~/.pypirc or create one according to the testpypi docs:
e.g.:
[distutils]
index-servers=
    pypi
    testpypi

[testpypi]
repository: https://test.pypi.org/legacy/
username: your username for pypi.org
