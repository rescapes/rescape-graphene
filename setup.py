import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="rescape_graphene",
    version="0.0.7",
    author="Andy Likuski",
    author_email="andy@likuski.org",
    description="Graphene helpers for rescape projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/calocan/rescape_graphene",
    packages=setuptools.find_packages(),
    classifiers=(
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ),
)