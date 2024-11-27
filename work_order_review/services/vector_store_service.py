import logging
import json
from typing import Dict, Optional
from openai import OpenAI
from contextlib import ExitStack
import tempfile
import os
import sys
import asyncio

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler with formatting
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add handler to logger if it doesn't already have handlers
if not logger.handlers:
    logger.addHandler(console_handler)

class VectorStoreService:
    def __init__(self):
        self.client = OpenAI()
        self.vector_store_name = "work_order_matcher_assessments"

    async def verify_metadata(self, vector_store_id: str = None) -> None:
        """Verify metadata is properly stored and can be filtered."""
        try:
            if not vector_store_id:
                vector_store_id = await self.get_or_create_store()

            # Get all files in the vector store
            files = self.client.beta.vector_stores.files.list(vector_store_id=vector_store_id)
            
            logger.info(f"\nTotal files in store: {len(files.data)}")
            
            # Examine the first few files in detail
            for file in files.data[:5]:  # Look at first 5 files
                logger.info(f"\nFile ID: {file.id}")
                
                # Get file content
                file_content = self.client.files.retrieve_content(file_id=file.id)
                logger.info(f"Content sample: {file_content[:500]}...")  # First 500 chars
                
                # Log metadata if present
                if hasattr(file, 'metadata'):
                    logger.info(f"Metadata: {json.dumps(file.metadata, indent=2)}")
                else:
                    logger.info("No metadata found")
                logger.info("-" * 80)

        except Exception as e:
            logger.error(f"Error verifying metadata: {str(e)}")