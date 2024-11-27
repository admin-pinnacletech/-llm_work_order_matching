from setuptools import setup, find_packages

setup(
    name="llm_work_order_matching",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'streamlit',
        'sqlalchemy>=2.0.0',
        'alembic',
        'aiosqlite',
        'aiohttp',
        'asyncio',
        'backoff',
        'python-dotenv',
    ],
) 