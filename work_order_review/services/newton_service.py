import logging
import aiohttp
import backoff
from typing import Dict, Optional
from ..database.models import Asset, Component, Assessment
import asyncio
import pprint

logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=2)

class NewtonService:
    def __init__(self, tenant_id: str, scenario_id: str, auth_header: Dict):
        self.BASE_URL = 'https://newton.pinnacletech.com'
        self.tenant_id = tenant_id
        self.scenario_id = scenario_id
        self.auth_header = auth_header
        self.session = None
        logger.debug(f"Initialized NewtonService with tenant_id={tenant_id}, scenario_id={scenario_id}")

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3
    )
    async def get_data(self, endpoint: str) -> Dict:
        """Make API request with retry logic"""
        logger.debug(f"Getting data from endpoint: {endpoint}")
        if not self.session:
            async with aiohttp.ClientSession() as session:
                return await self._make_request(session, endpoint)
        return await self._make_request(self.session, endpoint)

    async def _make_request(self, session: aiohttp.ClientSession, endpoint: str) -> Dict:
        url = self._build_url(endpoint)
        logger.info(f"Making request to: {url}")
        
        try:
            async with session.get(url, headers=self.auth_header) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"API error for {url}: {response.status} - {error_text}")
                    raise Exception(f"API error {response.status}: {error_text}")
                
                data = await response.json()
                logger.info(f"Successfully fetched data from {url}")
                return data
        except Exception as e:
            logger.error(f"Error making request to {url}: {str(e)}")
            raise

    def _build_url(self, endpoint: str) -> str:
        endpoint = endpoint.lstrip('/')
        base_url = f'{self.BASE_URL}/{self.tenant_id}/api/scenario/{self.scenario_id}'
        
        if endpoint.startswith('assessment/'):
            assessment_id = endpoint.split('/')[-1]
            url = f'{base_url}/assessment/{assessment_id}'
        else:
            url = f'{base_url}/{endpoint}'
            
        logger.debug(f"Built URL: {url}")
        return url 