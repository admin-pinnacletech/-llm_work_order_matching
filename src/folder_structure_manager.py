import newton_api_utils
import requests
import json
import os
import time

class FolderStructureManager:
    BASE_URL = 'https://newton.pinnacletech.com'
    def __init__(self, newton_path):
        self.newton_path = newton_path
        self.tenant_identifier, self.scenario_id, self.auth_header = self.deconstruct_newton_path()
        self.filepaths = self.build_folders()
        

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

    def build_folders(self):
        """
        Creates the necessary folder structure for storing retrieved data.

        Returns:
            dict: Dictionary containing paths to raw_data, pre_processed_data, algorithm_outputs, and post_processed_data.
        """
        tenant_identifier, scenario_id, auth_header = self.tenant_identifier, self.scenario_id, self.auth_header
        url = f'{self.BASE_URL}/{tenant_identifier}/api/scenario/{scenario_id}/scenariomanager'
        max_retries = 5
        retry_delay = 1  # seconds

        # Attempt to retrieve scenario manager data with retries
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=auth_header, timeout=10)
                response.raise_for_status()  # Raises an HTTPError for bad responses
                scenario_manager = response.json().get('data', [])
                break  # Exit loop if successful
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                if attempt == max_retries - 1:
                    print(f"Failed to retrieve scenario manager after {max_retries} attempts: {e}")
                    scenario_manager = []  # Use empty list if all retries fail
                else:
                    print(f"Attempt {attempt + 1} failed. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

        # Filter scenarios to match the current scenario ID
        filtered_scenarios = [scenario for scenario in scenario_manager if scenario['id'] == scenario_id]
        if len(filtered_scenarios) == 0:
            filtered_scenario = {
                'id': scenario_id,
                'name': 'Current'
            }
        else:
            filtered_scenario = filtered_scenarios[0]

        def create_folder_structure(base_path, folder_structure):
            """
            Recursively creates folders based on the provided structure.

            Args:
                base_path (str): The base directory path.
                folder_structure (dict): Nested dictionary defining folder hierarchy.

            Returns:
                list: List of created folder paths.
            """
            def create_folders(base, structure):
                paths = []
                for name, sub_structure in structure.items():
                    path = os.path.join(base, name)
                    os.makedirs(path, exist_ok=True)
                    if isinstance(sub_structure, dict) and sub_structure:
                        paths.extend(create_folders(path, sub_structure))
                    else:
                        paths.append(path)
                return paths

            return create_folders(base_path, folder_structure)

        # Define the folder structure based on tenant and scenario
        folder_structure = {
            'data': {
                tenant_identifier: {
                    filtered_scenario['name']: {
                        'raw_data': {},
                        'raw_data_manual': {},
                        'pre_processed_data': {},
                        'algorithm_outputs': {},
                        'post_processed_data': {},
                    }
                }
            }
        }

        # Set the base path to one level above where this file is located
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Create the folder structure and map the paths
        paths = create_folder_structure(base_path, folder_structure)
        filepaths = {
            'raw_data': paths[0],
            'raw_data_manual': paths[1],
            'pre_processed_data': paths[2],
            'algorithm_outputs': paths[3],
            'post_processed_data': paths[4]
        }

        return filepaths