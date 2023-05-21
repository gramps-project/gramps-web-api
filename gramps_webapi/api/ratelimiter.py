"""Rate limiting decorator."""


from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import get_jwt_identity

# limit by IP address
limiter = Limiter(key_func=get_remote_address)

# limit by user UUID
limiter_per_user = Limiter(key_func=get_jwt_identity)
