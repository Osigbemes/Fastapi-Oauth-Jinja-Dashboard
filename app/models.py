from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=True)
    provider = Column(String, nullable=False) # e.g., 'google' or 'github'
    provider_id = Column(String, nullable=False, index=True) # provider unique id


class Metric(Base):
    __tablename__ = 'metrics'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    user = relationship('User', backref='metrics')