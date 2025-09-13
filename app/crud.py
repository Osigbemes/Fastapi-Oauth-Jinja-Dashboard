from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Metric


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
    # Adds some demo metrics if missing
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