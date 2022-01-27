#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
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
    "Flask-Caching",
    "Flask-Compress",
    "Flask-Cors",
    "Flask-JWT-Extended>=4.2.1",
    "Flask-Limiter",
    "webargs",
    "SQLAlchemy",
    "pdf2image",
    "Pillow",
    "bleach",
    "whoosh",
    "jsonschema",
    "ffmpeg-python",
    "boto3",
    "alembic",
]

setup(
    author="Gramps Development Team",
    url="https://github.com/gramps-project/web-api",
    python_requires=">=3.5",
    description="A RESTful web API for the Gramps genealogical database.",
    license="AGPL v3 or greater",
    install_requires=REQUIREMENTS,
    long_description=README,
    long_description_content_type="text/markdown",
    include_package_data=True,
    name="gramps-webapi",
    packages=find_packages(include=["gramps_webapi", "gramps_webapi.*"]),
    version=__version__,
    zip_safe=False,
)
