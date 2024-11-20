import json
import os
import datetime
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class ConversationLogger:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.conversation = []
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(output_dir, f"conversation_{timestamp}.json")

    def log_user_message(self, content: Any):
        """Log a message sent to the assistant"""
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'role': 'user',
            'content': content
        }
        self.conversation.append(entry)
        self._save_conversation()
        logger.debug(f"Logged user message: {json.dumps(content, indent=2)}")

    def log_assistant_message(self, content: Any):
        """Log a response from the assistant"""
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'role': 'assistant',
            'content': content
        }
        self.conversation.append(entry)
        self._save_conversation()
        logger.debug(f"Logged assistant message: {json.dumps(content, indent=2)}")

    def log_validation_result(self, is_valid: bool, errors: List[str] = None):
        """Log validation results"""
        entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'role': 'validator',
            'content': {
                'is_valid': is_valid,
                'errors': errors or []
            }
        }
        self.conversation.append(entry)
        self._save_conversation()
        logger.debug(f"Logged validation result: {json.dumps(entry['content'], indent=2)}")

    def _save_conversation(self):
        """Save the conversation to a file"""
        try:
            with open(self.log_file, 'w') as f:
                json.dump({
                    'conversation': self.conversation,
                    'metadata': {
                        'timestamp': datetime.datetime.now().isoformat(),
                        'total_messages': len(self.conversation)
                    }
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}") 