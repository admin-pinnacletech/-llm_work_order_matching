import os
import json
import time
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from openai import OpenAI
from sqlalchemy import text, select
import uuid
import datetime
from work_order_review.database.models import (
    WorkOrderMatch, 
    WorkOrderStatus, 
    Assessment, 
    Asset, 
    Component,
    WorkOrder
)
from work_order_review.config.assistant_config import get_assistant_config
from .response_validation_service import ResponseValidationService
import asyncio
from openai.types.beta.threads import Run
from typing_extensions import override
from openai import AssistantEventHandler
import nest_asyncio
from concurrent.futures import ThreadPoolExecutor
from work_order_review.database.models import WorkOrderStatus
# Enable nested event loops
nest_asyncio.apply()

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class WorkOrderEventHandler(AssistantEventHandler):
    def __init__(self, service, thread_id):
        super().__init__()
        self.service = service
        self.thread_id = thread_id
        self.latest_message = None
        self.error = None

    @override
    def on_event(self, event) -> None:
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)

    def handle_requires_action(self, data, run_id):
        tool_outputs = []
        
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "validate_asset_client_ids":
                try:
                    args = json.loads(tool.function.arguments)
                    # Use the service's event loop directly
                    validated_content = self.service._loop.run_until_complete(
                        self.service.validation_service.validate_asset_client_ids(args)
                    )
                    # Convert ValidationResult to dictionary before JSON serialization
                    output = json.dumps(validated_content.to_dict(), indent=4)
                    tool_outputs.append({"tool_call_id": tool.id, "output": output})
                except ValueError as ve:
                    self.service.logger.warning(f"Validation failed: {str(ve)}")
                    output = json.dumps({
                        "error": str(ve),
                        "valid": False,
                        "original_request": args
                    }, indent=4)
                    tool_outputs.append({"tool_call_id": tool.id, "output": output})
                except Exception as e:
                    self.service.logger.error(f"Error in validate_asset_client_ids: {str(e)}")
                    tool_outputs.append({"tool_call_id": tool.id, "output": str(e)})
        
        if tool_outputs:
            self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        try:
            self.service.client.beta.threads.runs.submit_tool_outputs(
                thread_id=self.thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs
            )
        except Exception as e:
            self.service.logger.error(f"Error submitting tool outputs: {str(e)}")
            self.error = str(e)

    @override
    def on_text_created(self, text) -> None:
        self.service.logger.info("New message created")
        self.service.logger.info(f"Text: {text}")
        
    @override
    def on_text_delta(self, delta, snapshot):
        self.latest_message = snapshot.value if snapshot else None
        if self.latest_message:
            # Pretty print the response in the logs
            try:
                pretty_message = json.dumps(json.loads(self.latest_message), indent=4)
                self.service.logger.info(f"Pretty Printed Response:\n{pretty_message}")
            except json.JSONDecodeError:
                self.service.logger.warning("Failed to pretty print the response")

