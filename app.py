import streamlit as st
from work_order_review.ui.pages.scenario_select_page import render_scenario_select
from work_order_review.ui.pages.assessment_import_page import render_assessment_import
from work_order_review.ui.pages.vector_store_update_page import render_vector_store_update
from work_order_review.ui.pages.scenarios_page import render_scenarios
from work_order_review.ui.pages.work_order_upload_page import render_work_order_upload
from work_order_review.ui.pages.work_order_matching_page import render_work_order_matching
from work_order_review.ui.pages.work_order_review_page import render_work_order_review
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress SQLAlchemy logging
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

async def main():
    try:
        st.set_page_config(page_title="Work Order Review", layout="wide")
        
        # Add pages to sidebar
        pages = {
            'Add Scenario': render_scenarios,
            "Select Scenario": render_scenario_select,
            "Import Assessments": render_assessment_import,
            "Update Vector Store": render_vector_store_update,
            "Upload Work Orders": render_work_order_upload,
            "Match Work Orders": render_work_order_matching,
            "Review Matches": render_work_order_review
        }
        
        # Sidebar navigation
        st.sidebar.title("Navigation")
        
        # Show scenario info if selected
        if all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
            st.sidebar.success(f"""
                **Current Scenario**
                - Tenant: {st.session_state.get('tenant_name', st.session_state.tenant_id)}
                - Facility: {st.session_state.get('facility_name', '')}
                - Scenario: {st.session_state.get('scenario_name', st.session_state.scenario_id)}
            """)
        
        # Always show all pages
        available_pages = list(pages.keys())
        
        # Get current selection
        current_page = st.session_state.get('current_page', 'Select Scenario')
        if current_page not in available_pages:
            current_page = 'Select Scenario'
            st.session_state.current_page = current_page
            
        # Update selection with radio button
        selection = st.sidebar.radio(
            "Go to",
            options=available_pages,
            index=available_pages.index(current_page)
        )
        
        if selection != current_page:
            st.session_state.current_page = selection
            st.rerun()
        
        logger.info(f"Selected page: {selection}")
        
        # Render selected page
        await pages[selection]()
        
        # Show overlay if no scenario selected and not on scenario pages
        if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
            if selection not in ['Add Scenario', 'Select Scenario']:
                with st.container():
                    st.markdown(
                        """
                        <div style='position: fixed; top: 0; left: 0; right: 0; bottom: 0; 
                                background-color: rgba(0,0,0,0.7); z-index: 1000; 
                                display: flex; justify-content: center; align-items: center;'>
                            <div style='background-color: white; padding: 2rem; border-radius: 10px; 
                                    max-width: 500px; text-align: center;'>
                                <h2>Please Select a Scenario</h2>
                                <p>You need to select a scenario before using this page.</p>
                                <p>Go to <b>Select Scenario</b> in the navigation menu to choose one.</p>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
        st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except Exception as e:
        st.error(f"Application error: {str(e)}")
    finally:
        loop.close()