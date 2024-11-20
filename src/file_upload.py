import logging
import newton_api_utils
from folder_structure_manager import FolderStructureManager
from newton_data_retrieval import NewtonDataRetriever
from pre_processing import PreProcessor

from openai import OpenAI
import json
import os
import dotenv
import requests
from icecream import ic
from tqdm import tqdm
from contextlib import ExitStack
import openai
import time
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio
from concurrent.futures import ThreadPoolExecutor

dotenv.load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)

logger.addHandler(console_handler)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry_error_callback=lambda retry_state: None  # Return None on final failure
)
def upload_file_with_retry(client, file_path, filename):
    """Attempt to upload a file with retry logic."""
    with open(file_path, 'rb') as f:
        return client.files.create(
            file=f,
            purpose='assistants'
        )

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def add_to_vector_store(client, vector_store_id, file_path):
    """Upload and add a file to the vector store with retry logic."""
    # First upload the file with correct purpose
    with open(file_path, 'rb') as f:
        file = client.files.create(
            file=f,
            purpose='assistants'  # Changed from 'vector_store' to 'assistants'
        )
    
    # Then add it to the vector store
    return client.beta.vector_stores.files.create(  # Changed API endpoint
        vector_store_id=vector_store_id,
        file_id=file.id
    )

async def upload_assessments_to_vector_store(client, vector_store_id, filepaths, chunk_size=200):
    """Upload assessment files to OpenAI vector store using batch upload and polling."""
    logger.info("Starting assessment upload")
    
    assessment_dir = os.path.join(filepaths['pre_processed_data'], 'assessments')
    if not os.path.exists(assessment_dir):
        logger.error(f"Assessment directory not found: {assessment_dir}")
        return False
        
    try:
        # Get list of assessment files
        assessment_files = [f for f in os.listdir(assessment_dir) if f.endswith('.json')]
        total_files = len(assessment_files)
        logger.info(f"Found {total_files} assessment files to upload")
        
        # Process files in chunks
        for i in range(0, total_files, chunk_size):
            chunk = assessment_files[i:i + chunk_size]
            logger.info(f"Processing chunk {i//chunk_size + 1} of {(total_files + chunk_size - 1)//chunk_size} ({len(chunk)} files)")
            
            # Use the upload_and_poll method to handle the batch upload
            with ExitStack() as stack:
                # Open and manage all file streams for this chunk
                file_streams = [
                    stack.enter_context(open(os.path.join(assessment_dir, f), 'rb'))
                    for f in chunk
                ]
                
                file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store_id,
                    files=file_streams
                )
                
                logger.info(f"Chunk upload status: {file_batch.status}")
                logger.info(f"File counts: {file_batch.file_counts}")
                
                if file_batch.status != "completed":
                    logger.error(f"Chunk upload failed with status: {file_batch.status}")
                    return False
        
        logger.info("All chunks uploaded successfully")
        return True
            
    except Exception as e:
        logger.error(f"Error uploading assessments: {str(e)}")
        return False

async def main():
    logger.info("Starting file upload process")
    try:
        USER_ID = '4c453411-6d39-4704-81d0-ac09014d83eb'
        newton_path = {
            'tenantIdentifier': 'kuraray',
            'facilityScenarioId': 209309816,
            'authHeader': newton_api_utils.build_api_header(USER_ID)
        }
        logger.info(f"Initialized with tenant: {newton_path['tenantIdentifier']}")
        
        folder_structure_manager = FolderStructureManager(newton_path)
        filepaths = folder_structure_manager.build_folders()
        logger.debug("Folder structure created")
        
        data_retriever = NewtonDataRetriever(newton_path, use_local_cache=True)
        raw_data = await data_retriever.retrieve_raw_data()
        logger.info("Raw data retrieved successfully")
        
        pre_processor = PreProcessor(newton_path, raw_data, filepaths)
        pre_processed_data = pre_processor.pre_process()
        logger.info("Data pre-processing completed")

        assessments = pre_processed_data['assessments']
        work_orders = pre_processed_data['workOrders']
        logger.info(f"Loaded {len(assessments)} assessments and {len(work_orders)} work orders")

        client = OpenAI()
        
        # Check for existing vector store with same name
        vector_store_name = f"{newton_path['tenantIdentifier']}_{newton_path['facilityScenarioId']}_assessments"
        try:
            # List all vector stores and find one with matching name
            vector_stores = client.beta.vector_stores.list()
            existing_store = next(
                (vs for vs in vector_stores.data if vs.name == vector_store_name),
                None
            )
            
            if existing_store:
                logger.info(f"Found existing vector store: {existing_store.id}")
                vector_store_id = existing_store.id
            else:
                logger.info("Vector store not found, creating new one")
                vector_store = client.beta.vector_stores.create(
                    name=vector_store_name
                )
                vector_store_id = vector_store.id
                logger.info(f"Created new vector store with ID: {vector_store_id}")
            
            logger.info(f"Using vector store with ID: {vector_store_id}")
        except Exception as e:
            logger.error(f"Error managing vector store: {str(e)}")
            raise
        
        # Upload assessments
        success = await upload_assessments_to_vector_store(
            client=client,
            vector_store_id=vector_store_id,
            filepaths=filepaths
        )
        
        if not success:
            logger.error("Failed to upload assessments")
            raise Exception("File upload failed")
        
        logger.info("File upload process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in upload process: {str(e)}")
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

