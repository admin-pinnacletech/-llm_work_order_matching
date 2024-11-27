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

async def render_scenario_select():
    st.title("Select Scenario")
    render_header()
    
    user_id = os.getenv('USER_ID')
    if not user_id:
        user_id = st.text_input("User ID")
        if not user_id:
            st.error("Please provide your User ID or set USER_ID environment variable")
            return
            
    auth_header = build_api_header(user_id)
    
    async with AsyncSessionLocal() as session:
        service = ScenarioService(session=session, auth_header=auth_header)
        
        # Get list of tenants
        tenants = await service.get_tenants()
        
        # Create a list of tuples (id, display_name) for the selectbox
        tenant_options = [(t['id'], t['name']) for t in tenants]
        
        if tenant_options:
            selected_tenant_tuple = st.selectbox(
                "Select Tenant",
                options=tenant_options,
                format_func=lambda x: x[1],  # Display the name (second element of tuple)
            )
            
            if selected_tenant_tuple:
                selected_tenant = selected_tenant_tuple[0]  # Use the ID (first element of tuple)
                
                # Get facilities for selected tenant
                facilities = await service.get_facilities(selected_tenant)
                selected_facility = st.selectbox(
                    "Select Facility",
                    options=[f['id'] for f in facilities],
                    format_func=lambda x: next((f['name'] for f in facilities if f['id'] == x), x)
                )
                
                if selected_facility:
                    # Get scenarios for selected facility
                    scenarios = await service.get_scenarios(selected_tenant, selected_facility)
                    selected_scenario = st.selectbox(
                        "Select Scenario",
                        options=[s['id'] for s in scenarios],
                        format_func=lambda x: next((s['name'] for s in scenarios if s['id'] == x), x)
                    )
                    
                    if selected_scenario:
                        if st.button("Load Scenario"):
                            # Get the names for display
                            tenant_name = next((t[1] for t in tenant_options if t[0] == selected_tenant), selected_tenant)
                            facility_name = next((f['name'] for f in facilities if f['id'] == selected_facility), selected_facility)
                            scenario_name = next((s['name'] for s in scenarios if s['id'] == selected_scenario), selected_scenario)
                            
                            st.session_state.tenant_id = selected_tenant
                            st.session_state.facility_id = selected_facility
                            st.session_state.scenario_id = selected_scenario
                            st.session_state.tenant_name = tenant_name
                            st.session_state.facility_name = facility_name
                            st.session_state.scenario_name = scenario_name
                            
                            st.success("Scenario selected!")
        else:
            st.warning("No tenants found. Please import a scenario first.")