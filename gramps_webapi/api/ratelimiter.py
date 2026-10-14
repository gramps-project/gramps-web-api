"""Rate limiting decorator."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import get_jwt, get_jwt_identity

# limit by IP address
limiter = Limiter(key_func=get_remote_address)

# limit by user UUID
limiter_per_user = Limiter(key_func=get_jwt_identity)


def get_jwt_tree() -> str:
    """Return the tree ID from the verified JWT."""
    return get_jwt().get("tree") or ""


# limit by tree ID, for operations that affect the whole tree
limiter_per_tree = Limiter(key_func=get_jwt_tree)
