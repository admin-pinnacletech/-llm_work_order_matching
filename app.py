import streamlit as st
import asyncio
from datetime import datetime
from work_order_review.pages.scenario_manager import ScenarioManager

def validate_inputs(tenant_identifier: str, scenario_id: str) -> tuple[bool, str]:
    """Validate input formats before making API calls"""
    if not tenant_identifier:
        return False, "Tenant identifier is required"
    if not tenant_identifier.isalnum():
        return False, "Tenant identifier must be alphanumeric"
    
    if not scenario_id:
        return False, "Scenario ID is required"
    try:
        scenario_int = int(scenario_id)
        if scenario_int <= 0:
            return False, "Scenario ID must be a positive number"
    except ValueError:
        return False, "Scenario ID must be a number"
    
    return True, ""

async def main():
    st.title("Newton Data Import")
    
    # Initialize scenario manager
    scenario_manager = ScenarioManager()
    
    # Run duplicate cleanup on startup
    cleanup_count = await scenario_manager.cleanup_duplicates()
    if cleanup_count > 0:
        st.toast(f"Cleaned up {cleanup_count} duplicate scenarios")
    
    # Create two main sections with tabs
    tab1, tab2 = st.tabs(["Create New Scenario", "Select Existing"])
    
    with tab1:
        # Clean form with proper spacing and help text
        with st.form("new_scenario_form", border=True):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                tenant_identifier = st.text_input(
                    "Tenant Identifier",
                    placeholder="Enter tenant ID",
                    help="The alphanumeric identifier for your tenant"
                )
                
                scenario_id = st.text_input(
                    "Scenario ID",
                    placeholder="Enter scenario ID",
                    help="Numeric ID for the new scenario"
                )
            
            submitted = st.form_submit_button(
                "Create Scenario", 
                type="primary",
                use_container_width=True
            )
            
            if submitted:
                # Validate inputs
                is_valid, error_message = validate_inputs(tenant_identifier, scenario_id)
                
                if is_valid:
                    with st.spinner("Creating scenario..."):
                        try:
                            # Get scenario data
                            scenario_data = await scenario_manager.get_scenario_data(tenant_identifier, scenario_id)
                            
                            if scenario_data:
                                st.success("Scenario created successfully!")
                                # Force refresh of all picklists
                                st.session_state.refresh_data = True
                                st.rerun()
                            else:
                                st.error("Failed to create scenario. Please check the inputs and try again.")
                        except Exception as e:
                            st.error(f"Error creating scenario: {str(e)}")
                else:
                    st.error(error_message)
    
    with tab2:
        # Initialize or refresh tenant list
        if 'tenant_list' not in st.session_state or st.session_state.get('refresh_data'):
            st.session_state.tenant_list = await scenario_manager.get_tenants()
            st.session_state.refresh_data = False
        
        # Create three equal columns for selection
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("#### 1. Select Tenant")
            tenant_names = [t['name'] for t in st.session_state.tenant_list]
            selected_tenant_name = st.selectbox(
                "Select Tenant",
                options=tenant_names if tenant_names else ["No tenants available"],
                key='selected_tenant_name',
                label_visibility="collapsed"
            )
        
        with col2:
            if selected_tenant_name and selected_tenant_name != "No tenants available":
                st.write("#### 2. Select Facility")
                # Get selected tenant ID
                selected_tenant = next(t for t in st.session_state.tenant_list if t['name'] == selected_tenant_name)
                
                # Get facilities for selected tenant
                if ('facility_list' not in st.session_state or 
                    st.session_state.get('refresh_data') or 
                    st.session_state.get('last_tenant_id') != selected_tenant['id']):
                    st.session_state.facility_list = await scenario_manager.get_facilities(selected_tenant['id'])
                    st.session_state.last_tenant_id = selected_tenant['id']
                
                facility_names = [f['name'] for f in st.session_state.facility_list]
                selected_facility_name = st.selectbox(
                    "Select Facility",
                    options=facility_names if facility_names else ["No facilities available"],
                    key='selected_facility_name',
                    label_visibility="collapsed"
                )
        
        with col3:
            if selected_facility_name and selected_facility_name != "No facilities available":
                st.write("#### 3. Select Scenario")
                # Get selected facility ID
                selected_facility = next(f for f in st.session_state.facility_list if f['name'] == selected_facility_name)
                
                # Get scenarios for selected facility
                if ('scenario_list' not in st.session_state or 
                    st.session_state.get('refresh_data') or 
                    st.session_state.get('last_facility_id') != selected_facility['id']):
                    st.session_state.scenario_list = await scenario_manager.get_scenarios(
                        selected_tenant['id'],
                        selected_facility['id']
                    )
                    st.session_state.last_facility_id = selected_facility['id']
                
                scenario_names = [s['name'] for s in st.session_state.scenario_list]
                selected_scenario_name = st.selectbox(
                    "Select Scenario",
                    options=scenario_names if scenario_names else ["No scenarios available"],
                    key='selected_scenario_name',
                    label_visibility="collapsed"
                )
    
        # Only show summary and import button when all selections are made
        if (selected_tenant_name and selected_facility_name and selected_scenario_name and 
            all(x != "No scenarios available" for x in [selected_tenant_name, selected_facility_name, selected_scenario_name])):
            
            st.divider()
            
            # Create columns for summary and action
            sum_col, btn_col = st.columns([2, 1])
            
            with sum_col:
                st.info(
                    "**Ready to Import:**\n\n"
                    f"**Scenario:** {selected_scenario_name}\n"
                    f"**Facility:** {selected_facility_name}\n"
                    f"**Tenant:** {selected_tenant_name}"
                )
            
            with btn_col:
                st.write("")  # Add spacing
                st.write("")  # Add spacing
                if st.button("Import Data", type="primary", use_container_width=True):
                    with st.spinner("Importing scenario data..."):
                        # Your existing import logic here
                        pass

if __name__ == "__main__":
    asyncio.run(main()) 