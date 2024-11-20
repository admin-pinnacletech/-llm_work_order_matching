import newton_api_utils
from folder_structure_manager import FolderStructureManager
from newton_data_retrieval import NewtonDataRetriever

import requests
import json
from tqdm import tqdm
from scipy.stats import weibull_min
import pandas as pd
import os
import surpyval as surv
import numpy as np
from icecream import ic
from dotenv import load_dotenv
from openai import OpenAI
import shutil
import datetime
import logging
import datetime

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatters and add it to handlers
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)

# Add handlers to the logger
logger.addHandler(console_handler)

class PreProcessor:
    def __init__(self, newton_path, raw_data, filepaths):
        """Initialize PreProcessor with newton path and raw data."""
        self.newton_path = newton_path
        self.raw_data = raw_data
        self.filepaths = filepaths
        self.pre_processed_data = {
            'workOrders': [],
            'assessments': []
        }
        
        self.manual_data_path = os.path.join(
            os.getenv('MANUAL_DATA_DIR', ''),
            'CMMS Final Combined.xlsx'
        )
        logger.info(f"PreProcessor initialized for tenant {newton_path['tenantIdentifier']}")

    def read_manual_data(self):
        """Read manual data from Excel file."""
        try:
            manual_data_path = self.filepaths['raw_data_manual']
            logger.info(f"Reading manual data from {manual_data_path}")
            
            # Check if directory exists
            directory = os.path.dirname(manual_data_path)
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            # Check if file exists
            if not os.path.exists(manual_data_path):
                raise FileNotFoundError(
                    f"Manual data file not found at {manual_data_path}. "
                    "Please ensure the Excel file is placed in the correct location."
                )
            
            # Try to read the file
            try:
                self.raw_data = pd.read_excel(self.manual_data_path)
            except PermissionError:
                raise PermissionError(
                    f"Permission denied when trying to read {manual_data_path}. "
                    "Please ensure the file is not open in another program and you have read permissions."
                )
            
            if self.raw_data.empty:
                raise ValueError("Excel file is empty")
            
        except Exception as e:
            logger.error(f"Error reading manual data: {str(e)}")
            raise

    def jsonify_work_orders(self):
        """Convert work orders to JSON format, including all fields from each row."""
        logger.info("Converting work orders to JSON format")
        try:
            # Get the CMMS sheet which contains work orders
            #raw_data = self.raw_data['manual'].get('CMMS')
            
            if not isinstance(self.raw_data, pd.DataFrame):
                logger.error(f"CMMS sheet not found or empty. Available sheets: {list(self.raw_data['manual'].keys())}")
                return []
                
            logger.info(f"Number of rows in CMMS sheet: {len(self.raw_data)}")
            
            # Process each work order
            work_orders = []
            for index, row in self.raw_data.iterrows():
                # Convert the entire row to a dictionary, handling NaN values
                work_order = {
                    'id': str(index)  # Use row index as ID
                }
                
                for column, value in row.items():
                    # Convert NaN/NaT to None for JSON compatibility
                    if pd.isna(value):
                        work_order[column] = None
                    else:
                        work_order[column] = str(value)
                
                work_orders.append(work_order)
                
            logger.info(f"Processed {len(work_orders)} work orders")
            return work_orders
            
        except Exception as e:
            logger.error(f"Error converting work orders to JSON: {str(e)}")
            raise

    def save_pre_processed_data(self, work_orders, assessments):
        """Save pre-processed data to files in batches."""
        logger.info(f"Saving pre-processed data to {self.filepaths['pre_processed_data']}")
        
        try:
            # Save assessments
            assessment_dir = os.path.join(self.filepaths['pre_processed_data'], 'assessments')
            os.makedirs(assessment_dir, exist_ok=True)
            for assessment in assessments:
                filename = f"assessment_{assessment['id']}.json"
                with open(os.path.join(assessment_dir, filename), 'w') as f:
                    json.dump(assessment, f)

            # Save work orders in batches
            work_order_dir = os.path.join(self.filepaths['pre_processed_data'], 'work_orders')
            os.makedirs(work_order_dir, exist_ok=True)
            
            BATCH_SIZE = 1000
            for i in range(0, len(work_orders), BATCH_SIZE):
                batch = work_orders[i:i + BATCH_SIZE]
                batch_num = i // BATCH_SIZE
                filename = f"work_orders_batch_{batch_num}.json"
                
                logger.info(f"Saving batch {batch_num} ({len(batch)} work orders)")
                with open(os.path.join(work_order_dir, filename), 'w') as f:
                    json.dump(batch, f)

            # Save metadata
            metadata = {
                'timestamp': datetime.datetime.now().isoformat(),
                'total_work_orders': len(work_orders),
                'total_assessments': len(assessments),
                'num_work_order_batches': (len(work_orders) + BATCH_SIZE - 1) // BATCH_SIZE
            }
            
            with open(os.path.join(self.filepaths['pre_processed_data'], 'metadata.json'), 'w') as f:
                json.dump(metadata, f)

            return True

        except Exception as e:
            logger.error(f"Error saving pre-processed data: {str(e)}")
            return False

    def convert_timestamps(self, data):
        """Convert all timestamps/datetimes to ISO format strings."""
        if isinstance(data, dict):
            return {k: self.convert_timestamps(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.convert_timestamps(item) for item in data]
        elif isinstance(data, (pd.Timestamp, datetime.datetime)):
            return data.isoformat()
        else:
            return data

    def pre_process(self):  # Remove async
        """Pre-process the raw data."""
        try:
            logger.info("Starting pre-processing workflow")
            
            # Read and process manual data
            self.read_manual_data()  # This is synchronous
            
            # Process work orders and assessments
            work_orders = self.jsonify_work_orders()
            assessments = self.raw_data.get('assessments', [])
            
            # Just pass through the work orders as-is
            formatted_work_orders = []
            for wo in work_orders:
                # Convert all values to strings to ensure consistency
                formatted_wo = {k: str(v) if v is not None else "" for k, v in wo.items()}
                formatted_work_orders.append(formatted_wo)

            logger.info(f"Processed {len(formatted_work_orders)} work orders")
            
            # Save the processed data
            self.save_pre_processed_data(formatted_work_orders, assessments)
            
            logger.info("Pre-processing completed successfully")
            return {
                "assessments": assessments,
                "workOrders": formatted_work_orders
            }
            
        except Exception as e:
            logger.error(f"Error in pre-processing: {str(e)}")
            raise
        

    


