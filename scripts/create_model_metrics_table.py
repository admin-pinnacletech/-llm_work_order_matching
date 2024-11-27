import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from work_order_review.database.models import Base, ModelMetrics
from work_order_review.database.config import DATABASE_URL

async def create_model_metrics_table():
    # Create async engine
    engine = create_async_engine(DATABASE_URL)
    
    try:
        # Create tables using async context
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: ModelMetrics.__table__.create(sync_conn, checkfirst=True))
        print("Successfully created model_metrics table")
    except Exception as e:
        print(f"Error creating table: {str(e)}")
    finally:
        await engine.dispose()

async def recreate_model_metrics_table():
    # Create async engine
    engine = create_async_engine(DATABASE_URL)
    
    try:
        async with engine.begin() as conn:
            # Drop existing table
            await conn.run_sync(lambda sync_conn: ModelMetrics.__table__.drop(sync_conn, checkfirst=True))
            print("Dropped existing model_metrics table")
            
            # Create new table
            await conn.run_sync(lambda sync_conn: ModelMetrics.__table__.create(sync_conn, checkfirst=True))
            print("Successfully recreated model_metrics table")
    except Exception as e:
        print(f"Error recreating table: {str(e)}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    # Choose which function to run
    asyncio.run(recreate_model_metrics_table())  # This will drop and recreate
    # asyncio.run(create_model_metrics_table())  # This will only create if it doesn't exist 