import aiohttp
import asyncio
import logging
from typing import Dict, List
from datetime import datetime
from django.db import transaction
from asgiref.sync import sync_to_async
import backoff
from .models import Asset, Component, Assessment

logger = logging.getLogger(__name__)

class NewtonClient:
    def __init__(self, tenant_id: str, scenario_id: str, auth_header: Dict):
        self.BASE_URL = 'https://newton.pinnacletech.com'
        self.tenant_id = tenant_id
        self.scenario_id = scenario_id
        self.auth_header = auth_header
        
        # Stats for tracking
        self.stats = {
            'assets_created': 0,
            'assets_updated': 0,
            'components_created': 0,
            'components_updated': 0,
            'assessments_created': 0,
            'assessments_updated': 0
        }

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3
    )
    async def _get_data(self, session: aiohttp.ClientSession, endpoint: str) -> Dict:
        """Make API request with retry logic"""
        url = f'{self.BASE_URL}/{self.tenant_id}/api/scenario/{self.scenario_id}/{endpoint}'
        async with session.get(url, headers=self.auth_header) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API error {response.status}: {error_text}")
            return await response.json()

    @sync_to_async
    def _save_asset(self, data: Dict) -> Asset:
        """Save asset to database"""
        asset, created = Asset.objects.update_or_create(
            id=data['assetId'],
            defaults={
                'rawData': data
            }
        )
        if created:
            self.stats['assets_created'] += 1
        else:
            self.stats['assets_updated'] += 1
        return asset

    @sync_to_async
    def _save_component(self, data: Dict) -> Component:
        """Save component to database"""
        component, created = Component.objects.update_or_create(
            id=data['componentId'],
            defaults={
                'rawData': data
            }
        )
        if created:
            self.stats['components_created'] += 1
        else:
            self.stats['components_updated'] += 1
        return component

    @sync_to_async
    def _save_assessment(self, data: Dict):
        """Save assessment to database"""
        assessment, created = Assessment.objects.update_or_create(
            id=data['id'],
            defaults={
                'rawData': data
            }
        )
        if created:
            self.stats['assessments_created'] += 1
        else:
            self.stats['assessments_updated'] += 1

    async def import_facility_data(self, progress_callback=None):
        """Import all data for a facility"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get assessment list
                assessments = await self._get_data(session, 'assessment')
                total = len(assessments['data'])
                
                if progress_callback:
                    progress_callback(0, total, "Starting import...")

                for index, assessment in enumerate(assessments['data']):
                    try:
                        # Get detailed assessment data
                        details = await self._get_data(session, f"assessment/{assessment['id']}")
                        
                        # Save data (using Django's transaction management)
                        async with transaction.atomic():
                            asset = await self._save_asset(details)
                            component = await self._save_component(details)
                            await self._save_assessment(details)
                        
                        if progress_callback:
                            progress_callback(
                                index + 1, 
                                total, 
                                f"Processing assessment {index + 1}/{total}"
                            )

                    except Exception as e:
                        logger.error(f"Error processing assessment {assessment['id']}: {str(e)}")

                return self.stats

        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            raise 