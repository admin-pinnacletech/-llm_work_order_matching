import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional
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
        # Remove any leading slashes and construct URL properly
        endpoint = endpoint.lstrip('/')
        
        # Construct base URL
        url = f'{self.BASE_URL}/{self.tenant_id}/api/scenario/{self.scenario_id}'
        
        # Add endpoint
        if endpoint.startswith('assessment/'):
            # Handle detailed assessment endpoint
            assessment_id = endpoint.split('/')[-1]
            url = f'{url}/assessment/{assessment_id}'
        else:
            # Handle list endpoints
            url = f'{url}/{endpoint}'
        
        logger.info(f"Fetching from: {url}")
        
        async with session.get(url, headers=self.auth_header) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"API error for {url}: {response.status} - {error_text}")
                raise Exception(f"API error {response.status}: {error_text}")
            data = await response.json()
            logger.info(f"Successfully fetched data from {url}")
            return data

    @sync_to_async
    def _save_asset(self, data: Dict) -> Asset:
        """Save asset to database with minimal data"""
        asset, created = Asset.objects.update_or_create(
            id=data['assetId'],
            defaults={
                'client_id': data.get('assetClientId', ''),
                'name': data.get('assetName', ''),
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        return asset

    @sync_to_async
    def _save_component(self, data: Dict, asset: Asset) -> Component:
        """Save component to database with minimal data"""
        component, created = Component.objects.update_or_create(
            id=data['componentId'],
            defaults={
                'asset': asset,
                'name': data.get('componentName', ''),
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        return component

    @sync_to_async
    def _save_assessment(self, data: Dict, component: Component):
        """Save assessment to database (synchronous version)"""
        assessment, created = Assessment.objects.update_or_create(
            id=data['id'],
            defaults={
                'component': component,
                'raw_data': data,
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        if created:
            self.stats['assessments_created'] += 1
        else:
            self.stats['assessments_updated'] += 1

    @sync_to_async
    def _save_data_atomic(self, details, stats, processed_assets, processed_components):
        """Save all related data in a single transaction"""
        with transaction.atomic():
            try:
                # Validate required fields
                asset_id = details.get('assetId')
                component_id = details.get('componentId')
                assessment_id = details.get('id')

                if not all([asset_id, component_id, assessment_id]):
                    logger.error(f"Missing required IDs: asset={asset_id}, component={component_id}, assessment={assessment_id}")
                    logger.error(f"Full details: {details}")
                    raise ValueError("Missing required IDs")

                # Save or get asset
                asset, asset_created = Asset.objects.update_or_create(
                    id=asset_id,
                    defaults={
                        'raw_data': details,
                        'tenant_id': self.tenant_id,
                        'facility_scenario_id': self.scenario_id,
                        'is_active': True
                    }
                )
                
                if asset_created and asset_id not in processed_assets:
                    processed_assets.add(asset_id)
                    stats['assets'] += 1

                # Save or get component using select_for_update to prevent race conditions
                with transaction.atomic():
                    try:
                        component = Component.objects.select_for_update().get(id=component_id)
                        # Update existing component
                        for key, value in {
                            'asset': asset,
                            'raw_data': details,
                            'tenant_id': self.tenant_id,
                            'facility_scenario_id': self.scenario_id,
                            'is_active': True
                        }.items():
                            setattr(component, key, value)
                        component.save()
                    except Component.DoesNotExist:
                        # Create new component
                        component = Component.objects.create(
                            id=component_id,
                            asset=asset,
                            raw_data=details,
                            tenant_id=self.tenant_id,
                            facility_scenario_id=self.scenario_id,
                            is_active=True
                        )
                        if component_id not in processed_components:
                            processed_components.add(component_id)
                            stats['components'] += 1

                # Save assessment
                assessment, assessment_created = Assessment.objects.update_or_create(
                    id=assessment_id,
                    defaults={
                        'component': component,
                        'raw_data': details,
                        'tenant_id': self.tenant_id,
                        'facility_scenario_id': self.scenario_id,
                        'is_active': True
                    }
                )
                
                if assessment_created:
                    stats['assessments'] += 1

            except Exception as e:
                logger.error(f"Error in atomic save: {str(e)}")
                logger.error(f"Details: asset_id={details.get('assetId')}, component_id={details.get('componentId')}, assessment_id={details.get('id')}")
                logger.error(f"Raw data: {details}")
                raise

    def _save_asset_sync(self, data: Dict) -> Asset:
        """Synchronous version of save_asset"""
        asset, created = Asset.objects.update_or_create(
            id=data['assetId'],
            defaults={
                'raw_data': data,
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        return asset

    def _save_component_sync(self, data: Dict, asset: Asset) -> Component:
        """Synchronous version of save_component"""
        component, created = Component.objects.get_or_create(
            id=data['componentId'],
            defaults={
                'asset': asset,
                'raw_data': data,
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        
        # Update if needed
        if not created:
            Component.objects.filter(id=data['componentId']).update(
                asset=asset,
                raw_data=data,
                tenant_id=self.tenant_id,
                facility_scenario_id=self.scenario_id,
                is_active=True
            )
            component.refresh_from_db()
        
        return component

    def _save_assessment_sync(self, data: Dict, component: Component) -> Assessment:
        """Synchronous version of save_assessment"""
        assessment, created = Assessment.objects.update_or_create(
            id=data['id'],
            defaults={
                'component': component,
                'raw_data': data,
                'tenant_id': self.tenant_id,
                'facility_scenario_id': self.scenario_id,
                'is_active': True
            }
        )
        return assessment

    async def import_facility_data(self, progress_callback=None):
        """Import all data for a facility using only assessment endpoint"""
        try:
            stats = {'assets': 0, 'components': 0, 'assessments': 0}
            processed_assets = set()
            processed_components = set()
            
            async with aiohttp.ClientSession() as session:
                if progress_callback:
                    progress_callback(0, 1, "Fetching assessments...", 'assessment')
                
                assessments = await self._get_data(session, 'assessment')
                total_assessments = len(assessments.get('data', []))
                
                for index, assessment_data in enumerate(assessments.get('data', [])):
                    try:
                        # Get detailed assessment data
                        details = await self._get_data(session, f"assessment/{assessment_data['id']}")
                        
                        # Validate the data structure
                        if not isinstance(details, dict):
                            logger.error(f"Invalid details format for assessment {assessment_data['id']}: {details}")
                            continue

                        # Save all data in a single transaction
                        await self._save_data_atomic(details, stats, processed_assets, processed_components)
                        
                        if progress_callback:
                            progress_callback(
                                index + 1,
                                total_assessments,
                                f"Processing assessment {index + 1}/{total_assessments}",
                                'assessment'
                            )
                        
                    except Exception as e:
                        logger.error(f"Error processing assessment {assessment_data.get('id')}: {str(e)}")
                        continue
                
                return stats
                
        except Exception as e:
            logger.error(f"Import failed: {str(e)}")
            raise

    @sync_to_async
    def _get_asset(self, asset_id: str) -> Optional[Asset]:
        """Get asset from database"""
        try:
            return Asset.objects.get(id=asset_id)
        except Asset.DoesNotExist:
            logger.error(f"Asset {asset_id} not found")
            return None

    @sync_to_async
    def _get_component(self, component_id: str) -> Optional[Component]:
        """Get component from database"""
        try:
            return Component.objects.get(id=component_id)
        except Component.DoesNotExist:
            logger.error(f"Component {component_id} not found")
            return None