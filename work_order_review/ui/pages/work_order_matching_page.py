import streamlit as st
import pandas as pd
from typing import Dict, List
import logging
from datetime import datetime
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.work_order_matching_service import WorkOrderMatchingService
from work_order_review.ui.components.layout import render_header
from work_order_review.database.models import (
    WorkOrderStatus, 
    WorkOrder, 
    WorkOrderMatch,
    WorkOrderProcessingResult
)
from sqlalchemy import select, text, update
import asyncio
import uuid

logger = logging.getLogger(__name__)

async def render_work_order_matching():
    st.title("Match Work Orders")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
        
    # Store selections in session state
    if 'selected_work_orders' not in st.session_state:
        st.session_state.selected_work_orders = set()
        
    async with AsyncSessionLocal() as session:
        # Get unprocessed work orders first
        stmt = select(WorkOrder).where(
            WorkOrder.tenant_id == st.session_state.tenant_id,
            WorkOrder.facility_scenario_id == st.session_state.scenario_id,
            WorkOrder.status == WorkOrderStatus.UNPROCESSED.value
        )
        result = await session.execute(stmt)
        work_orders = result.scalars().all()
        
        if not work_orders:
            st.info("No unprocessed work orders found")
            return
            
        # Create dataframe for selection
        work_order_data = []
        for wo in work_orders:
            work_order_data.append({
                'id': wo.id,
                'external_id': wo.external_id,
                'description': wo.raw_data.get('description', 'No description'),
                'select': wo.id in st.session_state.selected_work_orders
            })
            
        df = pd.DataFrame(work_order_data)
        
        # Stats cards at the top
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Work Orders", len(work_orders))
        with col2:
            st.metric("Selected", len(st.session_state.selected_work_orders))
        with col3:
            st.metric("Remaining", len(work_orders) - len(st.session_state.selected_work_orders))
        
        st.divider()
        
        
        # Selection controls in a styled container
        with st.container():
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                st.write("")  # Add vertical spacing
                if st.button("📋 Select All", use_container_width=True):
                    st.session_state.selected_work_orders.update(df['id'].tolist())
                    st.rerun()

            with col2:
                st.write("")  # Add vertical spacing
                if st.button("🗑️ Clear Selection", use_container_width=True):
                    st.session_state.selected_work_orders.clear()
                    st.rerun()
            
            with col3:
                st.write("Batch Size")
                batch_size = st.number_input(
                    label="Batch Size",
                    label_visibility="collapsed",  # Hide the label
                    min_value=1, 
                    max_value=len(work_orders),
                    value=min(10, len(work_orders)), 
                    step=1,
                    help="Number of work orders to process at once"
                )
                st.write("")  # Add vertical spacing
                if st.button("➕ Select Batch", type="primary", use_container_width=True):
                    unselected_ids = [
                        wo.id for wo in work_orders 
                        if wo.id not in st.session_state.selected_work_orders
                    ]
                    new_selections = unselected_ids[:batch_size]
                    st.session_state.selected_work_orders.update(new_selections)
                    st.rerun()
        
        # Work orders table with styling
        st.markdown("""
        <div style='background-color: #f8f9fa; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;'>
            <h4 style='color: #495057; margin-top: 0;'>📄 Work Orders</h4>
        </div>
        """, unsafe_allow_html=True)
        
        # Enhanced data editor
        edited_df = st.data_editor(
            df,
            key="work_order_table",
            column_config={
                "select": st.column_config.CheckboxColumn(
                    "Process",
                    help="Select work orders to process",
                    default=False,
                ),
                "description": st.column_config.TextColumn(
                    "Description",
                    width="large"
                ),
                "external_id": st.column_config.TextColumn(
                    "Work Order ID",
                    width="medium"
                ),
                "id": st.column_config.TextColumn(
                    "ID",
                    width="medium"
                )
            },
            hide_index=True,
            disabled=["id", "external_id", "description"],
            use_container_width=True
        )
        
        # Process button with prominence
        if len(st.session_state.selected_work_orders) > 0:
            if st.button("🚀 Process Selected Work Orders", type="primary", use_container_width=True):
                selected_ids = [
                    row['id'] for _, row in edited_df.iterrows()
                    if row['select']
                ]
                
                if not selected_ids:
                    st.warning("Please select at least one work order")
                    return
                
                # Create a container for progress tracking
                progress_container = st.empty()
                with progress_container.container():
                    st.markdown("### Processing Progress")
                    progress_bar = st.progress(0.0)
                    status_text = st.empty()
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        time_remaining = st.empty()
                    
                    with col2:
                        st.markdown("### Statistics")
                        processed_count = st.empty()
                        avg_speed = st.empty()
                    
                    total = len(selected_ids)
                    start_time = datetime.now()
                    
                    # Process selected work orders
                    selected_work_orders = [wo for wo in work_orders if wo.id in selected_ids]
                    
                    try:
                        service = await WorkOrderMatchingService(
                            session=session,
                            tenant_id=st.session_state.tenant_id,
                            scenario_id=st.session_state.scenario_id
                        ).initialize()

                        def progress_callback(work_order_id: str, current: int):
                            progress = current / total
                            progress_bar.progress(progress, f"Processing {current}/{total}")
                            status_text.markdown(f"🔄 **Processing work order {current}/{total}**")
                            
                            elapsed_time = (datetime.now() - start_time).total_seconds()
                            if current > 1:
                                avg_time_per_item = elapsed_time / current
                                remaining_items = total - current
                                remaining_seconds = remaining_items * avg_time_per_item
                                remaining_minutes = int(remaining_seconds // 60)
                                remaining_seconds = int(remaining_seconds % 60)
                                
                                # Update statistics
                                processed_count.markdown(f"✅ **Processed:** {current}/{total}")
                                avg_speed.markdown(f"⚡ **Speed:** {avg_time_per_item:.1f}s/item")
                                time_remaining.markdown(
                                    f"⏱️ **Est. remaining:** {remaining_minutes}m {remaining_seconds}s"
                                )
                        
                        # Create processing results for tracking
                        for wo in selected_work_orders:
                            result = WorkOrderProcessingResult(
                                id=str(uuid.uuid4()),
                                work_order_id=wo.id
                            )
                            session.add(result)
                        await session.commit()
                        
                        results = await service.process_work_orders(
                            selected_work_orders,
                            progress_callback=progress_callback
                        )
                        
                        # Update processing results
                        for result in results:
                            wo_id = result['work_order_id']
                            stmt = update(WorkOrderProcessingResult).where(
                                WorkOrderProcessingResult.work_order_id == wo_id
                            ).values(
                                error=result.get('error'),
                                raw_response=result.get('response')
                            )
                            await session.execute(stmt)
                        await session.commit()
                        
                        # Clean up resources
                        await service.cleanup()
                        
                        # Show final results
                        successful = len([r for r in results if r.get('status') == 'success'])
                        failed = len([r for r in results if r.get('status') == 'error'])
                        
                        if successful:
                            st.success(f"Successfully processed {successful} work orders")
                        if failed:
                            st.warning(f"Failed to process {failed} work orders")
                        
                        # Show completion time
                        total_elapsed = (datetime.now() - start_time).total_seconds()
                        minutes = int(total_elapsed // 60)
                        seconds = int(total_elapsed % 60)
                        st.info(f"Total processing time: {minutes}m {seconds}s")
                        
                        # Clear the selected work orders from session state
                        st.session_state.selected_work_orders -= set(selected_ids)
                        
                        # Rerun to refresh the page
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
                        logger.error(f"Error during processing: {str(e)}", exc_info=True)

if __name__ == "__main__":
    import asyncio
    asyncio.run(render_work_order_matching()) 