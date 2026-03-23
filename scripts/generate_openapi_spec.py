#!/usr/bin/env python3
"""Generate OpenAPI specification JSON file.

This script generates an OpenAPI 3.0 specification file from the Flask-Smorest
API definition. The generated file can be used as a reference for frontend
development or AI agent code generation.

Usage:
    python scripts/generate_openapi_spec.py [output_file]

The default output file is 'openapi.json' in the current directory.
"""

import json
import sys
from pathlib import Path


def create_app_and_get_spec(config=None):
    """Create Flask app and capture the Flask-Smorest API object."""
    from gramps_webapi.app import create_app
    import flask_smorest

    # Temporarily store the api object using a wrapper
    original_init = flask_smorest.Api.__init__
    api_ref = []

    def wrapper(self, *args, **kwargs):
        result = original_init(self, *args, **kwargs)
        api_ref.append(self)
        return result

    flask_smorest.Api.__init__ = wrapper
    app = create_app(config or {"TESTING": True})
    flask_smorest.Api.__init__ = original_init

    return app, api_ref[0] if api_ref else None


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"

    print(f"Generating OpenAPI specification...")

    app, api = create_app_and_get_spec()

    with app.app_context():
        spec = api.spec.to_dict()

        output_path = Path(output_file)
        with output_path.open("w") as f:
            json.dump(spec, f, indent=2)

        print(f"✓ Generated {output_path} ({output_path.stat().st_size} bytes)")
        print(f"  Title: {spec['info']['title']}")
        print(f"  Version: {spec['info']['version']}")
        print(f"  Paths: {len(spec.get('paths', {}))}")
        print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
