import os
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from decouple import config

oauth = OAuth()


BASE_URL = config('BASE_URL', 'http://localhost:8000')
GOOGLE_REDIRECT_URI = config("GOOGLE_REDIRECT_URI")

if config('GOOGLE_CLIENT_ID') and config('GOOGLE_CLIENT_SECRET'):
    oauth.register(
    name='google',
    client_id=config('GOOGLE_CLIENT_ID'),
    client_secret=config('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly"
    },
    redirect_uri=GOOGLE_REDIRECT_URI
    )

if os.getenv('GITHUB_CLIENT_ID') and os.getenv('GITHUB_CLIENT_SECRET'):
    oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    authorize_url='https://github.com/login/oauth/authorize',
    access_token_url='https://github.com/login/oauth/access_token',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
    )