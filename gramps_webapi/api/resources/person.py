"""Person API resource."""

from flask_restful import Resource


class Person(Resource):
    """Person resource."""

    def get(self, gramps_id: str):  # pylint: disable=no-self-use
        """Get."""
        return {"gramps_id": gramps_id}
