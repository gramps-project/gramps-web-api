import uuid
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, url_for, request, current_app, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy.exc import IntegrityError


from . import user_db, User, add_user
from .const import ROLE_USER
from ..api.util import get_tree_id, abort_with_message, tree_exists
from ..api.auth import get_permissions
from ..const import TREE_MULTI


oauth = OAuth()
oidc_bp = Blueprint("oidc", __name__, url_prefix="/auth")


def configure_oauth(app):
    if not app.config.get("OAUTH_ENABLED", False):
        return


    oauth.init_app(app)


    if app.config.get("OAUTH_GOOGLE_CLIENT_ID") and app.config.get("OAUTH_GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["OAUTH_GOOGLE_CLIENT_ID"],
            client_secret=app.config["OAUTH_GOOGLE_CLIENT_SECRET"],
            access_token_url="https://oauth2.googleapis.com/token",
            authorize_url="https://accounts.google.com/o/oauth2/auth",
            api_base_url="https://www.googleapis.com/oauth2/v1/",
            client_kwargs={"scope": "openid email profile"},
        )


    if app.config.get("OAUTH_GITHUB_CLIENT_ID") and app.config.get("OAUTH_GITHUB_CLIENT_SECRET"):
        oauth.register(
            name="github",
            client_id=app.config["OAUTH_GITHUB_CLIENT_ID"],
            client_secret=app.config["OAUTH_GITHUB_CLIENT_SECRET"],
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )


    if app.config.get("OAUTH_MICROSOFT_CLIENT_ID") and app.config.get("OAUTH_MICROSOFT_CLIENT_SECRET"):
        oauth.register(
            name="microsoft",
            client_id=app.config["OAUTH_MICROSOFT_CLIENT_ID"],
            client_secret=app.config["OAUTH_MICROSOFT_CLIENT_SECRET"],
            access_token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            api_base_url="https://graph.microsoft.com/v1.0/",
            client_kwargs={"scope": "openid email profile"},
        )


@oidc_bp.route("/login/<provider>")
def login(provider):
    if not current_app.config.get("OAUTH_ENABLED", False):
        abort_with_message(403, "OAuth is not enabled")


    redirect_uri = request.args.get("redirect_uri", url_for("oidc.authorize", provider=provider, _external=True))
    return oauth.create_client(provider).authorize_redirect(redirect_uri)


@oidc_bp.route("/callback/<provider>")
def authorize(provider):
    if not current_app.config.get("OAUTH_ENABLED", False):
        abort_with_message(403, "OAuth is not enabled")

    client = oauth.create_client(provider)
    token = client.authorize_access_token()

    if provider == "google":
        user_info = client.parse_id_token(token)
    else:
        user_info = client.get("user").json()

    email = user_info.get("email")
    if not email:
        abort_with_message(400, "No email provided")

    user = user_db.session.query(User).filter_by(email=email).first()
    if not user:
        # Enforce OIDC registration enable/disable
        if not current_app.config.get("ALLOW_OIDC_REGISTRATION", True):
            abort_with_message(403, "User registration is disabled")

        # Determine the tree to use
        if current_app.config["TREE"] == TREE_MULTI:
            # In multi-tree, OIDC must know which tree to assign!
            abort_with_message(422, "tree is required for OIDC registration in multi-tree mode")
        tree_id = current_app.config["TREE"]
        if not tree_exists(tree_id):
            abort_with_message(422, "Tree does not exist")

        try:
            username = email.split("@", 1)[0]
            dummy_password = uuid.uuid4().hex  # Satisfy non-empty password check
            add_user(
                name=username,
                password=dummy_password,
                email=email,
                fullname=user_info.get("name", ""),
                role=ROLE_USER,
                tree=tree_id
            )
            user = user_db.session.query(User).filter_by(email=email).first()
            if not user:
                abort_with_message(500, "Failed to create user")
        except ValueError as exc:
            # Consistent error codes: 409 for conflict, 400 otherwise
            msg = str(exc)
            code = 409 if "exists" in msg.lower() else 400
            abort_with_message(code, msg)

    # Now continue as usual
    tree_id = get_tree_id(str(user.id))
    permissions = get_permissions(username=user.name, tree=tree_id)

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "permissions": list(permissions),
            "tree": tree_id
        }
    )
    refresh_token = create_refresh_token(identity=str(user.id))

    frontend_redirect = request.args.get("state") or current_app.config.get("FRONTEND_URL", "/")

    response = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 900),
        "user": {
            "name": user.name,
            "email": user.email,
            "full_name": user.fullname,
            "role": user.role,
            "tree": tree_id
        }
    }

    if request.headers.get("Accept") == "application/json":
        return jsonify(response)

    return redirect(f"{frontend_redirect}?access_token={access_token}&refresh_token={refresh_token}")
