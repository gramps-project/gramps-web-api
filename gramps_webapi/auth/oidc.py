import os
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, url_for, request, current_app, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
import uuid

from . import user_db, User
from .const import ROLE_OWNER
from ..api.util import get_tree_id
from ..api.auth import get_permissions

load_dotenv()

oauth = OAuth()

oidc_bp = Blueprint("oidc", __name__, url_prefix="/auth")

def configure_oauth(app):
    oauth.init_app(app)

    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        access_token_url='https://oauth2.googleapis.com/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        client_kwargs={'scope': 'openid email profile'},
    )

    oauth.register(
        name='github',
        client_id=os.getenv("GITHUB_CLIENT_ID"),
        client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'read:user user:email'},
    )

    oauth.register(
        name='microsoft',
        client_id=os.getenv("MICROSOFT_CLIENT_ID"),
        client_secret=os.getenv("MICROSOFT_CLIENT_SECRET"),
        access_token_url='https://login.microsoftonline.com/common/oauth2/v2.0/token',
        authorize_url='https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        api_base_url='https://graph.microsoft.com/v1.0/',
        client_kwargs={'scope': 'openid email profile'},
    )

@oidc_bp.route("/login/<provider>")
def login(provider):
    """Start the OAuth/OIDC login flow."""
    # Get the redirect URL from the request or use a default
    redirect_uri = request.args.get('redirect_uri', url_for("oidc.authorize", provider=provider, _external=True))
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@oidc_bp.route("/callback/<provider>")
def authorize(provider):
    """Handle the OAuth/OIDC callback and create/link user account."""
    client = oauth.create_client(provider)
    token = client.authorize_access_token()
    
    # Get user info from provider
    if provider == "google":
        user_info = client.parse_id_token(token)
    else:
        user_info = client.get('user').json()
    
    # Get email from OIDC user info
    email = user_info.get('email')
    if not email:
        return jsonify({"error": "No email provided by OIDC provider"}), 400
    
    # Check if user exists
    query = user_db.session.query(User)
    user = query.filter_by(email=email).scalar()
    
    if not user:
        # Create new user with default role
        try:
            user = User(
                id=uuid.uuid4(),
                name=email.split('@')[0],       
                email=email,
                fullname=user_info.get('name', ''),
                role=ROLE_OWNER,  # Give owner role to new users
                pwhash='',  
            )
            user_db.session.add(user)
            user_db.session.commit()
        except IntegrityError:
            return jsonify({"error": "User creation failed"}), 400
    
    # Get user's tree and permissions
    tree_id = get_tree_id(str(user.id))
    permissions = get_permissions(username=user.name, tree=tree_id)
    
    # Create JWT tokens with proper claims
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "permissions": list(permissions),
            "tree": tree_id
        }
    )
    refresh_token = create_refresh_token(identity=str(user.id))
    
    # Get the frontend redirect URL from the state parameter
    state = request.args.get('state', '')
    frontend_redirect = state if state else current_app.config.get('FRONTEND_URL', '/')
    
    # Return tokens in standard OAuth2 format
    response = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 900),  # 15 minutes default
        "user": {
            "name": user.name,
            "email": user.email,
            "full_name": user.fullname,
            "role": user.role,
            "tree": tree_id
        }
    }
    
    # If this is an API request (has Accept: application/json header)
    if request.headers.get('Accept') == 'application/json':
        return jsonify(response)
    
    # For browser requests, redirect to frontend with tokens
    return redirect(f"{frontend_redirect}?access_token={access_token}&refresh_token={refresh_token}")
