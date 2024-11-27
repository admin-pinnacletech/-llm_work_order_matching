import asyncio
from work_order_review.database.config import engine
from work_order_review.database.base import Base
from work_order_review.database.models import WorkOrder  # Import the model

async def init_db():
    """Drop all tables and recreate them"""
    async with engine.begin() as conn:
        # Drop all existing tables
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Database initialized successfully!")
    return

if __name__ == "__main__":
    asyncio.run(init_db()) 