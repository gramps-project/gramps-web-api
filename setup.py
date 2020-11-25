#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

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
    "bleach",
]

EXTRA_REQUIREMENTS = ["pycairo", "PyGObject"]

setup(
    author="Gramps Development Team",
    author_email="...",
    url="https://github.com/gramps-project/web-api",
    python_requires=">=3.5",
    description="A RESTful web API for the Gramps genealogical database.",
    license="GPL v2 or greater",
    install_requires=REQUIREMENTS,
    extra_requires=EXTRA_REQUIREMENTS,
    long_description=README,
    long_description_content_type="text/markdown",
    include_package_data=True,
    name="gramps_webapi",
    packages=find_packages(include=["gramps_webapi", "gramps_webapi.*"]),
    version=__version__,
    zip_safe=False,
)
