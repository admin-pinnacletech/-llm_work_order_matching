import streamlit as st
import pandas as pd
from typing import List, Dict, Tuple
from work_order_review.database.models import WorkOrder

def get_field_type(df: pd.DataFrame, field: str) -> str:
    """Determine the type of filter to use based on field data"""
    if field not in df.columns:
        return "text"
    
    dtype = df[field].dtype
    if pd.api.types.is_numeric_dtype(dtype):
        return "numeric"
    elif pd.api.types.is_datetime64_dtype(dtype):
        return "datetime"
    elif df[field].nunique() < 25:
        return "categorical"
    else:
        return "text"

def apply_filter(df: pd.DataFrame, field: str, operator: str, value: str) -> pd.DataFrame:
    """Apply a single filter to the dataframe"""
    if field not in df.columns:
        return df
        
    field_type = get_field_type(df, field)
    
    try:
        if field_type == "numeric":
            value = float(value)
            if operator == "equals":
                return df[df[field] == value]
            elif operator == "greater than":
                return df[df[field] > value]
            elif operator == "less than":
                return df[df[field] < value]
            elif operator == "contains":
                return df[df[field].astype(str).str.contains(str(value), case=False)]
        elif field_type == "categorical":
            return df[df[field] == value]
        else:
            if operator == "equals":
                return df[df[field].astype(str).eq(str(value))]
            elif operator == "contains":
                return df[df[field].astype(str).str.contains(str(value), case=False)]
            elif operator == "starts with":
                return df[df[field].astype(str).str.startswith(str(value), na=False)]
            elif operator == "ends with":
                return df[df[field].astype(str).str.endswith(str(value), na=False)]
    except Exception as e:
        st.warning(f"Error applying filter: {str(e)}")
        return df
    
    return df

def render_work_order_table(work_orders: List[WorkOrder]) -> Tuple[pd.DataFrame, List[WorkOrder]]:
    """Render a table of work orders with selection checkboxes and dynamic filtering."""
    # Convert work orders to DataFrame
    data = []
    work_order_map = {}  # Map to track DataFrame rows to WorkOrder objects
    for wo in work_orders:
        row = {
            'select': False,
            'id': wo.id,
            'tenant_id': wo.tenant_id,
            'facility_scenario_id': wo.facility_scenario_id,
            'external_id': wo.external_id,
            'status': wo.status,  # Ensure status is pulled from the WorkOrder object
            'summary': wo.llm_summary,
            'downtime_hours': wo.llm_downtime_hours,
            'cost': wo.llm_cost,
            'task_type': wo.task_type,
            **wo.raw_data,  # Unpack all raw_data fields
        }
        # Ensure status from WorkOrder object takes precedence
        row['status'] = wo.status
        data.append(row)
        work_order_map[len(data) - 1] = wo
    
    df = pd.DataFrame(data)
    df = df[df['tenant_id'] == st.session_state.tenant_id]
    df = df[df['facility_scenario_id'] == st.session_state.scenario_id]
    
    # Move important columns to the front
    front_columns = ['select', 'id', 'external_id', 'status', 'summary', 'downtime_hours', 'cost', 'task_type']
    other_columns = [col for col in df.columns if col not in front_columns]
    df = df[front_columns + other_columns]
    
    # Initialize or restore selections from session state
    if 'table_selections' not in st.session_state:
        st.session_state.table_selections = {}
    
    # Apply stored selections to DataFrame
    for i, row in df.iterrows():
        wo_id = str(work_order_map[i].id)
        if wo_id in st.session_state.table_selections:
            df.at[i, 'select'] = st.session_state.table_selections[wo_id]
    
    # Get all possible fields for filtering
    all_fields = sorted(df.columns.tolist())
    all_fields.remove('select')  # Remove the selection checkbox field
    
    # Initialize filters in session state if not present
    if 'filters' not in st.session_state:
        st.session_state.filters = []
    
    # Filter controls
    with st.expander("Filter Work Orders", expanded=True):
        # Add new filter button
        col1, col2 = st.columns([6, 1])
        with col1:
            if st.button("Add Filter"):
                st.session_state.filters.append({
                    'field': all_fields[0],
                    'operator': 'contains',
                    'value': ''
                })
        
        # Render existing filters
        filters_to_remove = []
        for i, filter_dict in enumerate(st.session_state.filters):
            col1, col2, col3, col4 = st.columns([3, 2, 3, 1])
            
            with col1:
                field = st.selectbox(
                    "Field",
                    all_fields,
                    key=f"field_{i}",
                    index=all_fields.index(filter_dict['field'])
                )
            
            with col2:
                field_type = get_field_type(df, field)
                if field_type == "numeric":
                    operators = ["equals", "greater than", "less than", "contains"]
                else:
                    operators = ["contains", "equals", "starts with", "ends with"]
                
                operator = st.selectbox(
                    "Operator",
                    operators,
                    key=f"operator_{i}",
                    index=operators.index(filter_dict['operator'])
                )
            
            with col3:
                if field_type == "categorical":
                    try:
                        value = st.selectbox(
                            "Value",
                            df[field].unique(),
                            key=f"value_{i}",
                            index=df[field].unique().tolist().index(filter_dict['value'])
                        )
                    except ValueError:
                        value = st.selectbox(
                            "Value",
                            df[field].unique(),
                            key=f"value_{i}",
                            index=0
                        )
                else:
                    value = st.text_input(
                        "Value",
                        key=f"value_{i}",
                        value=filter_dict['value']
                    )
            
            with col4:
                if st.button("❌", key=f"remove_{i}"):
                    filters_to_remove.append(i)
            
            # Update filter in session state
            st.session_state.filters[i] = {
                'field': field,
                'operator': operator,
                'value': value
            }
        
        # Remove marked filters
        for i in reversed(filters_to_remove):
            st.session_state.filters.pop(i)
    
    # Apply all filters
    filtered_df = df.copy()
    for filter_dict in st.session_state.filters:
        if filter_dict['value']:  # Only apply if value is not empty
            filtered_df = apply_filter(
                filtered_df,
                filter_dict['field'],
                filter_dict['operator'],
                filter_dict['value']
            )
    
    # Show row count and select all button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Showing {len(filtered_df)} of {len(df)} work orders")
    with col2:
        if st.button("Select All Filtered"):
            filtered_df['select'] = True
    
    # Create the editable dataframe
    edited_df = st.data_editor(
        filtered_df,
        column_config={
            "select": st.column_config.CheckboxColumn(
                "Select",
                help="Select work orders to process",
                default=False,
            ),
            "id": st.column_config.TextColumn(
                "ID",
                help="Work Order ID",
                width="medium",
            ),
            "external_id": st.column_config.TextColumn(
                "External ID",
                help="External Work Order ID",
                width="medium",
            ),
            "description": st.column_config.TextColumn(
                "Description",
                help="Work Order Description",
                width="large",
            ),
            "status": st.column_config.TextColumn(
                "Status",
                help="Work Order Status",
                width="small",
            ),
            "llm_summary": st.column_config.TextColumn(
                "AI Summary",
                help="AI-Generated Summary",
                width="large",
            ),
        },
        hide_index=True,
        key="work_order_table"
    )
    
    # Store selections in session state
    for i, row in edited_df.iterrows():
        wo_id = str(work_order_map[i].id)
        st.session_state.table_selections[wo_id] = bool(row['select'])
    
    # Get selected work orders
    selected_indices = edited_df.index[edited_df['select']].tolist()
    selected_work_orders = [work_order_map[i] for i in selected_indices]
    
    return edited_df, selected_work_orders