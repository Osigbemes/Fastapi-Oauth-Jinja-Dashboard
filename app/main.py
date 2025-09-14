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
import logging

logger = logging.getLogger(__name__)

load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY', 'changeme')

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",      # helps with Google OAuth
    https_only=False      # set True in production
)

# templates
templates = Jinja2Templates(directory='app/templates')

@app.get("/test-session")
async def test_session(request: Request):
    request.session["foo"] = "bar"
    return {"session_value": request.session.get("foo")}


@app.on_event('startup')
async def startup_event():
    # create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get('/')
async def homepage(request: Request):
    user = request.session.get('user')
    return templates.TemplateResponse('base.html', {'request': request, 'user': user})


@app.get("/auth/{provider}")
async def auth(request: Request, provider: str):
    logger.info(f"Auth endpoint called for provider: {provider}")
    logger.info(f"Registered providers: {list(oauth._registry.keys())}")

    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=404, detail="Unsupported provider")
    
    redirect_uri = str(request.url_for("auth_callback", provider=provider))  # ✅ fix
    return await client.authorize_redirect(request, redirect_uri)

@app.get("/auth/{provider}/callback")
async def auth_callback(request: Request, provider: str, db: AsyncSession = Depends(get_db)):
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=404, detail="Provider not configured")

    # 🔑 only call this once
    token = await client.authorize_access_token(request)
    if "id_token" not in token:
        raise HTTPException(status_code=400, detail="id_token not found in token response")

    if provider == "google":
        resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo", token=token)
        userinfo = resp.json()

        provider_id = userinfo.get("sub")
        email = userinfo.get("email")
        name = userinfo.get("name")

    else:
        userinfo = token.get("userinfo") or {}
        provider_id = userinfo.get("id") or userinfo.get("sub")
        email = userinfo.get("email")
        name = userinfo.get("name")

    # persist user
    user = await crud.get_user_by_provider(db, provider, provider_id)
    if not user:
        user = await crud.create_user(db, provider, provider_id, email=email, name=name)

    await crud.seed_metrics(db, user.id)

    request.session["user"] = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "provider": user.provider,
        "provider_id": user.provider_id
    }
    request.session["token"] = token  

    return RedirectResponse(url="/dashboard")


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    session_user = request.session.get('user')
    if not session_user:
        return None
    
    # fetch fresh from DB
    user = await crud.get_user_by_provider(db, session_user['provider'], str(session_user['id']))
    
    if not user:
        from sqlalchemy import select
        res = await db.execute(select('users').where('id'==session_user['id']))
        
        return session_user

@app.get("/dashboard")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.session.get("user")
    token = request.session.get("token")

    if not user or not token:
        return RedirectResponse(url="/")

    google_data, drive_data, calendar_data, gmail_data = {}, {}, {}, {}

    if user["provider"] == "google":
        try:
            google_data = await crud.get_google_userinfo(token["access_token"])

            raw_drive = await crud.get_drive_stats(token["access_token"])
            drive_data = {
                "file_count": raw_drive.get("file_count", []),
                "last_file": raw_drive.get("last_file", [{}])
                if raw_drive.get("last_file") else "None",
                "storage_used": raw_drive.get("storage_used", 0),
                "storage_limit": raw_drive.get("storage_limit", 0),
            }

            raw_calendar = await crud.get_calendar_stats(token["access_token"])
         
            calendar_data = {
                "event_count": raw_calendar.get("event_count", []),
                "next_event": raw_calendar.get("next_event", []),
                "next_event_time": raw_calendar.get("next_event_time", []),
            }

            raw_gmail = await crud.get_gmail_stats(token["access_token"])
            gmail_data = {
                "unread_count": raw_gmail.get("unread_count", []),
                "important_unread": raw_gmail.get("important_unread", []),
                "recent_subject": raw_gmail.get("recent_subject", [])
            }

        except Exception as e:
            print("Google API error:", e)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "google_data": google_data,
            "drive_data": drive_data,
            "calendar_data": calendar_data,
            "gmail_data": gmail_data,
        },
    )


@app.get('/logout')
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url='/')