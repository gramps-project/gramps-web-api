import os
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, url_for, request, current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
import uuid

from . import user_db, User

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
    redirect_uri = url_for("oidc.authorize", provider=provider, _external=True)
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
        return {"error": "No email provided by OIDC provider"}, 400
    
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
                role=0,  
                pwhash='',  
            )
            user_db.session.add(user)
            user_db.session.commit()
        except IntegrityError:
            return {"error": "User creation failed"}, 400
    
    # Create JWT tokens
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    
    # Return tokens and user info
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "name": user.name,
            "email": user.email,
            "full_name": user.fullname,
            "role": user.role
        }
    }
