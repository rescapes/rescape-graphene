# rescape_graphene
Graphene helpers for rescape projects

## Installation

Create a virtual environment using
```bash
mkdir ~/.virtualenvs
python3 -m venv ~/.virtualenvs/rescape-graphene
Activate it
source ~/.virtualenvs/rescape-graphene/bin/activate
```

#### Install requirements
If you don't have pur installed:
pip install pur

This updates requirements.txt to their latest version

Install requirements with latest versions
```bash
pur -r requirements.txt && $VIRTUAL_ENV/bin/pip3 install --no-cache-dir  --upgrade -r requirements.txt
```

Add the following to the bottom $VIRTUAL_ENV/bin/activate to setup the PYTHONPATH.
Replace the path with your code directory

```bash
export RESCAPE_GRAPHENE_BASE_DIR=/Users/andy/code/rescape-graphene
export RESCAPE_GRAPHENE_PROJECT_DIR=$RESCAPE_GRAPHENE_BASE_DIR/urbinsight
export PYTHONPATH=.:$RESCAPE_GRAPHENE_BASE_DIR:$RESCAPE_GRAPHENE_PROJECT_DIR
```

## Build

Update the version in setup.py
Run to generate build:
Update the version with bumpversion, which can't seem to look it up itself but udpates setup.py

```bash
git commit . -m "Version update" && git push
bumpversion --current-version {look in setup.py} patch setup.py
python3 setup.py clean sdist bdist_wheel
```

To distribute to testpypi site:
Upload package:

```bash
twine upload dist/*
```

All at once
``` bash
git commit . -m "Version update" && git push && bumpversion --current-version {look in setup.py} patch setup.py && python3 setup.py clean sdist bdist_wheel && twine upload dist/*
# without commit
bumpversion --current-version {look in setup.py} patch setup.py && python3 setup.py clean sdist bdist_wheel && twine upload dist/*
```

For setup of testpypi see ~/.pypirc or create one according to the testpypi docs:
e.g.:
[distutils]
index-servers=
    pypi
    testpypi

[testpypi]
repository: https://test.pypi.org/legacy/
username: your username for pypi.org

## Running tests
Create a postgres database rescape_graphene
# Login to psql:
CREATE DATABASE rescape_graphene;
CREATE USER test_user WITH PASSWORD 'test';
GRANT ALL PRIVILEGES ON DATABASE rescape_graphene to test_user;
# Give Superuser permission to create test databases
ALTER ROLE test_user SUPERUSER;

# Run the migrations
# Create a Django user test with pw testpass
 ./manage.py createsuperuser
 # or
 echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('test', 'test@nowhere.man', 'testpass')" | ./manage.py shell
