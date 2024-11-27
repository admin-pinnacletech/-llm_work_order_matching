from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

# Create metadata with naming convention
metadata = MetaData()

class Base(DeclarativeBase):
    metadata = metadata
    __abstract__ = True  # Prevents this base from being created as a table 