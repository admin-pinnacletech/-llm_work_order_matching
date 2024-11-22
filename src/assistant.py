import qc_review.newton_api_utils as newton_api_utils
from src.folder_structure_manager import FolderStructureManager
from qc_review.newton_data_retrieval import NewtonDataRetriever
from llm_work_order_matching.data_processor.services import PreProcessor

from openai import OpenAI
import json
import os
import dotenv
import datetime
import logging
import asyncio
from typing import List, Dict, Any
import shutil
from config import assistant_config
from src.response_validator import ResponseValidator
from conversation_logger import ConversationLogger
from tqdm import tqdm
import random
import time
import re

dotenv.load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)

class WorkOrderMatcher:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI()
        self.model = model
        self.assistant = self._create_assistant()
        
        # Add a timestamp for the batch
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async def process_batch(self, work_orders: List[Dict]) -> List[Dict]:
        """Process a batch of work orders and return matches."""
        all_results = []
        
        for work_order in tqdm(work_orders, desc="Processing Work Orders"):
            try:
                # Create thread and process work order
                thread = self.client.beta.threads.create()
                
                # Add the work order to the thread
                message = self.client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=json.dumps({"work_order": work_order})
                )
                
                # Run the assistant
                run = self.client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=self.assistant.id
                )
                
                # Wait for completion
                while True:
                    run_status = self.client.beta.threads.runs.retrieve(
                        thread_id=thread.id,
                        run_id=run.id
                    )
                    
                    if run_status.status == 'completed':
                        # Get the results
                        messages = self.client.beta.threads.messages.list(
                            thread_id=thread.id
                        )
                        
                        # Process the response
                        result = self._process_response(messages.data[0], work_order)
                        if result:
                            all_results.append(result)
                        break
                    
                    elif run_status.status == 'failed':
                        print(f"Run failed for work order {work_order.get('id')}")
                        break
                    
                    await asyncio.sleep(1)
                
            except Exception as e:
                print(f"Error processing work order {work_order.get('id')}: {str(e)}")
                continue
        
        return all_results

    def _get_vector_store_id(self) -> str:
        """Get the vector store ID for the current tenant."""
        vector_store_name = f"{self.newton_path['tenantIdentifier']}_{self.newton_path['facilityScenarioId']}_assessments"
        vector_stores = self.client.beta.vector_stores.list()
        vector_store = next((vs for vs in vector_stores.data if vs.name == vector_store_name), None)
        return vector_store.id if vector_store else None

    def _create_assistant(self) -> Dict:
        """Create or update an assistant for work order matching."""
        try:
            instructions = assistant_config.get_system_instructions()
            function_schema = assistant_config.get_function_schema()
            
            assistant_params = {
                "name": "Work Order Matcher",
                "instructions": instructions,
                "model": self.model,
                "tools": [
                    {"type": "function", "function": function_schema},
                    {"type": "file_search"}
                ],
                "tool_resources": {
                    'file_search': {
                        'vector_store_ids': [self._get_vector_store_id()]
                    }
                }
            }

            # Check for existing assistant
            assistants = self.client.beta.assistants.list()
            for assistant in assistants:
                if assistant.name == "Work Order Matcher":
                    logger.info(f"Found existing assistant: {assistant.id}. Updating parameters...")
                    updated_assistant = self.client.beta.assistants.update(
                        assistant_id=assistant.id,
                        **assistant_params
                    )
                    return updated_assistant

            # Create new assistant if none exists
            assistant = self.client.beta.assistants.create(**assistant_params)
            logger.info(f"Created new assistant: {assistant.id}")
            return assistant
            
        except Exception as e:
            logger.error(f"Error creating/updating assistant: {str(e)}")
            raise

    async def _handle_function_call(self, function_name: str, arguments: Dict) -> Any:
        """Handle function calls from the assistant."""
        logger.debug(f"Handling function call: {function_name}")
        logger.debug(f"Function arguments: {arguments}")
        
        try:
            if function_name == "validate_response":
                response = arguments.get("response", {})
                if not self.validator:
                    logger.error("Validator not initialized")
                    return {
                        "status": "error",
                        "message": "Validator not initialized"
                    }
                
                is_valid = self.validator.validate_response(response)
                return {
                    "is_valid": is_valid,
                    "errors": self.validator.validation_errors if not is_valid else [],
                    "status": "success" if is_valid else "error",
                    "message": "Validation successful" if is_valid else "Validation failed"
                }
            elif function_name == "match_work_order":
                return {
                    "matches": [],  # Return empty matches to let the assistant decide
                    "status": "success",
                    "message": "Function executed successfully"
                }
            elif function_name == "classify_repair":
                work_order = arguments.get("work_order", {})
                description = work_order.get("description", "").lower()
                wo_type = work_order.get("WO Type", "").lower()
                
                return {
                    "status": "success",
                    "work_order_info": {
                        "description": description,
                        "type": wo_type
                    }
                }
            else:
                logger.error(f"Unknown function: {function_name}")
                return {
                    "status": "error",
                    "message": f"Unknown function: {function_name}"
                }
                
        except Exception as e:
            logger.error(f"Error in function {function_name}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Function error: {str(e)}"
            }

    def _save_progress(self, results: List[Dict], processed: int, total: int):
        """Save intermediate results to file."""
        try:
            # Create a progress summary
            summary = {
                'timestamp': datetime.datetime.now().isoformat(),
                'progress': {
                    'processed': processed,
                    'total': total,
                    'percentage': round((processed / total) * 100, 2)
                },
                'results': results
            }
            
            # Save to file
            with open(self.results_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"Saved progress ({processed}/{total} work orders) to {self.results_file}")
            
        except Exception as e:
            logger.error(f"Error saving progress: {str(e)}", exc_info=True)

    def _load_work_orders(self, filepaths):
        """Load work orders from batched files."""
        work_orders = []
        work_order_dir = os.path.join(filepaths['pre_processed_data'], 'work_orders')
        
        for filename in os.listdir(work_order_dir):
            if filename.startswith('work_orders_batch_'):
                with open(os.path.join(work_order_dir, filename), 'r') as f:
                    batch = json.load(f)
                    work_orders.extend(batch)
        
        return work_orders

    def _provide_negative_feedback(self, validation_errors: List[str]) -> str:
        """Generate negative feedback message for invalid responses"""
        feedback = {
            "feedback_type": "negative",
            "message": "Your previous response was incorrect. Please carefully note:",
            "errors": validation_errors,
            "instructions": [
                "Do not include asset_client_id values unless they are confirmed in the assessment data",
                "Verify all assessment IDs exist in the provided assessments",
                "Double-check all field values against the validation requirements"
            ]
        }
        return json.dumps(feedback, indent=2)

    async def _confirm_empty_assessments(self, work_order):
        """Ask the model to confirm if there really are no matches for this work order."""
        prompt = f"""Please review this work order one more time and provide:
1. Confirm if there are truly no matching assessments
2. Classify whether this is a repair work order by checking:
   - Does it fix something broken?
   - Does it replace failed components?
   - Is it corrective maintenance?
   - Does it address a breakdown?

Work Order ID: {work_order['id']}
Description: {work_order['description']}
Type: {work_order.get('WO Type', 'Unknown')}
Activity Type: {work_order.get('Maintenance Activity Type', 'Unknown')}
Breakdown Indicator: {work_order.get('Breakdown Indicator', 'Unknown')}

If you find any matches, return them in the standard format.
If confirming no matches, explain why and include repair classification with reasoning."""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0
            )
            
            # Try to parse any JSON in the response
            try:
                content = response.choices[0].message.content
                # First try to parse as JSON
                try:
                    result = json.loads(content)
                    if isinstance(result, list) and len(result) > 0:
                        return result
                    elif isinstance(result, dict):
                        return [{
                            "work_order": work_order,
                            "assessments": result.get("assessments", []),
                            "repair_classification": result.get("repair_classification", {
                                "is_repair": False,
                                "reasoning": "Unable to determine from model response"
                            })
                        }]
                except json.JSONDecodeError:
                    # If not JSON, analyze the text response
                    is_repair = "repair" in content.lower() or "fix" in content.lower() or "replace" in content.lower()
                    repair_reason = content if len(content) < 100 else "Extracted from model's textual response"
                    return [{
                        "work_order": work_order,
                        "assessments": [],
                        "repair_classification": {
                            "is_repair": is_repair,
                            "reasoning": repair_reason
                        }
                    }]
            except json.JSONDecodeError:
                # If we can't parse JSON, assume model confirms no matches
                pass
            
            return [{
                "work_order": work_order,
                "assessments": [],
                "repair_classification": {
                    "is_repair": False,
                    "reasoning": "Unable to determine repair classification"
                }
            }]
            
        except Exception as e:
            logger.error(f"Error in confirmation check: {e}", exc_info=True)
            return [{
                "work_order": work_order,
                "assessments": [],
                "repair_classification": {
                    "is_repair": False,
                    "reasoning": "Error occurred during confirmation check"
                }
            }]

    def _extract_json_from_response(self, response_text: str, wo_id: str) -> str:
        """Extract JSON content from a response that might contain markdown and other text."""
        logger.debug(f"Attempting to extract JSON from response for WO {wo_id}")
        
        try:
            # Clean up common formatting issues
            response_text = response_text.replace('\n', ' ').strip()
            
            # Remove markdown headers and sections
            response_text = re.sub(r'###.*?\n', '', response_text)
            response_text = re.sub(r'\*\*.*?\*\*', '', response_text)
            
            # First try to parse the entire response as JSON
            try:
                json.loads(response_text)
                return response_text
            except json.JSONDecodeError:
                pass
            
            # Look for JSON between triple backticks
            json_pattern = r'```(?:json)?(.*?)```'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            for match in matches:
                try:
                    cleaned = match.strip()
                    json.loads(cleaned)
                    return cleaned
                except json.JSONDecodeError:
                    continue
            
            # Look for content between curly braces
            brace_pattern = r'\{[^{}]*\}'
            matches = re.findall(brace_pattern, response_text)
            for match in matches:
                try:
                    json.loads(match)
                    return match
                except json.JSONDecodeError:
                    continue
            
            # If no valid JSON found, try to construct one from the narrative
            if "assessment" in response_text.lower():
                constructed_json = self._construct_json_from_narrative(response_text)
                if constructed_json:
                    return constructed_json
            
            logger.error(f"Could not find valid JSON in response for WO {wo_id}")
            logger.debug(f"Raw response: {response_text}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON for WO {wo_id}: {str(e)}")
            logger.debug(f"Raw response: {response_text}")
            return None

    def _construct_json_from_narrative(self, text: str) -> str:
        """Attempt to construct JSON from narrative text."""
        try:
            result = {
                "assessments": [],
                "repair_classification": {
                    "is_repair": False,
                    "reasoning": "Unable to determine from narrative"
                }
            }
            
            # Look for repair classification
            repair_matches = re.findall(r'is.?repair:?\s*(true|false)', text, re.IGNORECASE)
            if repair_matches:
                result["repair_classification"]["is_repair"] = repair_matches[0].lower() == "true"
            
            # Look for reasoning
            reasoning_matches = re.findall(r'reasoning:?\s*([^\.]*\.)', text, re.IGNORECASE)
            if reasoning_matches:
                result["repair_classification"]["reasoning"] = reasoning_matches[0].strip()
            
            # Look for assessments
            assessment_pattern = r'assessment.*?id:?\s*([a-f0-9-]+).*?asset.*?id:?\s*([^\s,]+).*?name:?\s*([^,\n]+)'
            assessment_matches = re.findall(assessment_pattern, text, re.IGNORECASE | re.DOTALL)
            
            for match in assessment_matches:
                assessment = {
                    "assessment_id": match[0],
                    "asset_client_id": match[1],
                    "asset_name": match[2].strip(),
                    "confidence_score": 0.7,  # Default score
                    "reasoning": "Extracted from narrative"
                }
                result["assessments"].append(assessment)
            
            return json.dumps(result)
        except Exception as e:
            logger.error(f"Error constructing JSON from narrative: {str(e)}")
            return None

    def _log_run_details(self, thread_id: str, run_id: str, wo_id: str):
        """Log detailed information about a run failure."""
        try:
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id
            )
            
            logger.error(f"\nDetailed run information for WO {wo_id}:")
            logger.error(f"Run ID: {run.id}")
            logger.error(f"Status: {run.status}")
            logger.error(f"Started at: {self._format_timestamp(run.started_at)}")
            logger.error(f"Failed at: {self._format_timestamp(run.failed_at) if hasattr(run, 'failed_at') else 'Unknown'}")
            logger.error(f"Model: {run.model}")
            
            # Safely get error information
            if hasattr(run, 'last_error') and run.last_error:
                logger.error(f"Error Code: {run.last_error.code}")
                logger.error(f"Error Message: {run.last_error.message}")
            else:
                logger.error("No detailed error information available.")
            
            # Get run steps for more detail
            try:
                steps = self.client.beta.threads.runs.steps.list(
                    thread_id=thread_id,
                    run_id=run_id
                )
                logger.error("\nRun steps:")
                for step in steps.data:
                    logger.error(f"Step {step.id}:")
                    logger.error(f"  Type: {step.type}")
                    logger.error(f"  Status: {step.status}")
                    if hasattr(step, 'step_details') and step.step_details:
                        logger.error(f"  Details: {step.step_details}")
                    if hasattr(step, 'last_error') and step.last_error:
                        logger.error(f"  Step Error: {step.last_error.message}")
            except Exception as step_error:
                logger.error(f"Error retrieving run steps: {str(step_error)}")
            
            # Get thread messages
            try:
                messages = self.client.beta.threads.messages.list(thread_id=thread_id)
                logger.error("\nThread messages:")
                for msg in messages.data:
                    logger.error(f"Message {msg.id} ({msg.role}):")
                    for content in msg.content:
                        if content.type == 'text':
                            logger.error(f"  Content: {content.text.value[:200]}...")
                        else:
                            logger.error(f"  Content type {content.type} not handled.")
            except Exception as msg_error:
                logger.error(f"Error retrieving thread messages: {str(msg_error)}")
                
        except Exception as e:
            logger.error(f"Error getting run details: {str(e)}")

    def _format_timestamp(self, timestamp: int) -> str:
        """Convert UNIX timestamp to readable datetime string."""
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return 'Invalid timestamp'

    def _log_request_details(self, work_order: Dict):
        """Log details of the request being sent to the assistant."""
        try:
            logger.debug(f"\nRequest details for WO {work_order.get('id', 'unknown')}:")
            logger.debug(json.dumps(work_order, indent=2))
        except Exception as e:
            logger.error(f"Error logging request details: {str(e)}")

    def _create_error_result(self, work_order: Dict, error_message: str, raw_response: str = None) -> Dict:
        """Create a standardized error result object."""
        result = {
            "work_order": work_order,
            "assessments": [],
            "repair_classification": {
                "is_repair": False,
                "reasoning": f"Error occurred: {error_message}"
            },
            "error": error_message
        }
        
        if raw_response is not None:
            result["raw_response"] = raw_response
            
        return result

    async def _retry_failed_response(self, thread_id: str, wo_id: str) -> Dict:
        """Retry with simplified prompt when parsing fails."""
        retry_prompt = (
            "Your last response could not be parsed. Respond with ONLY this JSON structure:\n"
            "{\n"
            '  "work_order": {"id": "' + wo_id + '", "description": "..."},\n'
            '  "assessments": [],\n'
            '  "repair_classification": {"is_repair": false, "reasoning": "..."}\n'
            "}"
        )
        
        messages = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=retry_prompt
        )
        
        # Run and get response...

