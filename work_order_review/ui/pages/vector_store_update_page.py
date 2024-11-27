import streamlit as st
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.vector_store_service import VectorStoreService
from work_order_review.ui.components.layout import render_header
import logging
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

async def render_vector_store_update():
    st.title("Update Vector Store")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
        
    # Show current stats
    async with AsyncSessionLocal() as session:
        stmt = text("""
            SELECT COUNT(*) FROM assessments 
            WHERE tenant_id = :tenant_id 
            AND facility_scenario_id = :scenario_id
        """)
        result = await session.execute(stmt, {
            'tenant_id': st.session_state.tenant_id,
            'scenario_id': st.session_state.scenario_id
        })
        assessment_count = result.scalar()
        
    st.info(f"Found {assessment_count} assessments in database")
    
    if st.button("Update Vector Store"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        await handle_update(
            st.session_state.tenant_id,
            st.session_state.scenario_id,
            progress_bar,
            status_text
        )

    if st.button("Test Retrieval"):
        service = VectorStoreService()
        
        # Create expandable sections for different tests
        with st.expander("Basic Retrieval Tests", expanded=True):
            st.write("Testing basic retrieval functionality...")
            await service.test_retrieval()
            
        with st.expander("Metadata Verification", expanded=True):
            st.write("Verifying metadata storage and filtering...")
            await service.verify_metadata()

async def handle_update(tenant_id: str, scenario_id: str, progress_bar, status_text):
    try:
        async with AsyncSessionLocal() as session:
            stmt = text("""
                SELECT raw_data FROM assessments 
                WHERE tenant_id = :tenant_id 
                AND facility_scenario_id = :scenario_id
            """)
            result = await session.execute(stmt, {
                'tenant_id': tenant_id,
                'scenario_id': scenario_id
            })
            assessments = [json.loads(row[0]) for row in result]
            
        if not assessments:
            st.error("No assessments found in database")
            return
            
        total_assessments = len(assessments)
        status_text.text(f"Found {total_assessments} assessments")
        logger.info(f"Starting vector store update with {total_assessments} assessments")
        
        def update_progress(current: int, total: int):
            progress = min(current / total, 1.0) if total > 0 else 0
            progress_bar.progress(progress)
            status_text.text(f"Processed {current} of {total} assessments")
        
        service = VectorStoreService()
        success, result = await service.upload_assessments(
            assessments,
            progress_callback=update_progress
        )
        
        # Show final status with detailed stats
        if success:
            st.success(
                f"""Vector store update complete!
                • Total processed: {result['total_processed']}
                • Updated: {result['updated']}
                • Created: {result['created']}"""
            )
        else:
            st.error(f"Vector store update failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Error updating vector store: {str(e)}", exc_info=True)
        st.error(f"Error: {str(e)}")