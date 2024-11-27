import streamlit as st
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.assessment_service import AssessmentService
from work_order_review.newton_api_utils import build_api_header
from work_order_review.ui.components.layout import render_header
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

async def render_assessment_import():
    st.title("Import Assessment Data")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
        
    user_id = os.getenv('USER_ID')
    if not user_id:
        user_id = st.text_input("User ID")
        if not user_id:
            st.error("Please provide your User ID or set USER_ID environment variable")
            return
            
    if st.button("Import Assessment Data"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        await handle_import(st.session_state.tenant_id, st.session_state.scenario_id, user_id, progress_bar, status_text)

async def handle_import(tenant_id: str, scenario_id: str, user_id: str, progress_bar, status_text):
    try:
        auth_header = build_api_header(user_id)
        
        async with AsyncSessionLocal() as session:
            service = AssessmentService(session=session, auth_header=auth_header)
            
            def update_progress(current: int, total: int, message: str):
                progress = min(current / total, 1.0) if total > 0 else 0
                progress_bar.progress(progress)
                status_text.text(message)
            
            stats = await service.import_assessment_data(
                tenant_id, 
                scenario_id,
                progress_callback=update_progress
            )
            
            if stats:
                progress_bar.progress(1.0)
                status_text.text("Import complete!")
                st.success(f"""Assessment data imported successfully!
                    \nAssets: {stats.get('assets', 0)}
                    \nComponents: {stats.get('components', 0)}
                    \nAssessments: {stats.get('assessments', 0)}""")
            else:
                st.error("Failed to import assessment data")
                
    except Exception as e:
        logger.error(f"Error importing assessment data: {str(e)}")
        st.error(f"Error: {str(e)}")