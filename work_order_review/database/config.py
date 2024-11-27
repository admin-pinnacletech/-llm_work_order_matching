from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .base import Base
import os
import logging

# Configure SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Get the directory where the application is running
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define database path
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'work_order_review.db')

# Ensure data directory exists
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# Create database URL
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600
)
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Create tables
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) 