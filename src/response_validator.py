from typing import Dict, List, Union, Any
import logging
import json
import uuid

logger = logging.getLogger(__name__)

class ResponseValidator:
    def __init__(self, assessments: List[Dict]):
        self.assessments = assessments
        self.validation_errors = []
        
        # Create lookup dictionary for valid assessment IDs
        # Ensure we handle both string and UUID formats
        self.assessment_lookup = {}
        for assessment in assessments:
            assessment_id = str(assessment.get('id', '')).lower()
            if assessment_id:
                self.assessment_lookup[assessment_id] = assessment
        
        logger.info(f"Initialized validator with {len(self.assessment_lookup)} valid assessment IDs")

    def validate_response(self, response: Dict) -> bool:
        """Validates the response from the assistant"""
        self.validation_errors = []
        
        # Handle retry responses
        if isinstance(response, dict) and 'status' in response and response['status'] == 'retry':
            required_retry_fields = ['status', 'reason', 'suggested_batch_size']
            if all(field in response for field in required_retry_fields):
                return True
            else:
                self.validation_errors.append(f"Retry response missing required fields: {required_retry_fields}")
                return False
        
        # Handle matches responses
        try:
            # If it's a single match response, wrap it in a list
            if isinstance(response, dict) and ('work_order' in response or 'assessments' in response):
                response = [response]
                
            return self._validate_matches_response(response)
        except Exception as e:
            self.validation_errors.append(f"Validation error: {str(e)}")
            return False

    def _log_response(self, response: Union[Dict, List]):
        """Logs details about the received response."""
        if isinstance(response, dict) and 'status' in response:
            self.logger.info(f"Response type: Retry/Error request")
            self.logger.info(f"Status: {response['status']}")
            if 'reason' in response:
                self.logger.info(f"Reason: {response['reason']}")
        else:
            self.logger.info(f"Response type: Matches")
            self.logger.info(f"Number of matches: {len(response)}")

    def _validate_response_structure(self, response: Union[Dict, List]) -> bool:
        """Validates the overall response structure."""
        # Check if response is retry request
        if isinstance(response, dict) and 'status' in response:
            return self._validate_retry_response(response)
        
        # Otherwise, validate as matches response
        return self._validate_matches_response(response)

    def _validate_retry_response(self, response: Dict) -> bool:
        """Validates a retry response"""
        required_fields = ['status', 'reason']
        
        # Check required fields exist
        if not all(field in response for field in required_fields):
            self.validation_errors.append("Retry response missing required fields")
            return False
            
        # Validate status is 'retry'
        if response['status'] != 'retry':
            self.validation_errors.append("Invalid status for retry response")
            return False
            
        return True

    def _validate_matches_response(self, response: List) -> bool:
        """Validates a matches response"""
        if not isinstance(response, list):
            self.validation_errors.append("Response must be a list of matches")
            return False
            
        for match in response:
            if not self._validate_match(match):
                return False
                
        return True

    def _validate_match(self, match: Dict) -> bool:
        """Validates an individual match object"""
        # Validate work order
        if not self._validate_work_order(match.get('work_order', {})):
            return False
            
        # Validate assessments
        if not self._validate_assessments(match.get('assessments', []), match.get('work_order', {})):
            return False
            
        return True

    def _validate_work_order(self, work_order: Dict) -> bool:
        """Validates a work order object"""
        required_fields = ['id', 'description']
        
        if not all(field in work_order for field in required_fields):
            self.validation_errors.append(f"Work order missing required fields: {required_fields}")
            return False
            
        # Add specific work order validation logic here
        # For example:
        # - ID format validation
        # - Description minimum length
        # - Impact value validation
            
        return True

    def _validate_assessments(self, assessments: List[Dict], work_order: Dict) -> bool:
        """Validate assessment matches and encourage multiple when appropriate."""
        if not isinstance(assessments, list):
            self.validation_errors.append("Assessments must be a list")
            return False
            
        if not assessments:
            return True  # Empty list is valid if no matches found
            
        # Validate each assessment
        for assessment in assessments:
            if not self._validate_assessment(assessment):
                return False
                
        # Check for duplicate assessment IDs
        assessment_ids = [str(a.get('assessment_id')).lower() for a in assessments]
        if len(assessment_ids) != len(set(assessment_ids)):
            self.validation_errors.append("Duplicate assessment IDs found")
            return False
            
        return True

    def _validate_assessment(self, assessment: Dict) -> bool:
        """Validates an individual assessment match"""
        # Check if assessment_id is same as asset_client_id (incorrect)
        if assessment.get('assessment_id') == assessment.get('asset_client_id'):
            self.validation_errors.append(
                f"Assessment ID cannot be same as asset_client_id: {assessment.get('assessment_id')}"
            )
            return False
        
        # Validate assessment_id format (must be UUID or "unknown")
        assessment_id = str(assessment.get('assessment_id', '')).lower()
        if assessment_id != "unknown":
            try:
                uuid.UUID(assessment_id)
            except ValueError:
                self.validation_errors.append(
                    f"Invalid UUID format for assessment_id: {assessment_id}"
                )
                return False
            
        # Check if assessment_id exists in our data (if not "unknown")
        if assessment_id != "unknown" and assessment_id not in self.assessment_lookup:
            self.validation_errors.append(
                f"Assessment ID '{assessment_id}' not found in valid assessments data"
            )
            return False
        
        # Validate UUID format
        try:
            uuid.UUID(assessment_id)
        except ValueError:
            self.validation_errors.append(f"Invalid UUID format for assessment_id: {assessment_id}")
            return False
        
        # Validate asset_client_id matches the referenced assessment
        original_assessment = self.assessment_lookup[assessment_id]
        if assessment.get('asset_client_id') != original_assessment.get('asset_client_id'):
            self.validation_errors.append(
                f"Asset client ID mismatch for assessment {assessment_id}. "
                f"Got {assessment.get('asset_client_id')}, "
                f"expected {original_assessment.get('asset_client_id')}"
            )
            return False
        
        # Validate confidence score
        score = assessment.get('confidence_score')
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            self.validation_errors.append(
                f"Confidence score must be a number between 0 and 1, got: {score}"
            )
            return False
        
        # Validate reasoning
        reasoning = assessment.get('reasoning', '')
        if not reasoning or len(reasoning.strip()) < 10:
            self.validation_errors.append("Reasoning must be at least 10 characters long")
            return False
            
        return True

    def get_validation_errors(self) -> List[str]:
        """Returns list of validation errors from last validation"""
        return self.validation_errors 

    def _provide_negative_feedback(self, validation_errors: List[str]) -> str:
        return json.dumps({
            "feedback_type": "negative",
            "message": "STOP! Your response format is incorrect. Follow these rules:",
            "rules": [
                "1. Respond with ONLY JSON - no other text",
                "2. Do not explain or analyze outside the JSON",
                "3. Do not include source citations",
                "4. If unsure, return empty arrays rather than explanations"
            ],
            "example": {
                "work_order": {"id": "123", "description": "example"},
                "assessments": [],
                "repair_classification": {
                    "is_repair": false,
                    "reasoning": "Cannot determine"
                }
            }
        })