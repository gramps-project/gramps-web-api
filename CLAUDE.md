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
