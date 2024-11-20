# Work Order Assessment Matching System

A Python-based system for matching maintenance work orders with equipment assessments in an industrial facility.

## Overview

This system processes maintenance work orders and matches them with relevant equipment assessments by analyzing:
- Work order descriptions and identifiers
- Asset names and locations 
- Equipment components and systems
- Repair classifications
- Confidence scoring

## Key Features

- Work order processing and classification
- Assessment data matching
- Repair task identification
- Confidence score calculation
- JSON response formatting
- Batch processing capability

## Requirements
bash
newton-api-utils
openai
python-dotenv
requests
tqdm
icecream
scipy
pandas
surpyval
numpy

## Project Structure

```
├── src/
│   ├── config/
│   │   ├── assistant_config.py      # Assistant configuration
│   │   ├── system_instructions.txt  # System prompts and rules
│   │   └── function_schema.json     # API function definitions
│   ├── pre_processing.py           # Data preprocessing
│   └── wo_matching.py              # Core matching logic
├── data/
│   └── kuraray/
│       └── Current/
│           ├── raw_data/           # Input data
│           └── pre_processed_data/ # Processed data
```

## Key Components

### Pre-Processing
- Reads and formats work order data
- Processes assessment data
- Handles data validation and cleaning
- Manages batch processing

### Work Order Matching
- Analyzes work order descriptions
- Matches with relevant assessments
- Calculates confidence scores
- Classifies repair tasks

### Assistant Configuration
- Manages OpenAI integration
- Handles system prompts
- Configures function schemas
- Updates assistant settings

## Usage

1. Ensure all requirements are installed
2. Configure environment variables
3. Place input data in raw_data directory
4. Run preprocessing:
```python
python src/pre_processing.py
```
5. Execute matching:
```python
python src/wo_matching.py
```

## Response Format

The system returns JSON responses in the following format:
```json
{
    "work_order": {
        "id": "string",
        "description": "string"
    },
    "assessments": [{
        "assessment_id": "uuid string",
        "asset_client_id": "string",
        "asset_name": "string",
        "component": "string",
        "confidence_score": "number between 0-1",
        "reasoning": "string"
    }],
    "repair_classification": {
        "is_repair": "boolean",
        "reasoning": "string"
    }
}
```

## Error Handling

For large requests, the system returns:
```json
{
    "status": "retry",
    "reason": "string",
    "suggested_batch_size": "number"
}
```