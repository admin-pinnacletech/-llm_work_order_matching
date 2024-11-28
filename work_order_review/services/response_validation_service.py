from typing import Dict, Tuple, Optional, Set
import logging
import json
from sqlalchemy import select
from work_order_review.database.models import Asset

logger = logging.getLogger(__name__)

class ValidationResult:
    def __init__(self, is_valid: bool, message: str = None, invalid_assets: list = None):
        self.is_valid = is_valid
        self.message = message
        self.invalid_assets = invalid_assets or []

    def to_dict(self):
        """Convert ValidationResult to a dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "message": self.message,
            "invalid_assets": self.invalid_assets
        }

class ResponseValidationService:
    def __init__(self, session, tenant_id: str, scenario_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.scenario_id = scenario_id
        self.asset_client_ids = None
        self.logger = logging.getLogger(__name__)
    
    async def _get_asset_client_ids(self) -> Set[str]:
        """Fetch and cache asset client IDs for the current tenant and scenario."""
        if self.asset_client_ids is None:
            try:
                self.logger.info(
                    f"Fetching asset client IDs for tenant {self.tenant_id} "
                    f"and scenario {self.scenario_id}"
                )
                # Query only active assets with non-null client_ids for current tenant/scenario
                stmt = select(Asset.client_id).where(
                    Asset.tenant_id == self.tenant_id,
                    Asset.facility_scenario_id == self.scenario_id,
                    Asset.client_id.isnot(None),
                    Asset.is_active == True
                ).distinct()
                
                result = await self.session.execute(stmt)
                result_list = result.scalars().all()
                
                # Clean and validate the IDs
                self.asset_client_ids = {
                    str(client_id).strip() 
                    for client_id in result_list 
                    if client_id and str(client_id).strip()
                }
                
                # Debug logging
                self.logger.info(
                    f"Found {len(self.asset_client_ids)} unique asset client IDs "
                    f"for tenant {self.tenant_id} and scenario {self.scenario_id}"
                )
                if self.asset_client_ids:
                    sample = list(self.asset_client_ids)[:5]
                    self.logger.info(f"Sample asset client IDs: {sample}")
                else:
                    self.logger.warning(
                        f"No asset client IDs found for tenant {self.tenant_id} "
                        f"and scenario {self.scenario_id}!"
                    )
                
            except Exception as e:
                self.logger.error(f"Error fetching asset client ids: {e}")
                raise
            
        return self.asset_client_ids
    
    async def validate_asset_client_ids(self, message_content: str) -> ValidationResult:
        """Validate that all asset client IDs in the message exist."""
        try:
            # Ensure asset client IDs are loaded
            await self._get_asset_client_ids()

            # Parse the message content
            if isinstance(message_content, str):
                try:
                    data = json.loads(message_content)
                except json.JSONDecodeError:
                    return ValidationResult(False, "Invalid JSON format in message")
            else:
                data = message_content

            # Extract asset client IDs from matches
            if not isinstance(data, dict) or 'matches' not in data:
                return ValidationResult(False, "Message missing required 'matches' field")

            matches = data['matches']
            if not isinstance(matches, list):
                return ValidationResult(False, "'matches' must be a list")

            match_asset_client_ids = [match.get('asset_client_id') for match in matches]
            self.logger.info(f"Found {len(match_asset_client_ids)} asset client IDs in matches. {match_asset_client_ids}")
            asset_client_ids = [
                match.get('asset_client_id') 
                for match in matches 
                if 'asset_client_id' in match
            ]

            asset_ids_valid = all(asset_id in self.asset_client_ids for asset_id in asset_client_ids)
            self.logger.info(f"Asset Client IDs seen as valid by response validation service: {asset_ids_valid}")
            
            if not asset_client_ids:
                return ValidationResult(False, "No asset client IDs found in matches")

            # Check against valid IDs
            invalid_assets = [
                asset_id 
                for asset_id in asset_client_ids 
                if asset_id not in self.asset_client_ids
            ]

            if invalid_assets:
                return ValidationResult(
                    False,
                    f"The following assets were not found: {', '.join(invalid_assets)}",
                    invalid_assets
                )

            return ValidationResult(True, "All asset client IDs are valid")

        except Exception as e:
            self.logger.error(f"Error in validate_asset_client_ids: {str(e)}")
            return ValidationResult(False, f"Validation error: {str(e)}")
            
            
            