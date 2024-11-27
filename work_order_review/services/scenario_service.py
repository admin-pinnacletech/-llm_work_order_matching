import logging
from typing import Dict, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.models import Tenant, Facility, FacilityScenario
from .newton_service import NewtonService
import pprint
from sqlalchemy import text
import json
logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=2)

class ScenarioService:
    def __init__(self, session: AsyncSession, auth_header: Dict):
        self.session = session
        self.auth_header = auth_header
        
    async def import_scenario(self, tenant_id: str, scenario_id: str) -> bool:
        """Import a scenario and its data"""
        try:
            newton_service = NewtonService(tenant_id, scenario_id, self.auth_header)
            scenario_data = await newton_service.get_data('scenariomanager')
            
            logger.info(f"Received scenario data:\n{pp.pformat(scenario_data)}")
            if not scenario_data:
                logger.error("Failed to get scenario data")
                return False
            
            # Track if we found the requested scenario
            found_requested_scenario = False
            
            # First pass: check if requested scenario is in the list
            for scenario in scenario_data['data']:
                if str(scenario['id']) == scenario_id:
                    found_requested_scenario = True
                    break
            
            # If not found in list, try to fetch it directly
            if not found_requested_scenario:
                logger.info(f"Scenario {scenario_id} not found in list, trying direct fetch")
                specific_scenario = await newton_service.get_data(f'scenariomanager/{scenario_id}')
                
                if not specific_scenario:
                    logger.error(f"Scenario {scenario_id} not found in system")
                    raise ValueError(f"Scenario {scenario_id} not found")
                    
                # Add the specific scenario to our data for saving
                scenario_data['data'].append(specific_scenario)
            
            # Now save all scenarios including the specific one if it was fetched
            await self._save_scenario_data(scenario_data, tenant_id, scenario_id)
            return True
            
        except ValueError as ve:
            # Re-raise ValueError for specific scenario not found
            raise
        except Exception as e:
            logger.error(f"Failed to import scenario: {str(e)}")
            return False

    async def _save_scenario_data(self, data: Dict, tenant_id: str, scenario_id: str):
        """Save scenario data to database using SQLite's REPLACE syntax"""
        try:
            # Replace tenant
            stmt = text("""
                INSERT OR REPLACE INTO tenants (id, name, raw_data)
                VALUES (:id, :name, :raw_data)
            """)
            await self.session.execute(stmt, {
                'id': tenant_id,
                'name': tenant_id,
                'raw_data': json.dumps(data)  # Serialize to JSON
            })
            
            # Save all scenarios from the API response
            for scenario in data['data']:
                # Replace facility
                stmt = text("""
                    INSERT OR REPLACE INTO facilities (id, name, tenant_id, raw_data)
                    VALUES (:id, :name, :tenant_id, :raw_data)
                """)
                await self.session.execute(stmt, {
                    'id': scenario['facilityId'],
                    'name': scenario['facilityName'],
                    'tenant_id': tenant_id,
                    'raw_data': json.dumps(scenario)  # Serialize to JSON
                })
                
                # Replace scenario
                stmt = text("""
                    INSERT OR REPLACE INTO facility_scenarios (id, name, tenant_id, facility_id, raw_data)
                    VALUES (:id, :name, :tenant_id, :facility_id, :raw_data)
                """)
                await self.session.execute(stmt, {
                    'id': str(scenario['id']),
                    'name': scenario['name'],
                    'tenant_id': tenant_id,
                    'facility_id': scenario['facilityId'],
                    'raw_data': json.dumps(scenario)  # Serialize to JSON
                })
            
            await self.session.commit()
            logger.info(f"Successfully saved/updated all scenario data for tenant {tenant_id}")
            logger.debug(f"Processed scenarios:\n{pp.pformat([s['id'] for s in data['data']])}")
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error saving scenario data: {str(e)}")
            raise

    async def get_tenants(self) -> List[Dict]:
        """Get list of all tenants"""
        try:
            stmt = text("SELECT DISTINCT id, name FROM tenants")
            result = await self.session.execute(stmt)
            return [{"id": row[0], "name": row[1]} for row in result]
        except Exception as e:
            logger.error(f"Error fetching tenants: {str(e)}")
            return []

    async def get_facilities(self, tenant_id: str) -> List[Dict]:
        """Get facilities for a tenant"""
        try:
            stmt = text("""
                SELECT DISTINCT id, name 
                FROM facilities 
                WHERE tenant_id = :tenant_id
            """)
            result = await self.session.execute(stmt, {"tenant_id": tenant_id})
            return [{"id": row[0], "name": row[1]} for row in result]
        except Exception as e:
            logger.error(f"Error fetching facilities: {str(e)}")
            return []

    async def get_scenarios(self, tenant_id: str, facility_id: str) -> List[Dict]:
        """Get scenarios for a facility"""
        try:
            stmt = text("""
                SELECT DISTINCT id, name 
                FROM facility_scenarios 
                WHERE tenant_id = :tenant_id 
                AND facility_id = :facility_id
            """)
            result = await self.session.execute(stmt, {
                "tenant_id": tenant_id,
                "facility_id": facility_id
            })
            return [{"id": row[0], "name": row[1]} for row in result]
        except Exception as e:
            logger.error(f"Error fetching scenarios: {str(e)}")
            return []

    async def get_scenario_info(self, tenant_id: str, scenario_id: str) -> Optional[Dict]:
        """Get display info for a scenario"""
        try:
            stmt = text("""
                SELECT 
                    t.name as tenant_name,
                    f.name as facility_name,
                    fs.name as scenario_name
                FROM facility_scenarios fs
                JOIN tenants t ON t.id = fs.tenant_id
                JOIN facilities f ON f.id = fs.facility_id
                WHERE fs.id = :scenario_id
                AND fs.tenant_id = :tenant_id
            """)
            result = await self.session.execute(stmt, {
                "tenant_id": tenant_id,
                "scenario_id": scenario_id
            })
            row = result.first()
            if row:
                return {
                    "tenant_name": row.tenant_name,
                    "facility_name": row.facility_name,
                    "scenario_name": row.scenario_name
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching scenario info: {str(e)}")
            return None