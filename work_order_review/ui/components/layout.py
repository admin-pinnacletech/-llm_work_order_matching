import streamlit as st

def render_header():
    """Render the persistent header in sidebar if scenario is selected"""
    # Create a container at the top of the sidebar
    header_container = st.sidebar.container()
    
    # Update header if we have an active scenario
    if all(key in st.session_state for key in ['tenant_name', 'facility_name', 'scenario_name']):
        header_container.markdown(
            f"""<div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 1rem; font-size: 0.9em;'>
                <b>Current Scenario:</b><br/>
                {st.session_state.tenant_name}<br/>
                {st.session_state.facility_name}<br/>
                {st.session_state.scenario_name}
            </div>""",
            unsafe_allow_html=True
        )