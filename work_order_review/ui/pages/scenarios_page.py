import streamlit as st
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.scenario_service import ScenarioService
from work_order_review.newton_api_utils import build_api_header
from work_order_review.ui.components.layout import render_header
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

async def render_scenarios():
    st.title("Scenario Management")
    
    user_id = os.getenv('USER_ID')
    if not user_id:
        user_id = st.text_input("User ID")
        if not user_id:
            st.error("Please provide your User ID or set USER_ID environment variable")
            return
    
    tenant_id = st.text_input("Tenant ID", value=st.session_state.get('tenant_id', ''))
    scenario_id = st.text_input("Scenario ID", value=st.session_state.get('scenario_id', ''))
    
    if st.button("Import Scenario"):
        await handle_import(tenant_id, scenario_id, user_id)

async def handle_import(tenant_id: str, scenario_id: str, user_id: str):
    if not tenant_id or not scenario_id:
        st.error("Please provide both Tenant ID and Scenario ID")
        return
    
    try:
        auth_header = build_api_header(user_id)
        
        async with AsyncSessionLocal() as session:
            service = ScenarioService(session=session, auth_header=auth_header)
            
            with st.spinner("Importing scenario..."):
                try:
                    success = await service.import_scenario(tenant_id, scenario_id)
                    if success:
                        # Get scenario info for display
                        scenario_info = await service.get_scenario_info(tenant_id, scenario_id)
                        if scenario_info:
                            st.session_state.tenant_id = tenant_id
                            st.session_state.scenario_id = scenario_id
                            st.session_state.tenant_name = scenario_info['tenant_name']
                            st.session_state.facility_name = scenario_info['facility_name']
                            st.session_state.scenario_name = scenario_info['scenario_name']
                            st.success("Scenario imported successfully!")
                        else:
                            st.error("Failed to get scenario information")
                    else:
                        st.error("Failed to import scenario")
                except ValueError as ve:
                    st.error(str(ve))
                    
    except Exception as e:
        logger.error(f"Error importing scenario: {str(e)}")
        st.error(f"Error: {str(e)}")