import logging
import qc_review.newton_api_utils as newton_api_utils
from src.folder_structure_manager import FolderStructureManager
from qc_review.newton_data_retrieval import NewtonDataRetriever
from llm_work_order_matching.data_processor.services import PreProcessor

import json
import os
from datetime import datetime
from typing import Dict, List
from pathlib import Path
from icecream import ic
from tqdm import tqdm
import csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResultsMerger:
    def __init__(self, newton_path: Dict, filename: str):
        self.newton_path = newton_path
        folder_structure_manager = FolderStructureManager(newton_path)
        self.filepaths = folder_structure_manager.build_folders()
        self.filename = filename

    def get_results(self):
        with open(os.path.join(self.filepaths['algorithm_outputs'], self.filename), 'r') as f:
            self.results = json.load(f)

    def load_work_orders(self):
        """Load all work orders from JSON files in the work_orders directory."""
        work_orders = []
        work_orders_path = os.path.join(self.filepaths['pre_processed_data'], 'work_orders')
        
        # Single loop to both find and load JSON files
        for file in os.listdir(work_orders_path):
            if file.endswith('.json'):
                with open(os.path.join(work_orders_path, file), 'r') as f:
                    data = json.load(f)
                    # If data is a list, extend work_orders with all items
                    if isinstance(data, list):
                        work_orders.extend(data)
                    else:
                        work_orders.append(data)
        
        print(f"Total work orders loaded: {len(work_orders)}")
        self.work_orders = work_orders
        return work_orders
    
    def merge_results(self):
        # Add debugging to check data structure
        print("Type of self.results:", type(self.results))
        print("Keys in results:", list(self.results.keys()))
        
        # Get the actual results array from the nested structure
        results_array = self.results.get('results', [])
        print("Number of results to process:", len(results_array))
        
        # Flatten work orders if they're in batches
        flattened_work_orders = []
        for wo in self.work_orders:
            if isinstance(wo, list):
                flattened_work_orders.extend(wo)
            else:
                flattened_work_orders.append(wo)
        self.work_orders = flattened_work_orders
        
        print(f"Number of work orders to process: {len(self.work_orders)}")
        
        for work_order in tqdm(self.work_orders, desc="Merging results"):
            # Initialize default values in case no match is found
            work_order['assessments'] = []
            work_order['repair_classification'] = {}
            
            for result_data in results_array:
                # If result_data is a list, get the first item
                if isinstance(result_data, list) and result_data:
                    result_data = result_data[0]
                
                # Skip if result_data doesn't have the expected structure
                if not isinstance(result_data, dict):
                    continue
                    
                # Skip if this result doesn't have a work_order key
                if 'work_order' not in result_data:
                    # If the result_data has an 'id' directly, try to match that
                    if 'id' in result_data and 'description' in result_data:
                        if work_order['id'] == result_data['id']:
                            work_order['assessments'] = result_data.get('assessments', [])
                            work_order['repair_classification'] = result_data.get('repair_classification', {})
                    continue
                
                # Try to match using work_order.id
                if work_order['id'] == result_data['work_order']['id']:
                    work_order['assessments'] = result_data.get('assessments', [])
                    work_order['repair_classification'] = result_data.get('repair_classification', {})
        
        return self.work_orders
    
    def save_results(self):
        """Save processed results in both JSON and CSV formats."""
        # Save JSON with UTF-8 encoding
        with open(os.path.join(self.filepaths['post_processed_data'], 'merged_results.json'), 'w', encoding='utf-8') as f:
            json.dump(self.work_orders, f, indent=4, ensure_ascii=False)
        
        # Save CSV with UTF-8 encoding and BOM (for Excel compatibility)
        with open(os.path.join(self.filepaths['post_processed_data'], 'merged_results.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # Get all possible work order fields from the first work order
            wo_fields = list(self.work_orders[0].keys())
            wo_fields.remove('assessments')  # We'll handle assessments separately
            wo_fields.remove('repair_classification')  # We'll add this at the end
            
            # Write header
            header = wo_fields + [
                'assessment_id',
                'asset_client_id',
                'asset_name',
                'component',
                'confidence_score',
                'reasoning',
                'is_repair',
                'repair_reasoning'
            ]
            writer.writerow(header)
            
            # Write data
            for wo in self.work_orders:
                base_row = [wo.get(field, '') for field in wo_fields]
                repair_class = wo.get('repair_classification', {})
                repair_info = [
                    repair_class.get('is_repair', ''),
                    repair_class.get('reasoning', '')
                ]
                
                # If there are no assessments, write one row with base info
                if not wo.get('assessments'):
                    writer.writerow(base_row + ['', '', '', '', '', ''] + repair_info)
                else:
                    # Write a row for each assessment
                    for assessment in wo['assessments']:
                        assessment_row = [
                            assessment.get('assessment_id', ''),
                            assessment.get('asset_client_id', ''),
                            assessment.get('asset_name', ''),
                            assessment.get('component', ''),
                            assessment.get('confidence_score', ''),
                            assessment.get('reasoning', '')
                        ]
                        writer.writerow(base_row + assessment_row + repair_info)

    def main(self):
        self.get_results()
        self.load_work_orders()
        self.merge_results()
        self.save_results()

if __name__ == '__main__':
    USER_ID = '4c453411-6d39-4704-81d0-ac09014d83eb'
    newton_path = {
        'tenantIdentifier': 'kuraray',
        'facilityScenarioId': 209309816,
        'authHeader': newton_api_utils.build_api_header(USER_ID)
    }
    filename = 'results_20241119_174923.json'
    results_merger = ResultsMerger(newton_path, filename)
    results_merger.main()
