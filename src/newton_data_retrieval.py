from django.db import transaction
from asgiref.sync import sync_to_async
import aiohttp
import asyncio
from tqdm import tqdm
from django.utils.timezone import make_aware
from qc_review.models import Asset, Assessment
import logging
import datetime
from django.utils import timezone
from aiohttp import ClientTimeout
from asyncio import TimeoutError
import backoff  # You'll need to pip install backoff
import uuid

logger = logging.getLogger(__name__)

class NewtonDataRetriever:
    def __init__(self, newton_path):
        self.BASE_URL = 'https://newton.pinnacletech.com'
        self.newton_path = newton_path
        self.tenant_identifier = newton_path['tenantIdentifier']
        self.scenario_id = newton_path['facilityScenarioId']
        self.auth_header = newton_path['authHeader']
        self.assets_created = 0
        self.assets_updated = 0
        self.assessments_created = 0
        self.assessments_updated = 0
        self.timeout = ClientTimeout(total=30)  # 30 second timeout

    @sync_to_async
    def _create_or_update_asset(self, asset_data):
        asset, created = Asset.objects.update_or_create(
            asset_id=asset_data['assetId'],
            defaults={
                'client_id': asset_data['assetClientId'],
                'name': asset_data['assetName']
            }
        )
        return asset, created

    @backoff.on_exception(
        backoff.expo,
        (TimeoutError, aiohttp.ClientError),
        max_tries=3,
        max_time=300
    )
    async def get_assessment_detail(self, session, assessment_id):
        """Get detailed data for a single assessment with retries"""
        url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/assessment/{assessment_id}'
        async with session.get(url, headers=self.auth_header, timeout=self.timeout) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API returned status {response.status}: {error_text}")
            return await response.json()

    @sync_to_async
    def _create_or_update_assessment(self, assessment_data, asset):
        now = timezone.now()
        
        # Validate UUID
        try:
            assessment_id = uuid.UUID(str(assessment_data['id']))
        except (ValueError, AttributeError, TypeError):
            logger.error(f"Invalid UUID found in assessment data: {assessment_data.get('id')}")
            return False

        try:
            created_str = assessment_data.get('created')
            modified_str = assessment_data.get('lastModified')
            
            created_date = (make_aware(datetime.datetime.fromisoformat(created_str.replace('Z', '+00:00'))) 
                          if created_str else now)
            modified_date = (make_aware(datetime.datetime.fromisoformat(modified_str.replace('Z', '+00:00'))) 
                           if modified_str else now)
        except (ValueError, AttributeError):
            created_date = now
            modified_date = now

        pid_number = (assessment_data.get('assetOrComponentData', {}) or {}).get('pidNumber', '')

        try:
            assessment, created = Assessment.objects.update_or_create(
                id=assessment_id,  # Use validated UUID
                defaults={
                    'asset': asset,
                    'tenantIdentifier': self.tenant_identifier,
                    'facilityScenarioId': self.scenario_id,
                    'assetSubTypeName': assessment_data.get('assetSubTypeName', ''),
                    'status': assessment_data.get('status', 0),
                    'pidNumber': pid_number,
                    'created': created_date,
                    'lastModified': modified_date,
                    'rawData': assessment_data
                }
            )
            return created
        except Exception as e:
            logger.error(f"Error creating/updating assessment {assessment_id}: {str(e)}")
            return False

    async def store_assessment_data(self, raw_assessments):
        for assessment_data in tqdm(raw_assessments, desc="Storing assessments"):
            # Create/update asset
            asset, asset_created = await self._create_or_update_asset(assessment_data)
            if asset_created:
                self.assets_created += 1
            else:
                self.assets_updated += 1

            # Create/update assessment
            assessment_created = await self._create_or_update_assessment(assessment_data, asset)
            if assessment_created:
                self.assessments_created += 1
            else:
                self.assessments_updated += 1

    async def get_assessment_list(self):
        """Get the list of assessment IDs"""
        url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/assessment'
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.auth_header) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API returned status {response.status}: {error_text}")
                
                data = await response.json()
                return data.get('data', [])

    async def retrieve_and_store_data(self):
        try:
            assessment_list = await self.get_assessment_list()
            logger.info(f"Retrieved {len(assessment_list)} assessments to process")

            async with aiohttp.ClientSession() as session:
                # Create progress bar
                pbar = tqdm(total=len(assessment_list), desc="Processing assessments")
                
                # Process assessments concurrently
                async def process_assessment(assessment_summary):
                    try:
                        # Get detailed data
                        assessment_data = await self.get_assessment_detail(session, assessment_summary['id'])
                        
                        # Create/update asset
                        asset, asset_created = await self._create_or_update_asset(assessment_data)
                        if asset_created:
                            self.assets_created += 1
                        else:
                            self.assets_updated += 1

                        # Create/update assessment
                        assessment_created = await self._create_or_update_assessment(assessment_data, asset)
                        if assessment_created:
                            self.assessments_created += 1
                        else:
                            self.assessments_updated += 1

                    except Exception as e:
                        logger.error(f"Error processing assessment {assessment_summary['id']}: {str(e)}")
                    finally:
                        pbar.update(1)

                # Create tasks for all assessments
                tasks = [process_assessment(summary) for summary in assessment_list]
                
                # Run all tasks concurrently
                await asyncio.gather(*tasks)
                
                # Close progress bar
                pbar.close()

            return {
                'assets_created': self.assets_created,
                'assets_updated': self.assets_updated,
                'assessments_created': self.assessments_created,
                'assessments_updated': self.assessments_updated,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Error retrieving and storing data: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
