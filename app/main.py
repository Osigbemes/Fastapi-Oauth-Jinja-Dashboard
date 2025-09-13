import os
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from dotenv import load_dotenv
from .auth import oauth
from .database import engine, Base, get_db
from . import crud
from sqlalchemy.ext.asyncio import AsyncSession
from .schemas import UserOut
import asyncio


load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY', 'changeme')


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


# templates
templates = Jinja2Templates(directory='app/templates')

@app.on_event('startup')
async def startup_event():
    # create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get('/')
async def homepage(request: Request):
    user = request.session.get('user')
    return templates.TemplateResponse('base.html', {'request': request, 'user': user})


@app.get('/login/{provider}')
async def login(request: Request, provider: str):
    if provider not in oauth:
        raise HTTPException(status_code=404, detail='Provider not configured')
    redirect_uri = str(request.url_for('auth_callback', provider=provider))
    return await oauth[provider].authorize_redirect(request, redirect_uri)


@app.get('/auth/{provider}/callback')
async def auth_callback(request: Request, provider: str, db: AsyncSession = Depends(get_db)):
    if provider not in oauth:
        raise HTTPException(status_code=404, detail='Provider not configured')
    token = await oauth[provider].authorize_access_token(request)


    # Provider-specific user info extraction
    if provider == 'google':
        # For google OpenID connect
        userinfo = await oauth.google.parse_id_token(request, token)
        provider_id = userinfo.get('sub')
        email = userinfo.get('email')
        name = userinfo.get('name')
    elif provider == 'github':
        # For github, call the user endpoint
        resp = await oauth.github.get('user', token=token)
        profile = resp.json()
        provider_id = str(profile.get('id'))
        name = profile.get('name') or profile.get('login')
        # email may be null in profile, try /user/emails if needed
        email = profile.get('email')
        if not email:
            # try emails endpoint
            resp2 = await oauth.github.get('user/emails', token=token)
            emails = resp2.json()
            primary = next((e['email'] for e in emails if e.get('primary') and e.get('verified')), None)
            email = primary
    else:
        # Generic flow: try userinfo endpoint
        userinfo = token.get('userinfo') or {}
        provider_id = userinfo.get('id') or userinfo.get('sub')
        email = userinfo.get('email')
        name = userinfo.get('name')


    # persist user
    user = await crud.get_user_by_provider(db, provider, provider_id)
    if not user:
        user = await crud.create_user(db, provider, provider_id, email=email, name=name)
    # seed demo metrics
    await crud.seed_metrics(db, user.id)


    # set session
    request.session['user'] = {'id': user.id, 'name': user.name, 'email': user.email, 'provider': user.provider}
    return RedirectResponse(url='/dashboard')


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    session_user = request.session.get('user')
    if not session_user:
        return None
    # fetch fresh from DB
    user = await crud.get_user_by_provider(db, session_user['provider'], str(session_user['id']))
    # Note: provider_id stored as string; above provider id is id in user table, so fallback to id lookup
    if not user:
        from sqlalchemy import select
        res = await db.execute(select('users').where('id'==session_user['id']))
        # If not found, return None
        return session_user


@app.get('/dashboard')
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.session.get('user')
    if not user:
        return RedirectResponse(url='/')
    # load metrics
    metrics = await crud.get_metrics_for_user(db, int(user['id']))
    # convert to simple dict list
    metrics_list = [{'key': m.key, 'value': m.value} for m in metrics]
    return templates.TemplateResponse('dashboard.html', {'request': request, 'user': user, 'metrics': metrics_list})


@app.get('/logout')
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')