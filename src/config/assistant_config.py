import logging
import os
import json

logger = logging.getLogger(__name__)

def get_system_instructions():
    """Get the system instructions for the assistant."""
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'system_instructions.txt')
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read system instructions: {str(e)}")
        raise

def get_function_schema():
    """Get the function schema for validation."""
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'function_schema.json')
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read function schema: {str(e)}")
        raise

def update_assistant(client, assistant_id):
    """Update assistant with latest config."""
    logger.info(f"Updating assistant {assistant_id} with latest configuration")
    try:
        # Update assistant settings
        client.beta.assistants.update(
            assistant_id=assistant_id,
            name="Work Order Matching Assistant",
            instructions=get_system_instructions(),
            tools=[
                {"type": "file_search"},
                {"type": "function", "function": get_function_schema()}
            ],
            model="gpt-4o-mini"
        )
        
        logger.info("Successfully updated assistant configuration")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update assistant: {str(e)}")
        return False 