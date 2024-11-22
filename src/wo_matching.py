import logging
import qc_review.newton_api_utils as newton_api_utils
from src.folder_structure_manager import FolderStructureManager
from qc_review.newton_data_retrieval import NewtonDataRetriever
from llm_work_order_matching.data_processor.services import PreProcessor

import requests
import json
from tqdm import tqdm
from scipy.stats import weibull_min
import pandas as pd
import os
import surpyval as surv
import numpy as np
from icecream import ic

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)

logger.addHandler(console_handler)

if __name__ == "__main__":
    logger.info("Starting work order matching process")
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
        raw_data = data_retriever.retrieve_raw_data()
        logger.info("Raw data retrieved successfully")
        
        pre_processor = PreProcessor(newton_path, raw_data)
        pre_processed_data = pre_processor.pre_process()
        logger.info("Data pre-processing completed")

        assessments = pre_processed_data['assessments']
        work_orders = pre_processed_data['workOrders']
        logger.info(f"Loaded {len(assessments)} assessments and {len(work_orders)} work orders")

        ic(work_orders[42])
        logger.debug("Sample work order printed")
        
    except Exception as e:
        logger.error(f"Error in work order matching process: {str(e)}")
        raise













    
