import logging
from typing import Optional, Dict, List, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from work_order_review.services.newton_service import NewtonService
from work_order_review.database.models import Asset, Component, Assessment
import json
import pprint
import asyncio

logger = logging.getLogger(__name__)

class AssessmentService:
    def __init__(self, session: AsyncSession, auth_header: Dict[str, str]):
        self.session = session
        self.auth_header = auth_header
        self._db_lock = asyncio.Lock()  # Add lock for DB operations
        
    async def import_assessment_data(
        self, 
        tenant_id: str, 
        scenario_id: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, int]:
        """Import assessment data from Newton API and derive assets/components"""
        try:
            newton_service = NewtonService(tenant_id, scenario_id, self.auth_header)
            stats = {'assets': 0, 'components': 0, 'assessments': 0}
            processed_assets = set()
            processed_components = set()
            
            assessments_list = await newton_service.get_data('assessment')
            if not assessments_list:
                logger.error("Failed to get assessments list")
                return None
                
            total_assessments = len(assessments_list.get('data', []))
            logger.info(f"Found {total_assessments} assessments to process")
            
            if progress_callback:
                progress_callback(0, total_assessments, f"Processing 0/{total_assessments} assessments")

            # Process in batches with controlled concurrency
            batch_size = 100
            max_concurrent = 1  # Limit concurrent batches
            semaphore = asyncio.Semaphore(max_concurrent)
            assessment_summaries = assessments_list.get('data', [])
            tasks = []

            async def process_batch(batch_items, start_idx):
                async with semaphore:
                    batch_tasks = []
                    for idx, summary in enumerate(batch_items):
                        task = self._process_assessment(
                            summary, 
                            start_idx + idx,
                            newton_service,
                            tenant_id,
                            scenario_id,
                            stats,
                            processed_assets,
                            processed_components,
                            progress_callback,
                            total_assessments
                        )
                        batch_tasks.append(task)
                    
                    # Process batch concurrently
                    await asyncio.gather(*batch_tasks)
                    
                    # Commit after batch completes
                    async with self._db_lock:
                        await self.session.commit()

            # Create batch processing tasks
            for i in range(0, len(assessment_summaries), batch_size):
                batch = assessment_summaries[i:i + batch_size]
                task = process_batch(batch, i)
                tasks.append(task)

            # Run all batches
            await asyncio.gather(*tasks)
            
            logger.info(f"Import complete. Stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to import assessment data: {str(e)}")
            async with self._db_lock:
                await self.session.rollback()
            return None

    async def _process_assessment(
        self,
        assessment_summary: Dict,
        current_index: int,
        newton_service: NewtonService,
        tenant_id: str,
        scenario_id: str,
        stats: Dict,
        processed_assets: set,
        processed_components: set,
        progress_callback: Optional[Callable],
        total_assessments: int
    ) -> None:
        """Process a single assessment with DB locking."""
        try:
            assessment_id = assessment_summary['id']
            detailed_data = await newton_service.get_data(f'assessment/{assessment_id}')
            
            if not detailed_data:
                return None

            async with self._db_lock:
                # Extract asset data
                asset_data = detailed_data.get('assetOrComponentData', {})
                if asset_data and asset_data.get('assetId') and asset_data['assetId'] not in processed_assets:
                    await self._save_asset({
                        'id': asset_data['assetId'],
                        'clientId': asset_data['assetClientId'],
                        'name': asset_data['assetName'],
                        'isActive': True
                    }, tenant_id, scenario_id)
                    processed_assets.add(asset_data['assetId'])
                    stats['assets'] += 1
                
                # Handle component
                component_id = detailed_data.get('componentId')
                if component_id and component_id not in processed_components:
                    component_data = {
                        'id': component_id,
                        'assetId': detailed_data['assetId'],
                        'name': detailed_data.get('componentName', ''),
                        'clientId': detailed_data.get('componentClientId', ''),
                        'isActive': True
                    }
                    await self._save_component(component_data, tenant_id, scenario_id)
                    processed_components.add(component_id)
                    stats['components'] += 1
                
                # Save assessment
                await self._save_assessment(detailed_data, tenant_id, scenario_id)
                stats['assessments'] += 1

            if progress_callback:
                progress_callback(
                    current_index + 1,
                    total_assessments,
                    f"Processed {current_index + 1}/{total_assessments} assessments"
                )
                
        except Exception as e:
            logger.error(f"Error processing assessment {assessment_summary.get('id')}: {str(e)}")

    async def _save_asset(self, data: Dict, tenant_id: str, scenario_id: str):
        stmt = text("""
            INSERT OR REPLACE INTO assets (id, client_id, name, tenant_id, facility_scenario_id, is_active, raw_data)
            VALUES (:id, :client_id, :name, :tenant_id, :facility_scenario_id, :is_active, :raw_data)
        """)
        await self.session.execute(stmt, {
            'id': str(data['id']),
            'client_id': data.get('clientId'),
            'name': data.get('name'),
            'tenant_id': tenant_id,
            'facility_scenario_id': scenario_id,
            'is_active': data.get('isActive', True),
            'raw_data': json.dumps(data)
        })
        
    async def _save_component(self, data: Dict, tenant_id: str, scenario_id: str):
        stmt = text("""
            INSERT OR REPLACE INTO components (id, asset_id, client_id, name, tenant_id, facility_scenario_id, is_active, raw_data)
            VALUES (:id, :asset_id, :client_id, :name, :tenant_id, :facility_scenario_id, :is_active, :raw_data)
        """)
        await self.session.execute(stmt, {
            'id': str(data['id']),
            'asset_id': str(data.get('assetId') or data.get('asset', {}).get('id')),
            'client_id': data.get('clientId'),
            'name': data.get('name'),
            'tenant_id': tenant_id,
            'facility_scenario_id': scenario_id,
            'is_active': data.get('isActive', True),
            'raw_data': json.dumps(data)
        })
        
    async def _save_assessment(self, data: Dict, tenant_id: str, scenario_id: str):
        stmt = text("""
            INSERT OR REPLACE INTO assessments (id, component_id, tenant_id, facility_scenario_id, is_active, raw_data)
            VALUES (:id, :component_id, :tenant_id, :facility_scenario_id, :is_active, :raw_data)
        """)
        
        # Handle null component_id properly
        component_id = data.get('componentId') or data.get('component', {}).get('id')
        if component_id:
            component_id = str(component_id)
        else:
            component_id = None  # Use None instead of 'None' string
        
        await self.session.execute(stmt, {
            'id': str(data['id']),
            'component_id': component_id,
            'tenant_id': tenant_id,
            'facility_scenario_id': scenario_id,
            'is_active': data.get('isActive', True),
            'raw_data': json.dumps(data)
        })