class WorkOrderMatchingService:
    def __init__(self, session, tenant_id: str, scenario_id: str):
        self.session = session
        self.tenant_id = tenant_id
        self.scenario_id = scenario_id
        self.client = OpenAI()
        self.model = "gpt-4o-mini"
        self.assistant = None
        self.thread = None
        self.event_handler = None
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.validation_service = ResponseValidationService(session, tenant_id, scenario_id)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

    async def initialize(self):
        """Initialize the assistant and thread."""
        if not self.assistant:
            self.assistant = self._create_assistant()
        self.thread = self.client.beta.threads.create()
        self.event_handler = WorkOrderEventHandler(service=self, thread_id=self.thread.id)
        return self

    def _get_vector_store_id(self) -> str:
        """Get the vector store ID for the current tenant."""
        vector_store_name = f"work_order_matcher_assessments"
        vector_stores = self.client.beta.vector_stores.list()
        vector_store = next((vs for vs in vector_stores.data if vs.name == vector_store_name), None)
        return vector_store.id if vector_store else None

    def _create_assistant(self) -> Dict:
        """Create or update assistant with vector store access."""
        try:
            vector_store_id = self._get_vector_store_id()
            if not vector_store_id:
                raise ValueError("Vector store not found")
            
            assistant_params = get_assistant_config(
                self.tenant_id, 
                self.scenario_id, 
                vector_store_id
            )
            
            # Check for existing assistant
            assistants = self.client.beta.assistants.list()
            existing = next(
                (a for a in assistants if a.name == "Work Order Matcher"), 
                None
            )
            
            if existing:
                return self.client.beta.assistants.update(
                    assistant_id=existing.id,
                    **assistant_params
                )
            
            return self.client.beta.assistants.create(**assistant_params)
            
        except Exception as e:
            logger.error(f"Error creating assistant: {str(e)}")
            raise

    def _pretty_print_message(self, message) -> None:
        """Helper to pretty print a message content."""
        try:
            # Extract text content from the message
            for content_block in message.content:
                if hasattr(content_block, 'text'):
                    content = content_block.text.value
                    if content:
                        try:
                            # Try to parse and pretty print as JSON
                            parsed_content = json.loads(content)
                            logger.info(f"New message:\n{json.dumps(parsed_content, indent=2)}")
                        except json.JSONDecodeError:
                            # If not JSON, print as plain text
                            logger.info(f"New message:\n{content}")
                        break
        except Exception as e:
            logger.warning(f"Error pretty printing message: {str(e)}")

    def _pretty_print_tool_call(self, tool_call) -> None:
        """Helper to pretty print a tool call."""
        try:
            # Check if arguments is a string and try to parse it
            if isinstance(tool_call.function.arguments, str):
                args = json.loads(tool_call.function.arguments)
            else:
                args = tool_call.function.arguments
            
            logger.info(f"\nTool Call:\n"
                       f"Function: {tool_call.function.name}\n"
                       f"Arguments:\n{json.dumps(args, indent=2)}")
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing tool call arguments: {str(e)}")
            logger.warning(f"Raw arguments: {tool_call.function.arguments}")
        except Exception as e:
            logger.warning(f"Error pretty printing tool call: {str(e)}")

    async def process_work_orders(self, work_orders: List[WorkOrder], progress_callback=None) -> List[Dict]:
        """Process multiple work orders and return results."""
        results = []
        for index, work_order in enumerate(work_orders):
            result = await self.process_work_order(work_order)
            results.append(result)
            
            if progress_callback:
                progress_callback(work_order.id, index + 1)
        
        return results

    async def process_work_order(self, work_order: WorkOrder) -> Dict:
        """Process a single work order and return its result."""
        try:
            work_order_id = str(work_order.id)
            
            # Format the message for the assistant
            message = {
                "work_order": {
                    "id": work_order_id,
                    "summary": work_order.raw_data.get('summary', '')
                }
            }
            
            # Create message in thread
            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role="user",
                content=json.dumps(message, indent=4)
            )
            
            # Run the assistant
            run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant.id
            )
            
            # Wait for completion
            while True:
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=run.id
                )
                if run.status == 'completed':
                    break
                elif run.status == 'requires_action':
                    self.event_handler.handle_requires_action(run, run.id)
                elif run.status in ['failed', 'cancelled', 'expired']:
                    return {
                        'work_order_id': work_order_id,
                        'status': 'error',
                        'error': f'Assistant run failed with status: {run.status}'
                    }
                await asyncio.sleep(1)
            
            # Get the response
            messages = self.client.beta.threads.messages.list(
                thread_id=self.thread.id
            )
            response_content = messages.data[0].content[0].text.value if messages.data else None
            
            if not response_content:
                return {
                    'work_order_id': work_order_id,
                    'status': 'error',
                    'error': 'No response received from assistant'
                }

            # Save the matches
            save_success = await self._save_asset_matches(work_order_id, response_content)
            if save_success:
                return {
                    'work_order_id': work_order_id,
                    'status': 'success',
                    'response': response_content
                }
            else:
                return {
                    'work_order_id': work_order_id,
                    'status': 'error',
                    'error': 'Failed to save matches'
                }

        except Exception as e:
            self.logger.error(f"Error processing work order {work_order}: {str(e)}")
            return {
                'work_order_id': str(work_order.id),
                'status': 'error',
                'error': str(e)
            }
    async def _save_asset_matches(self, work_order_id: str, response_content: str) -> bool:
        """Save the asset matches to the database."""
        logger.info(f"Saving matches for work order {work_order_id}")
        try:

            
            # Ensure we have content
            if not response_content:
                logger.error("Invalid or empty response content")
                return False

            # Try to clean the content if it's a code block
            cleaned_content = response_content
            if response_content.startswith('```') and response_content.endswith('```'):
                # Extract content between code blocks
                lines = response_content.split('\n')
                cleaned_content = '\n'.join(lines[1:-1])  # Remove first and last lines

            # Parse the response content
            try:
                response_data = json.loads(cleaned_content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {str(e)}")
                logger.error(f"Failed content: '{cleaned_content}'")
                return False

            # Validate response structure
            if not isinstance(response_data, dict) or 'matches' not in response_data:
                logger.error("Response missing required 'matches' field")
                return False

            matches = response_data['matches']
            if not isinstance(matches, list):
                logger.error("'matches' field must be a list")
                return False

            # Delete existing matches
            delete_stmt = text("""
                DELETE FROM work_order_matches 
                WHERE work_order_id = :work_order_id
            """)
            await self.session.execute(delete_stmt, {'work_order_id': work_order_id})
            
            # Insert new matches
            for match in matches:
                try:
                    new_match = WorkOrderMatch(
                        id=str(uuid.uuid4()),
                        work_order_id=work_order_id,
                        asset_client_id=match['asset_client_id'],
                        matching_confidence_score=float(match['matching_confidence_score']),
                        matching_reasoning=match['matching_reasoning'],
                    )
                    self.session.add(new_match)
                except (KeyError, ValueError) as e:
                    logger.error(f"Invalid match data: {str(e)}")
                    await self.session.rollback()
                    return False
            
            # Update work order status
            update_stmt = text("""
                UPDATE work_orders 
                SET status = :status
                WHERE id = :work_order_id
            """)
            await self.session.execute(
                update_stmt,
                {
                    'status': WorkOrderStatus.PENDING_REVIEW.value,
                    'work_order_id': work_order_id
                }
            )
            
            await self.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error saving matches: {str(e)}")
            await self.session.rollback()
            return False

    async def cleanup(self):
        """Clean up resources after processing all work orders."""
        if self.thread:
            try:
                self.client.beta.threads.delete(self.thread.id)
            except Exception as e:
                self.logger.warning(f"Failed to delete thread: {str(e)}")

    def __del__(self):
        """Cleanup resources on deletion."""
        self._executor.shutdown(wait=False)
        if self._loop.is_running():
            self._loop.stop()
        self._loop.close()
