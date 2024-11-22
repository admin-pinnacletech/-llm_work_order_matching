import logging
from typing import Optional, Dict, List
import aiohttp
from django.db import transaction
from asgiref.sync import sync_to_async
from work_order_review.models import Tenant, Facility, FacilityScenario
from ..newton_api_utils import build_api_header

logger = logging.getLogger(__name__)

class ScenarioManager:
    def __init__(self, user_id: str = None):
        self.BASE_URL = 'https://newton.pinnacletech.com'
        if user_id:
            self.auth_header = build_api_header(user_id)
        else:
            # Default test user if none provided
            self.auth_header = build_api_header('4c453411-6d39-4704-81d0-ac09014d83eb')
        self.logger = logging.getLogger(__name__)
    
    @sync_to_async
    def _save_tenant(self, tenant_data: Dict) -> Tenant:
        tenant, _ = Tenant.objects.update_or_create(
            id=tenant_data['id'],
            defaults={
                'name': tenant_data['name'],
                'rawData': tenant_data
            }
        )
        return tenant

    @sync_to_async
    def _save_facility(self, facility_data: Dict, tenant: Tenant) -> Facility:
        facility, _ = Facility.objects.update_or_create(
            id=facility_data['id'],
            defaults={
                'name': facility_data['name'],
                'tenantId': tenant,
                'rawData': facility_data
            }
        )
        return facility

    @sync_to_async
    def _save_scenario(self, scenario_data: Dict, tenant: Tenant, facility: Facility) -> FacilityScenario:
        """Save scenario with duplicate handling"""
        try:
            # Try to get existing scenario
            scenario = FacilityScenario.objects.get(
                tenantId=tenant,
                facilityId=facility,
                name=scenario_data['name']
            )
            # Update existing scenario
            scenario.rawData = scenario_data
            scenario.save()
            self.logger.info(f"Updated existing scenario: {scenario.name}")
            return scenario
        except FacilityScenario.DoesNotExist:
            # Create new scenario if it doesn't exist
            scenario = FacilityScenario.objects.create(
                id=scenario_data['id'],
                name=scenario_data['name'],
                tenantId=tenant,
                facilityId=facility,
                rawData=scenario_data
            )
            self.logger.info(f"Created new scenario: {scenario.name}")
            return scenario

    @sync_to_async
    def cleanup_duplicates(self):
        """Remove duplicate scenarios keeping the most recently updated one"""
        from django.db.models import Count
        
        self.logger.info("Starting duplicate cleanup")
        
        # Find groups of duplicates
        duplicates = (
            FacilityScenario.objects.values('tenantId', 'facilityId', 'name')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        
        cleanup_count = 0
        for dup in duplicates:
            # Get all scenarios in this duplicate group
            scenarios = FacilityScenario.objects.filter(
                tenantId=dup['tenantId'],
                facilityId=dup['facilityId'],
                name=dup['name']
            ).order_by('-updated')
            
            # Keep the most recent, delete others
            keep = scenarios.first()
            to_delete = scenarios.exclude(id=keep.id)
            count = to_delete.count()
            to_delete.delete()
            cleanup_count += count
            
            self.logger.info(
                f"Cleaned up {count} duplicates of scenario '{dup['name']}' "
                f"for tenant {dup['tenantId']}, facility {dup['facilityId']}"
            )
        
        self.logger.info(f"Cleanup complete. Removed {cleanup_count} duplicate scenarios.")
        return cleanup_count

    async def get_tenants(self) -> List[Dict]:
        """Get list of available tenants"""
        self.logger.info("Fetching available tenants")
        
        try:
            # First try to get from database
            tenants = await sync_to_async(list)(Tenant.objects.all())
            if tenants:
                self.logger.info(f"Found {len(tenants)} tenants in database")
                return [{'id': t.id, 'name': t.name} for t in tenants]
            
            # If no tenants in database, fetch from API
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/api/tenants"
                self.logger.info(f"Fetching tenants from API: {url}")
                async with session.get(url, headers=self.auth_header) as response:
                    if response.status == 200:
                        data = await response.json()
                        for tenant_data in data.get('data', []):
                            await self._save_tenant(tenant_data)
                        return data.get('data', [])
                    self.logger.error(f"API returned status {response.status}")
                    return []
        except Exception as e:
            self.logger.error(f"Error getting tenants: {str(e)}")
            return []

    async def get_facilities(self, tenant_id: str) -> List[Dict]:
        """Get list of facilities for a tenant"""
        self.logger.info(f"Fetching facilities for tenant: {tenant_id}")
        
        try:
            # First try to get from database
            facilities = await sync_to_async(list)(Facility.objects.filter(tenantId_id=tenant_id))
            if facilities:
                self.logger.info(f"Found {len(facilities)} facilities in database")
                return [{'id': f.id, 'name': f.name} for f in facilities]
            
            # If no facilities in database, fetch from API
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/{tenant_id}/api/facilities"
                async with session.get(url, headers=self.auth_header) as response:
                    if response.status == 200:
                        data = await response.json()
                        tenant = await Tenant.objects.aget(id=tenant_id)
                        for facility_data in data.get('data', []):
                            await self._save_facility(facility_data, tenant)
                        return data.get('data', [])
                    self.logger.error(f"API returned status {response.status}")
                    return []
        except Exception as e:
            self.logger.error(f"Error getting facilities: {str(e)}")
            return []

    async def get_scenarios(self, tenant_id: str, facility_id: str) -> List[Dict]:
        """Get list of scenarios for a facility"""
        self.logger.info(f"Fetching scenarios for facility: {facility_id}")
        
        try:
            # First try to get from database
            scenarios = await sync_to_async(list)(FacilityScenario.objects.filter(facilityId_id=facility_id))
            if scenarios:
                self.logger.info(f"Found {len(scenarios)} scenarios in database")
                scenario_list = [{'id': s.id, 'name': s.name} for s in scenarios]
                # Always add Current scenario at the beginning
                scenario_list.insert(0, {'id': 'current', 'name': 'Current'})
                return scenario_list
            
            # If no scenarios in database, fetch from API
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/{tenant_id}/api/scenarios"
                self.logger.info(f"Fetching scenarios from API: {url}")
                async with session.get(url, headers=self.auth_header) as response:
                    if response.status == 200:
                        data = await response.json()
                        tenant = await Tenant.objects.aget(id=tenant_id)
                        facility = await Facility.objects.aget(id=facility_id)
                        
                        # Filter scenarios for this facility
                        scenarios = [s for s in data.get('data', []) if s['facilityId'] == facility_id]
                        self.logger.info(f"Found {len(scenarios)} scenarios for facility")
                        
                        # Save scenarios to database
                        for scenario_data in scenarios:
                            await self._save_scenario(scenario_data, tenant, facility)
                        
                        # Format response
                        scenario_list = [{'id': s['id'], 'name': s['name']} for s in scenarios]
                        
                        # Always add Current scenario at the beginning
                        scenario_list.insert(0, {'id': 'current', 'name': 'Current'})
                        
                        return scenario_list
                    
                    self.logger.error(f"API returned status {response.status}")
                    # Even if API fails, return at least the Current scenario
                    return [{'id': 'current', 'name': 'Current'}]
                    
        except Exception as e:
            self.logger.error(f"Error getting scenarios: {str(e)}")
            # Even if there's an error, return at least the Current scenario
            return [{'id': 'current', 'name': 'Current'}]

    async def get_scenario_data(self, tenant_identifier: str, scenario_id: str) -> Optional[Dict]:
        """
        Get scenario data from scenario manager
        
        Args:
            tenant_identifier (str): The tenant identifier
            scenario_id (str): The scenario ID to look up
            
        Returns:
            Optional[Dict]: Dictionary containing scenario data or None if not found/error
        """
        self.logger.info(f"Fetching scenario data for tenant: {tenant_identifier}, scenario: {scenario_id}")
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.BASE_URL}/{tenant_identifier}/api/scenario/{scenario_id}/scenariomanager"
            self.logger.info(f"Making request to: {url}")
            
            try:
                async with session.get(url, headers=self.auth_header) as response:
                    self.logger.info(f"Response status: {response.status}")
                    
                    if response.status == 200:
                        json_response = await response.json()
                        self.logger.info(f"Response data: {json_response}")
                        
                        if json_response.get('data'):
                            # Save tenant to database
                            tenant = await self._save_tenant({'id': tenant_identifier, 'name': tenant_identifier})
                            
                            # Get facility info from first scenario
                            first_scenario = json_response['data'][0]
                            facility = await self._save_facility({
                                'id': first_scenario['facilityId'],
                                'name': first_scenario['facilityName']
                            }, tenant)
                            
                            # Save all scenarios to database
                            for scenario_data in json_response['data']:
                                await self._save_scenario(scenario_data, tenant, facility)
                            
                            # Try to find our specific scenario
                            matching_scenario = next(
                                (s for s in json_response['data'] if str(s['id']) == str(scenario_id)),
                                None
                            )
                            
                            if matching_scenario:
                                self.logger.info(f"Found matching scenario: {matching_scenario['name']}")
                                return {
                                    'tenantId': tenant_identifier,
                                    'facilityId': matching_scenario['facilityId'],
                                    'facilityName': matching_scenario['facilityName'],
                                    'name': matching_scenario['name']
                                }
                            else:
                                # If scenario not found, create it as 'Current'
                                self.logger.info(f"Scenario {scenario_id} not found, creating as 'Current'")
                                current_scenario = {
                                    'id': scenario_id,
                                    'name': 'Current',
                                    'facilityId': first_scenario['facilityId'],
                                    'facilityName': first_scenario['facilityName']
                                }
                                # Save the Current scenario to database
                                await self._save_scenario(current_scenario, tenant, facility)
                                
                                return {
                                    'tenantId': tenant_identifier,
                                    'facilityId': first_scenario['facilityId'],
                                    'facilityName': first_scenario['facilityName'],
                                    'name': 'Current'
                                }
                        
                        self.logger.error("No data found in response")
                        return None
                    
                    self.logger.error(f"Error response: {await response.text()}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Exception during API request: {str(e)}", exc_info=True)
                return None