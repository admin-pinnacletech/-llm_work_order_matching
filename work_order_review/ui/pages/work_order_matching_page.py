import streamlit as st
import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update, func
import asyncio

from work_order_review.database.config import AsyncSessionLocal
from work_order_review.database.models import (
    WorkOrder, 
    WorkOrderProcessingResult, 
    WorkOrderStatus
)
from work_order_review.services.work_order_matching_service import WorkOrderMatchingService
from work_order_review.ui.components.layout import render_header
from work_order_review.ui.components.work_order_table import render_work_order_table
from work_order_review.ui.components.batch_selector import render_batch_selector

logger = logging.getLogger(__name__)

async def render_work_order_matching():
    """Main page render function for work order matching."""
    logger.info("Starting render_work_order_matching")
    start_time = datetime.now()
    render_header()
    
    # Constants
    page_size = 5000
    
    async with AsyncSessionLocal() as session:
        # Get count of unprocessed work orders first
        logger.info("Querying total work order count")
        query_start = datetime.now()
        count_query = select(func.count()).select_from(WorkOrder).where(
            WorkOrder.tenant_id == st.session_state.tenant_id,
            WorkOrder.facility_scenario_id == st.session_state.scenario_id,
            WorkOrder.status == WorkOrderStatus.UNPROCESSED.value
        )
        result = await session.execute(count_query)
        total_work_orders = result.scalar()
        logger.info(f"Found {total_work_orders} total work orders in {(datetime.now() - query_start).total_seconds():.2f}s")

        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Work Orders", total_work_orders)
        with col2:
            selected_count = st.session_state.get('selected_count', 0)
            st.metric("Selected", selected_count)
        with col3:
            st.metric("Remaining", total_work_orders - selected_count)

        # Create tabs for different views
        tab1, tab2 = st.tabs(["📋 Work Orders", "⚙️ Processing Options"])

        with tab1:
            # Initialize page state if not exists
            if 'page' not in st.session_state:
                st.session_state.page = 1
                st.session_state.work_orders = None
            
            # Only fetch work orders if page changed or not loaded
            if 'last_page' not in st.session_state or st.session_state.last_page != st.session_state.page:
                logger.info(f"Fetching work orders for page {st.session_state.page}")
                offset = (st.session_state.page - 1) * page_size
                
                query_start = datetime.now()
                query = select(WorkOrder).where(
                    WorkOrder.tenant_id == st.session_state.tenant_id,
                    WorkOrder.facility_scenario_id == st.session_state.scenario_id,
                ).order_by(WorkOrder.created_at.desc()).offset(offset).limit(page_size)
                
                result = await session.execute(query)
                st.session_state.work_orders = result.scalars().all()
                st.session_state.last_page = st.session_state.page
                logger.info(f"Fetched {len(st.session_state.work_orders)} work orders in {(datetime.now() - query_start).total_seconds():.2f}s")

            # Render work order table and get selections
            st.markdown("### Work Orders")
            edited_df, table_selected_work_orders = render_work_order_table(st.session_state.work_orders)
            
            # Process button and workflow
            if table_selected_work_orders:
                logger.info(f"Selected work orders from table: {len(table_selected_work_orders)}")
                st.divider()
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Ready to process {len(table_selected_work_orders)} work orders**")
                with col2:
                    if st.button(
                        "🚀 Process Selected", 
                        type="primary", 
                        use_container_width=True,
                        key="process_selected_button"
                    ):
                        logger.info("Process button clicked")
                        progress_text = st.empty()
                        progress_bar = st.progress(0)
                        
                        async def update_progress(current: int, total: int, status: str):
                            progress = float(current) / float(total) if total > 0 else 0
                            progress_bar.progress(progress)
                            progress_text.text(f"Processing {current} of {total} work orders...")
                        
                        await process_work_orders(
                            session=session,
                            work_orders=table_selected_work_orders,
                            callback=update_progress
                        )
                        
                        # Clear selections and refresh work orders
                        st.session_state.table_selections = {}
                        st.session_state.work_orders = None  # Force refresh of work orders
                        st.session_state.last_page = None    # Force refresh of current page
                        st.rerun()
            else:
                st.info("Select work orders to begin processing")

        with tab2:
            st.markdown("### Processing Options")
            auto_process = st.checkbox(
                "Auto-process next batch",
                help="Automatically start processing the next batch when current batch completes"
            )
            
            send_notifications = st.checkbox(
                "Send notifications",
                help="Send notifications when processing completes"
            )

        logger.info(f"Total page render time: {(datetime.now() - start_time).total_seconds():.2f}s")

async def process_work_orders(session, work_orders, callback):
    """Process selected work orders with progress tracking."""
    logger.info(f"Processing {len(work_orders)} work orders")
    st.warning("⚠️ **Please do not navigate away from this page.** Processing will stop if you leave.")
    
    # Setup progress tracking
    progress_container = st.empty()
    status_text = st.empty()
    timing_text = st.empty()
    
    with progress_container:
        progress_bar = st.progress(0.0)
        st.markdown("### Processing Work Orders")
    
    # Track timing
    start_time = datetime.now()
    
    try:
        # Create processing results for tracking
        logger.info("Creating processing result records")
        for wo in work_orders:
            result = WorkOrderProcessingResult(
                id=str(uuid.uuid4()),
                work_order_id=wo.id
            )
            session.add(result)
        await session.commit()
        logger.info("Processing result records created")
        
        # Initialize service
        logger.info("Initializing WorkOrderMatchingService")
        service = await WorkOrderMatchingService(
            session=session,
            tenant_id=st.session_state.tenant_id,
            scenario_id=st.session_state.scenario_id
        ).initialize()
        logger.info("Service initialized successfully")
        
        # Test service functionality
        logger.info("Testing service functionality")
        test_result = service.client.beta.assistants.list(limit=1)
        logger.info(f"Test API call successful: {bool(test_result)}")
        
        # Process work orders
        logger.info("Starting processing loop")
        
        def update_progress(wo_id: str, current: int, status: str):
            """Synchronous progress callback"""
            progress = float(current) / len(work_orders)
            progress_bar.progress(progress)
            
            status_text.text(
                f"Processing work order {current}/{len(work_orders)}\n"
                f"ID: {wo_id}\nStatus: {status}"
            )
            
            elapsed_time = (datetime.now() - start_time).total_seconds()
            if current > 0:
                avg_time_per_item = elapsed_time / current
                remaining_items = len(work_orders) - current
                estimated_remaining_time = remaining_items * avg_time_per_item
                
                timing_text.text(
                    f"Average time per work order: {avg_time_per_item:.1f} seconds\n"
                    f"Estimated time remaining: {timedelta(seconds=int(estimated_remaining_time))}"
                )
        
        results = await service.process_work_orders(
            work_orders,
            progress_callback=update_progress  # Now passing a sync function
        )
        
        # Display results
        successful = len([r for r in results if r.get('status') == 'success'])
        failed = len([r for r in results if r.get('status') == 'error'])
        
        if successful:
            st.success(f"Successfully processed {successful} work orders")
        if failed:
            st.warning(f"Failed to process {failed} work orders")
    except Exception as e:
        logger.exception("Error during processing")
        st.error(f"An error occurred: {str(e)}")
    finally:
        # Clear progress displays
        progress_container.empty()
        status_text.empty()
        timing_text.empty()

if __name__ == "__main__":
    import asyncio
    asyncio.run(render_work_order_matching()) 