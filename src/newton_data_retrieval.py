import newton_api_utils
from folder_structure_manager import FolderStructureManager
import requests
import json
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm
import pandas as pd
import os
import numpy as np
import time
import uuid
import datetime
import asyncio
import aiohttp
from icecream import ic
import logging

logger = logging.getLogger(__name__)

class NewtonDataRetriever:
    """
    Class to retrieve and process data from the Newton API.
    Handles authentication, data retrieval, caching, and folder structure management.
    """

    def __init__(self, newton_path, use_local_cache=True):
        """
        Initializes the NewtonDataRetriever with the provided path and caching preferences.

        Args:
            newton_path (dict): Dictionary containing tenant identifier, scenario ID, and auth header.
            use_local_cache (bool): Flag to determine whether to use local caching. Defaults to True.
        """
        self.BASE_URL = 'https://newton.pinnacletech.com'
        self.newton_path = newton_path
        self.use_local_cache = use_local_cache
        self.tenant_identifier, self.scenario_id, self.auth_header = self.deconstruct_newton_path()
        self.folder_structure_manager = FolderStructureManager(self.newton_path)
        self.filepaths = self.folder_structure_manager.filepaths
        self.session = None  # Placeholder for aiohttp session

    def deconstruct_newton_path(self):
        """
        Extracts tenant identifier, scenario ID, and auth header from the newton_path.

        Returns:
            tuple: Contains tenant identifier (str), scenario ID (int), and auth header (dict).
        """
        tenant_identifier = self.newton_path['tenantIdentifier']
        scenario_id = int(self.newton_path['facilityScenarioId'])
        auth_header = self.newton_path['authHeader']
        return tenant_identifier, scenario_id, auth_header

    def get_active_assessment_list(self):
        """
        Retrieves the list of active assessments for the current scenario.

        Returns:
            list: List of cleaned assessment dictionaries.
        """
        url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/assessment'
        response = requests.get(url, headers=self.auth_header)
        assessments = response.json().get('data', [])

        # Filter out inactive assessments
        #assessments = [assessment for assessment in assessments if assessment.get('isActiveForRiskAnalysis')] #TODO: Uncomment this line when we have active assessments

        assessment_list = []
        for assessment in assessments:
            if assessment['lostProductionImpactPercent'] is None:
                # Default value assignment; TODO indicates uncertainty
                assessment['lostProductionImpactPercent'] = 1.0

            # Clean and extract relevant assessment fields
            assessment_cleaned = {
                'id': assessment['id'],
                'areaClientId': assessment.get('areaClientId'),
                'unitClientId': assessment.get('unitClientId'),
                'unitId': assessment.get('unitId'),
                'systemClientId': assessment.get('systemClientId'),
                'subSystemClientId': assessment.get('subSystemClientId'),
                'assetClientId': assessment.get('assetClientId'),
                'assetName': assessment.get('assetName'),
                'assetId': assessment.get('assetId'),
                'componentClientId': assessment.get('componentClientId'),
                'componentName': assessment.get('componentName'),
                'componentId': assessment.get('componentId'),
                'lostProductionImpactPercent': assessment.get('lostProductionImpactPercent'),
                'predictedFailureDate': assessment.get('predictedFailureDate'),
                'inServiceDate': assessment.get('inServiceDate'),
            }
            assessment_list.append(assessment_cleaned)

        return assessment_list

    async def get_raw_record(self, session, record_id, record_type):
        """
        Asynchronously retrieves a raw record from the API with retry logic.

        Args:
            session (aiohttp.ClientSession): The aiohttp session to use for the request.
            record_id (str): The ID of the record to retrieve.
            record_type (str): The type of the record (e.g., 'task', 'assessment').

        Returns:
            dict: The raw record data in JSON format.

        Raises:
            Exception: If all retry attempts fail.
        """
        url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/{record_type}/{record_id}'
        max_retries = 3
        backoff_factor = 2
        delay = 1  # initial delay in seconds

        if record_type == 'lvc':
            url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/assessment/readassessmentlvcresult?componentId={record_id}'

        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(url, headers=self.auth_header) as response:
                    response.raise_for_status()  # Raise an exception for HTTP errors
                    raw_record = await response.json()
                    if record_type == 'lvc':
                        raw_record = raw_record[0]
                    return raw_record
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == max_retries:
                    print(f"Attempt {attempt} failed. No more retries left.")
                    raise Exception(f"Failed to retrieve record {record_id} after {max_retries} attempts.") from e
                else:
                    print(f"Attempt {attempt} failed with error: {e}. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    delay *= backoff_factor  # Exponential backoff


    async def get_raw_records(self, record_list, record_type, filename=None):
        """
        Retrieves raw records from the API, utilizing caching if enabled.

        Args:
            record_list (list): List of records to retrieve.
            record_type (str): The type of records (e.g., 'task', 'assessment').
            convert_note (bool): Flag to determine whether to convert 'note' fields. Defaults to True.

        Returns:
            list: List of raw record dictionaries.
        """
        if filename is None:
            filename = f'{record_type}s'
        filename = f'{filename}.json'

        # Initialize raw_records list
        raw_records = []
        file_path = os.path.join(self.filepaths['raw_data'], filename)

        # Load cached data if available and caching is enabled
        if self.use_local_cache and os.path.exists(file_path):
            with open(file_path, 'r') as f:
                raw_records = json.load(f)
        else:
            pass  # raw_records remains an empty list

        # Determine which records need to be fetched (not in cache)
        if record_type != 'lvc':
            records_to_get = [record for record in record_list if record['id'] not in [r['id'] for r in raw_records]]
        else:
            records_to_get = record_list

        task_definitions_dict = {}
        if record_type == 'task':
            # Retrieve task definitions for tasks
            url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/facilitytaskdefinition'
            response = requests.get(url, headers=self.auth_header)
            task_definitions = response.json().get('data', [])
            task_definitions_dict = {definition['id']: definition for definition in task_definitions}
        
        

        # Asynchronously fetch raw records
        async with aiohttp.ClientSession() as session:
            tasks = [self.get_raw_record(session, record['id'], record_type) for record in records_to_get]

            new_records = []
            for task in async_tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"Getting raw {record_type}s", dynamic_ncols=True):
                try:
                    raw_record = await task
                    if record_type == 'task':
                        # Populate 'note' from task definitions if missing
                        if raw_record.get('note') is None:
                            task_definition = task_definitions_dict.get(raw_record.get('taskDefinitionId'))
                            if task_definition:
                                raw_record['note'] = task_definition.get('comment')
                    new_records.append(raw_record)
                except Exception as e:
                    print(f"Error processing record: {e}")
                    continue

            # Append newly fetched records to raw_records
            raw_records.extend(new_records)

        # Save the updated raw records to cache
        with open(file_path, 'w') as f:
            json.dump(raw_records, f, indent=4)

        return raw_records

    def delete_raw_data(self):
        """
        Deletes cached raw data files for specified record types.

        Args:
            record_types (list): List of record types to delete (e.g., ['assessment', 'task']).
        """
        filepath = self.filepaths['raw_data']
        files = os.listdir(filepath)
        for file in files:
            os.remove(os.path.join(filepath, file))

    async def get_raw_data(self):
        """
        Orchestrates the retrieval of all raw data, including assessments, tasks, PoF curves, and CoFs.

        Returns:
            tuple: Contains lists and dictionaries of retrieved data.
        """
        if not self.use_local_cache:
            self.delete_raw_data()

        # Retrieve active assessments
        assessments = self.get_active_assessment_list()

        

        # Asynchronously fetch raw assessments and tasks
        raw_assessments = await self.get_raw_records(assessments, 'assessment')

        self.raw_data = {
            'assessments': raw_assessments,
        }

        # Return all retrieved data
        return self.raw_data

    async def retrieve_raw_data(self):
        """
        Initiates the asynchronous retrieval of raw data.
        """
        try:
            if not self.use_local_cache:
                self.delete_raw_data()
            url = f'{self.BASE_URL}/{self.tenant_identifier}/api/scenario/{self.scenario_id}/task'
            response = requests.get(url, headers=self.auth_header)
            tasks = response.json().get('data', [])
            tasks = [task for task in tasks if task['implementationStatus'] == 4]

            # Retrieve active assessments
            assessments = self.get_active_assessment_list()
            
            # Asynchronously fetch raw data
            raw_assessments = await self.get_raw_records(assessments, 'assessment')
            tasks = await self.get_raw_records(tasks, 'task')

            self.raw_data = {
                'assessments': raw_assessments,
                'tasks': tasks,
            }

            return self.raw_data
            
        except Exception as e:
            logger.error(f"Error retrieving raw data: {str(e)}")
            raise
    


# Example usage
if __name__ == '__main__':
    USER_ID = '4c453411-6d39-4704-81d0-ac09014d83eb'
    auth_header = newton_api_utils.build_api_header(USER_ID)
    newton_path = {
        'tenantIdentifier': 'westfraser',
        'facilityScenarioId': 47648651,
        'authHeader': auth_header
    }

    data_retriever = NewtonDataRetriever(newton_path, use_local_cache=False)
    raw_data = asyncio.run(data_retriever.retrieve_raw_data())
