"""The setup script."""

from setuptools import find_packages, setup

with open("README.md") as readme_file:
    README = readme_file.read()

with open("gramps_webapi/_version.py") as version_file:
    exec(version_file.read())


REQUIREMENTS = [
    "Click>=7.0",
    "Flask",
    "Flask-Compress",
    "Flask-Cors",
    "Flask-JWT-Extended",
    "Flask-Limiter",
    "webargs",
    "SQLAlchemy",
    "pdf2image",
    "Pillow",
]


setup(
    author="Gramps Development Team",
    author_email="...",
    url="https://github.com/gramps-project/web-api",
    python_requires=">=3.5",
    description="A RESTful web API for the Gramps genealogical database.",
    license="GPL v2 or greater",
    install_requires=REQUIREMENTS,
    long_description=README,
    long_description_content_type="text/markdown",
    include_package_data=True,
    name="gramps_webapi",
    packages=find_packages(include=["gramps_webapi", "gramps_webapi.*"]),
    version=__version__,
    zip_safe=False,
)
