"""Gramps XML export endpoint."""

from io import BytesIO
from tempfile import NamedTemporaryFile

from flask import send_file
from gramps.cli.user import User
from gramps.plugins.export.exportxml import XmlWriter
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import jwt_required_ifauth


@jwt_required_ifauth
@use_args({"compress": fields.Boolean(missing=False)}, location="query")
def export_xml(args):
    """Return the family tree as a Gramps XML file."""
    dbstate = get_dbstate()
    user = User()
    writer = XmlWriter(
        dbase=dbstate.db, user=user, strip_photos=0, compress=args["compress"]
    )
    # XmlWriter expects a filename as input, so we create a temp file.
    # However, we don't want the temp file to stick around, so after
    # writing it, we read it into memory and delete it; then we serve
    # the buffer from memory.
    f_xml = BytesIO()
    with NamedTemporaryFile("rb") as f:
        writer.write(f.name)
        f.seek(0)
        f_xml.write(f.read())
        f_xml.seek(0)
    if args["compress"]:
        attachment_filename = "tree.gramps.gz"
    else:
        attachment_filename = "tree.gramps"
    return send_file(
        f_xml,
        mimetype="application/xml",
        as_attachment=True,
        attachment_filename=attachment_filename,
    )