async def main():
    try:
        # Initialize data pipeline
        USER_ID = '4c453411-6d39-4704-81d0-ac09014d83eb'
        newton_path = {
            'tenantIdentifier': 'kuraray',
            'facilityScenarioId': 209309816,
            'authHeader': newton_api_utils.build_api_header(USER_ID)
        }
        
        # Setup data structures
        folder_manager = FolderStructureManager(newton_path)
        filepaths = folder_manager.build_folders()
        data_retriever = NewtonDataRetriever(newton_path, use_local_cache=True)
        raw_data = await data_retriever.retrieve_raw_data()
        
        # Pass filepaths to PreProcessor
        pre_processor = PreProcessor(newton_path, raw_data, filepaths)
        processed_data = await pre_processor.pre_process()

        # Get work orders and assessments
        work_orders = processed_data['workOrders']
        assessments = processed_data['assessments']

        debug_limit = 500
        #random.seed(42)
        #if debug limit is set, randomly select a subset of work orders
        if debug_limit > 0:
            work_orders = random.sample(work_orders, debug_limit)

        # Initialize matcher
        matcher = WorkOrderMatcher(
            os.getenv('OPENAI_API_KEY'),
            model="gpt-4o-mini",
            newton_path=newton_path,
            filepaths=filepaths
        )

        # Process all work orders in a single batch
        logger.info(f"Starting batch processing of {len(work_orders)} work orders")
        results = await matcher.process_batch(work_orders, assessments)
        
        # No need for additional save since _save_progress already saves to the final file
        logger.info(f"Final results saved to {matcher.results_file}")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())

