import streamlit as st
import pandas as pd
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.work_order_service import WorkOrderService
from work_order_review.ui.components.layout import render_header
import logging

logger = logging.getLogger(__name__)

async def render_work_order_upload():
    st.title("Upload Work Orders")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
        
    uploaded_file = st.file_uploader("Choose a file", type=['xlsx', 'csv'])
    
    if uploaded_file is not None:
        try:
            # Handle Excel files with multiple sheets
            if uploaded_file.name.endswith('.xlsx'):
                xls = pd.ExcelFile(uploaded_file)
                if len(xls.sheet_names) > 1:
                    sheet_name = st.selectbox("Select sheet", xls.sheet_names)
                    df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
                else:
                    df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
            
            st.write("Preview of uploaded data:")
            st.dataframe(df.head())
            
            # Let user select ID column
            id_column = st.selectbox(
                "Select the column containing work order IDs",
                options=df.columns.tolist()
            )
            
            if st.button("Upload Work Orders"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                stats_container = st.empty()
                
                await handle_upload(
                    df=df,
                    id_column=id_column,
                    tenant_id=st.session_state.tenant_id,
                    scenario_id=st.session_state.scenario_id,
                    progress_bar=progress_bar,
                    status_text=status_text,
                    stats_container=stats_container
                )
                
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}", exc_info=True)
            st.error(f"Error: {str(e)}")

async def handle_upload(df, id_column, tenant_id, scenario_id, 
                       progress_bar, status_text, stats_container):
    try:
        async with AsyncSessionLocal() as session:
            service = WorkOrderService(session)
            
            def update_progress(current: int, total: int, successful: int, failed: int):
                progress = min(current / total, 1.0)
                progress_bar.progress(progress)
                status_text.text(f"Processing: {current}/{total}")
                stats_container.info(f"""
                    ### Current Progress
                    - Successfully processed: {successful}
                    - Failed: {failed}
                    - Remaining: {total - current}
                """)
            
            stats = await service.upload_work_orders(
                df=df,
                id_column=id_column,
                tenant_id=tenant_id,
                scenario_id=scenario_id,
                progress_callback=update_progress
            )
            
            if stats:
                st.success(f"""
                    Upload complete!
                    • Successfully uploaded: {stats['successful']}
                    • Failed: {stats['failed']}
                    • Total processed: {stats['total']}
                """)
            else:
                st.error("Failed to upload work orders")
                
    except Exception as e:
        logger.error(f"Error uploading work orders: {str(e)}", exc_info=True)
        st.error(f"Error: {str(e)}") 