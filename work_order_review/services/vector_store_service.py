import logging
import json
from typing import Dict, Optional, List, Tuple, Callable
from openai import OpenAI
from contextlib import ExitStack
import tempfile
import os
import sys
import asyncio
import streamlit as st
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
        
    async def get_or_create_store(self) -> str:
        """Get or create the vector store."""
        try:
            # List existing stores
            stores = self.client.beta.vector_stores.list()
            
            # Check if our store exists
            for store in stores.data:
                if store.name == self.vector_store_name:
                    logger.info(f"Found existing vector store: {store.id}")
                    return store.id
            
            # Create new store if not found
            logger.info("Creating new vector store")
            store = self.client.beta.vector_stores.create(
                name=self.vector_store_name,
                description="Vector store for work order matching assessments"
            )
            logger.info(f"Created new vector store: {store.id}")
            return store.id
            
        except Exception as e:
            logger.error(f"Error getting/creating vector store: {str(e)}")
            raise

    async def upload_assessments(
        self, 
        assessments: List[Dict], 
        progress_callback: Optional[Callable[[int, int], None]] = None,
        batch_size: int = 1000,
        chunk_size: int = 1000  # Size of text chunks for embedding
    ) -> Tuple[bool, Dict[str, any]]:
        """Upload assessments to the vector store in batches."""
        try:
            logger.info(f"Starting upload of {len(assessments)} assessments")
            vector_store_id = await self.get_or_create_store()
            
            # Track statistics
            stats = {
                "total_processed": len(assessments),
                "created": 0,
                "updated": 0,
                "errors": 0,
                "chunks_created": 0
            }
            
            # Process in batches
            for i in range(0, len(assessments), batch_size):
                batch = assessments[i:i + batch_size]
                
                # Create temporary files for batch upload
                temp_files = []
                try:
                    # Process each assessment in the batch
                    for assessment in batch:
                        # Convert assessment to text and chunk it
                        text = json.dumps(assessment)
                        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
                        
                        # Create embeddings for each chunk
                        embeddings_response = self.client.embeddings.create(
                            model="text-embedding-3-small",
                            input=chunks,
                            encoding_format="float"
                        )
                        
                        # Create temp file for chunks and their embeddings
                        temp_fd, temp_path = tempfile.mkstemp(suffix='.json')
                        with os.fdopen(temp_fd, 'w') as temp_file:
                            for chunk_idx, (chunk, embedding_data) in enumerate(zip(chunks, embeddings_response.data)):
                                json_line = {
                                    "text": chunk,
                                    "embedding": embedding_data.embedding,
                                    "metadata": {
                                        'tenant_id': st.session_state.tenant_id,
                                        'scenario_id': st.session_state.scenario_id,
                                        'asset_client_id': assessment.get('assetClientId'),
                                        'component_client_id': assessment.get('componentClientId'),
                                        'asset_name': assessment.get('assetName'),
                                        'component_name': assessment.get('componentName')
                                    }
                                }
                                temp_file.write(json.dumps(json_line) + "\n")
                        temp_files.append(temp_path)
                        stats["chunks_created"] += len(chunks)
                    
                    # Upload batch files to vector store
                    logger.info(f"Uploading batch {i//batch_size + 1} to vector store")
                    for file_path in temp_files:
                        try:
                            # Upload file
                            with open(file_path, 'rb') as file_data:
                                file = self.client.files.create(
                                    file=file_data,
                                    purpose="assistants"
                                )
                            
                            # Wait for file to be processed
                            max_retries = 5
                            for retry in range(max_retries):
                                try:
                                    file_status = self.client.files.retrieve(file.id)
                                    if file_status.status == "processed":
                                        break
                                    if retry < max_retries - 1:
                                        await asyncio.sleep(1)
                                except Exception as e:
                                    logger.warning(f"Error checking file status (attempt {retry+1}): {str(e)}")
                                    if retry < max_retries - 1:
                                        await asyncio.sleep(1)
                            
                            # Add processed file to vector store
                            if file_status.status == "processed":
                                self.client.beta.vector_stores.files.create(
                                    vector_store_id=vector_store_id,
                                    file_id=file.id
                                )
                                stats["created"] += 1
                                logger.info(f"Successfully uploaded and processed file {file.id}")
                            else:
                                raise Exception(f"File {file.id} failed to process after {max_retries} attempts")
                            
                        except Exception as e:
                            logger.error(f"Error uploading file {file_path}: {str(e)}")
                            stats["errors"] += 1
                            
                finally:
                    # Clean up temp files for this batch
                    for file_path in temp_files:
                        try:
                            if os.path.exists(file_path):
                                os.unlink(file_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete temp file {file_path}: {str(e)}")
                
                # Update progress after each batch
                if progress_callback:
                    progress_callback(min(i + batch_size, len(assessments)), len(assessments))
                
            logger.info("Upload complete")
            return True, {
                "message": f"Successfully uploaded {len(assessments)} assessments ({stats['chunks_created']} chunks)",
                **stats
            }
            
        except Exception as e:
            logger.error(f"Error uploading assessments: {str(e)}")
            return False, {
                "message": str(e),
                "total_processed": len(assessments),
                "created": stats.get("created", 0),
                "updated": stats.get("updated", 0),
                "errors": len(assessments) - stats.get("created", 0),
                "chunks_created": stats.get("chunks_created", 0)
            }

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