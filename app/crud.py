from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Metric

import httpx
from typing import Dict, Any

# Base helper
async def _get_google_resource(url: str, access_token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {} 


# ---- Google User Info ----
async def get_google_userinfo(access_token: str) -> Dict[str, Any]:
    url = "https://www.googleapis.com/oauth2/v2/userinfo"
    return await _get_google_resource(url, access_token)

import httpx
from datetime import datetime, timezone

GOOGLE_API_BASE = "https://www.googleapis.com"

async def get_drive_stats(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        # File count + recent file
        files_resp = await client.get(
            f"{GOOGLE_API_BASE}/drive/v3/files",
            headers=headers,
            params={"pageSize": 10, "fields": "files(name, modifiedTime)", "orderBy": "modifiedTime desc"}
        )
        files = files_resp.json().get("files", [])

        # Storage quota
        about_resp = await client.get(
            f"{GOOGLE_API_BASE}/drive/v3/about",
            headers=headers,
            params={"fields": "storageQuota"}
        )
        quota = about_resp.json().get("storageQuota", {})

    return {
        "file_count": len(files),
        "last_file": files[0]["name"] if files else None,
        "storage_used": int(quota.get("usage", 0)) // (1024*1024),  # MB
        "storage_limit": int(quota.get("limit", 0)) // (1024*1024) if quota.get("limit") else None
    }


async def get_calendar_stats(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient() as client:
        events_resp = await client.get(
            f"{GOOGLE_API_BASE}/calendar/v3/calendars/primary/events",
            headers=headers,
            params={
                "timeMin": now,             
                "singleEvents": True,
                "orderBy": "startTime",    
                "maxResults": 5         
            }
        )
        events = events_resp.json().get("items", [])

    return {
        "event_count": len(events),
        "next_event": events[0]["summary"] if events else None,
        "next_event_time": events[0]["start"].get("dateTime") if events else None
    }


async def get_gmail_stats(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        # All unread
        unread_resp = await client.get(
            f"{GOOGLE_API_BASE}/gmail/v1/users/me/messages",
            headers=headers,
            params={"q": "is:unread"}
        )
        unread = unread_resp.json().get("messages", [])

        # Important unread
        imp_resp = await client.get(
            f"{GOOGLE_API_BASE}/gmail/v1/users/me/messages",
            headers=headers,
            params={"q": "is:unread is:important"}
        )
        important = imp_resp.json().get("messages", [])

        # Latest subject
        recent_subject = None
        if unread:
            msg_id = unread[0]["id"]
            msg_resp = await client.get(
                f"{GOOGLE_API_BASE}/gmail/v1/users/me/messages/{msg_id}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["Subject"]}
            )
            headers_list = msg_resp.json().get("payload", {}).get("headers", [])
            subject_header = next((h for h in headers_list if h["name"] == "Subject"), None)
            recent_subject = subject_header["value"] if subject_header else None

    return {
        "unread_count": len(unread),
        "important_unread": len(important),
        "recent_subject": recent_subject
    }

    
async def get_user_by_provider(session: AsyncSession, provider: str, provider_id: str):
    q = select(User).where(User.provider == provider, User.provider_id == provider_id)
    res = await session.execute(q)
    return res.scalars().first()


async def get_user_by_email(session: AsyncSession, email: str):
    q = select(User).where(User.email == email)
    res = await session.execute(q)
    return res.scalars().first()


async def create_user(session: AsyncSession, provider: str, provider_id: str, email: str = None, name: str = None):
    user = User(provider=provider, provider_id=provider_id, email=email, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_metrics_for_user(session: AsyncSession, user_id: int):
    q = select(Metric).where(Metric.user_id == user_id)
    res = await session.execute(q)
    return res.scalars().all()


async def seed_metrics(session: AsyncSession, user_id: int):
    # just dummy data for demo, might look into this later
    existing = await get_metrics_for_user(session, user_id)
    if existing:
        return
    demo = [
    Metric(user_id=user_id, key='active_sessions', value='3'),
    Metric(user_id=user_id, key='monthly_signups', value='27'),
    Metric(user_id=user_id, key='errors', value='1'),
    ]
    session.add_all(demo)
    await session.commit()