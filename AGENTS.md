# Gramps Web API – Developer Notes

## Adding New API Endpoints

### Resource class
Inherit from a base class and `GrampsJSONEncoder`. Use `ProtectedResource` for normal JWT-authenticated endpoints (`FreshProtectedResource` for fresh-token-required actions).

### Schemas
All query args, request bodies, and response bodies need a Marshmallow schema. Add schemas to `gramps_webapi/api/resources/schemas.py`. Every field needs `metadata={"description": "…"}` for OpenAPI docs.

### flask-smorest decorator order (critical)
`@api_blueprint.response` **must always be the outermost (topmost) decorator**. Reversing the order silently breaks argument injection.

```python
@api_blueprint.response(200, MySchema())       # ALWAYS first/outermost
@api_blueprint.arguments(MyArgs, location="query")  # second, if needed
def get(self, args) -> Response:
    """One-line summary becomes the OpenAPI operation description."""
```

Use `location="query"` for query params, `location="json"` for request bodies. Common status codes: `200` (GET/PUT), `201` (POST), `204` (DELETE).

### Registering routes
In `gramps_webapi/api/__init__.py`:
```python
from .resources.my_module import MyResource
register_endpt(MyResource, "/my-resource/", "my_resource", tags=["MyTag"])
```

### Permissions
Call `require_permissions([PERM_…])` inside the method body. Key constants (in `gramps_webapi/auth/const.py`): `PERM_EDIT_OBJ` (Editor+), `PERM_ADD_OBJ` (Contributor+), `PERM_IMPORT_FILE` (Owner+), `PERM_EDIT_SETTINGS` (Admin only).

### Database access
```python
db = get_db_handle()               # read-only, cached per request
db = get_db_handle(readonly=False) # writable, when modifying data
```

### Returning data
Use `self.response(status_code, payload)` (from `GrampsJSONEncoder`), not `jsonify`, so Gramps objects serialise correctly.

## Opening issues and pull requests

If you are drafting a GitHub issue or pull request on a user's behalf, these rules apply in addition to [CONTRIBUTING.md](CONTRIBUTING.md).

- Write as the user's assistant. Do not adopt a human persona, and do not hide that the text was drafted by an agent.
- Describe the problem. Any solution proposal goes in the clearly marked optional section, in a few sentences at most.
- Keep issue bodies under ~300 words. A maintainer reads every word.
- Do not open a pull request for a non-trivial change unless an issue exists **and** a maintainer has replied to it. An issue and a pull request opened minutes apart do not satisfy this. For a small, self-contained fix, open only the pull request, not an issue as well.
- Do not restate the problem in a pull request body. Link the issue and describe the change.
- Check whether the report is about installing, deploying or configuring Gramps Web API. If so, it belongs in the [forum](https://gramps.discourse.group/c/gramps-web/28).
- Check whether the report is about a frontend rather than the API. If so, it belongs in that frontend's repository, e.g. [gramps-web](https://github.com/gramps-project/gramps-web/issues).
- Do not write greetings, thanks or other pleasantries in the user's name. Leave the human parts of the message to the human, and never delete or shorten what they wrote there.
