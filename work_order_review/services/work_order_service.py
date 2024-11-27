import logging
import json
import uuid
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Callable
from sqlalchemy import text
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.database.models import WorkOrderStatus

logger = logging.getLogger(__name__)

class WorkOrderService:
    def __init__(self, session):
        self.session = session
        
    def _serialize_timestamps(self, obj):
        """Recursively serialize timestamps in an object to ISO format"""
        if isinstance(obj, dict):
            return {key: self._serialize_timestamps(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_timestamps(item) for item in obj]
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return obj
        
    def _prepare_row_data(self, row: pd.Series) -> dict:
        """Convert row to dict and handle special data types"""
        try:
            # Convert row to dict, handling NaN values
            row_dict = row.where(pd.notna(row), None).to_dict()
            
            # Serialize any timestamps in the data
            serialized_dict = self._serialize_timestamps(row_dict)
            
            logger.debug(f"Serialized row data: {serialized_dict}")
            return serialized_dict
            
        except Exception as e:
            logger.error(f"Error preparing row data: {str(e)}")
            raise
    
    async def create_table(self):
        """Create work orders table if it doesn't exist"""
        await self.session.execute(text("""
            CREATE TABLE IF NOT EXISTS work_orders (
                id UUID PRIMARY KEY,
                external_id VARCHAR NOT NULL,
                tenant_id VARCHAR NOT NULL,
                facility_scenario_id VARCHAR NOT NULL,
                raw_data JSONB NOT NULL,
                CONSTRAINT unique_work_order 
                    UNIQUE (tenant_id, facility_scenario_id, external_id)
            )
        """))
        await self.session.commit()
        
    async def upload_work_orders(
        self,
        df: pd.DataFrame,
        id_column: str,
        tenant_id: str,
        scenario_id: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, int]:
        """Upload work orders from dataframe"""
        try:
            await self.create_table()
            
            total_rows = len(df)
            successful = 0
            failed = 0
            
            for index, row in df.iterrows():
                try:
                    # Prepare row data with timestamp handling
                    row_dict = self._prepare_row_data(row)
                    
                    # Insert work order
                    stmt = text("""
                        INSERT INTO work_orders (id, external_id, tenant_id, facility_scenario_id, raw_data, status)
                        VALUES (:id, :external_id, :tenant_id, :scenario_id, :raw_data, :status)
                        ON CONFLICT (tenant_id, facility_scenario_id, external_id) DO UPDATE 
                        SET raw_data = EXCLUDED.raw_data
                    """)
                    
                    await self.session.execute(stmt, {
                        'id': str(uuid.uuid4()),
                        'external_id': str(row[id_column]),
                        'tenant_id': tenant_id,
                        'scenario_id': scenario_id,
                        'raw_data': json.dumps(row_dict),
                        'status': WorkOrderStatus.UNPROCESSED.value
                    })
                    
                    successful += 1
                except Exception as e:
                    logger.error(f"Error processing row {index}: {str(e)}")
                    failed += 1
                
                if progress_callback:
                    progress_callback(index + 1, total_rows, successful, failed)
                
                # Commit every 100 rows
                if (index + 1) % 100 == 0:
                    await self.session.commit()
                    logger.info(f"Committed batch. Progress: {index + 1}/{total_rows}")
            
            # Final commit
            await self.session.commit()
            
            logger.info(f"Upload complete. Successful: {successful}, Failed: {failed}")
            return {
                'successful': successful,
                'failed': failed,
                'total': total_rows
            }
            
        except Exception as e:
            logger.error(f"Error uploading work orders: {str(e)}", exc_info=True)
            await self.session.rollback()
            return None 

    async def insert_work_order(self, work_order_data: Dict):
        """Insert or update a work order"""
        query = text("""
            INSERT INTO work_orders (id, external_id, tenant_id, facility_scenario_id, raw_data)
            VALUES (:id, :external_id, :tenant_id, :facility_scenario_id, :raw_data)
            ON CONFLICT(tenant_id, facility_scenario_id, external_id) DO
            UPDATE SET raw_data = :raw_data
            WHERE tenant_id = :tenant_id 
            AND facility_scenario_id = :facility_scenario_id 
            AND external_id = :external_id
        """)
        
        await self.session.execute(
            query,
            {
                "id": str(uuid.uuid4()),
                "external_id": work_order_data["external_id"],
                "tenant_id": work_order_data["tenant_id"],
                "facility_scenario_id": work_order_data["facility_scenario_id"],
                "raw_data": json.dumps(work_order_data["raw_data"])
            }
        ) 