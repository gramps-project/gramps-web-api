import os
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, url_for, session, request
from dotenv import load_dotenv

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
    redirect_uri = url_for("oidc.authorize", provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri)

@oidc_bp.route("/callback/<provider>")
def authorize(provider):
    client = oauth.create_client(provider)
    token = client.authorize_access_token()
    user = client.parse_id_token(token) if provider == "google" else client.get('user').json()
    session['user'] = user
    return {"status": "logged_in", "provider": provider, "user": user}
