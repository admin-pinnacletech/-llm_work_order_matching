import json
import os
import logging
from typing import Dict
from sqlalchemy import select
from work_order_review.database.models import Assessment

logger = logging.getLogger(__name__)

async def get_valid_assessment_ids(session, tenant_id: str, scenario_id: str) -> list:
    """Get list of valid assessment IDs for the tenant/scenario."""
    stmt = select(Assessment.id).where(
        Assessment.tenant_id == tenant_id,
        Assessment.facility_scenario_id == scenario_id
    )
    result = await session.execute(stmt)
    return [str(row[0]) for row in result]

def get_system_instructions() -> str:
    """Load system instructions from file."""
    instructions_path = os.path.join(
        os.path.dirname(__file__),
        'system_instructions.txt'
    )
    
    try:
        with open(instructions_path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading system instructions: {e}")
        raise

def get_function_schema(tenant_id: str, scenario_id: str) -> Dict:
    """Load and return the function schema."""
    schema_path = os.path.join(
        os.path.dirname(__file__),
        'function_schema.json'
    )
    
    try:
        # Load base schema
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        return schema
    except Exception as e:
        logger.error(f"Error loading function schema: {e}")
        raise

def get_assistant_config(tenant_id: str, scenario_id: str, vector_store_id: str) -> Dict:
    """Get the complete assistant configuration."""
    return {
        "name": "Work Order Matcher",
        "instructions": get_system_instructions(),
        "model": "gpt-4o-mini",
        "tools": [
            {
                "type": "function",
                "function": get_function_schema(tenant_id, scenario_id)
            },
            {
                "type": "file_search"
            }
        ],
        "tool_resources": {
            "file_search": {
                "vector_store_ids": [vector_store_id]
            }
        }
    } 