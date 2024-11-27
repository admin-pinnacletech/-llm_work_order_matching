import streamlit as st
import pandas as pd
from typing import Dict, List
import logging
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.services.work_order_matching_service import WorkOrderMatchingService
from work_order_review.ui.components.layout import render_header
from work_order_review.database.models import WorkOrderStatus, WorkOrder, WorkOrderMatch, Asset, Component
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
import uuid
import asyncio
from sqlalchemy import text
from datetime import datetime
from sqlalchemy import update
from work_order_review.services.match_review_service import MatchReviewService

logger = logging.getLogger(__name__)

async def get_assets(session):
    """Get all assets for the current tenant/scenario"""
    query = select(Asset).where(
        Asset.tenant_id == st.session_state.tenant_id,
        Asset.facility_scenario_id == st.session_state.scenario_id
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_components(session, asset_id: str):
    """Get components for a specific asset"""
    logger.info(f"Querying components for asset_id: {asset_id}")
    query = select(Component).where(
        Component.asset_id == asset_id,
        Component.tenant_id == st.session_state.tenant_id,
        Component.facility_scenario_id == st.session_state.scenario_id
    )
    result = await session.execute(query)
    components = result.scalars().all()
    logger.info(f"Found {len(components)} components")
    return components

async def render_work_order_review():
    st.title("Review Work Order Matches")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
    
    async with AsyncSessionLocal() as session:
        # Get pending review work orders with matches preloaded
        stmt = select(WorkOrder).where(
            WorkOrder.tenant_id == st.session_state.tenant_id,
            WorkOrder.facility_scenario_id == st.session_state.scenario_id,
            WorkOrder.status == WorkOrderStatus.PENDING_REVIEW.value
        ).options(
            selectinload(WorkOrder.matches)
        ).order_by(
            WorkOrder.created_at,
            WorkOrder.external_id
        )
        
        result = await session.execute(stmt)
        work_orders = result.scalars().all()
        
        if not work_orders:
            st.info("No work orders pending review")
            return
            
        # Initialize work order index in session state if not present
        # or reset if it's out of bounds
        if ('current_wo_index' not in st.session_state or 
            st.session_state.current_wo_index >= len(work_orders)):
            st.session_state.current_wo_index = 0
        
        current_index = st.session_state.current_wo_index
        work_order = work_orders[current_index]
        
        # Progress indicator
        st.progress((current_index + 1) / len(work_orders))
        st.markdown(f"### Work Order {current_index + 1} of {len(work_orders)}")
        st.subheader(f"Work Order: {work_order.external_id}")
        
        # Create two main columns
        wo_col, matches_col = st.columns([1, 1])
        
        # Work Order Details Column
        with wo_col:
            st.markdown("### Work Order Details")
            
            # Filter out internal fields and empty values
            excluded_fields = {'id', 'tenant_id', 'facility_scenario_id', 'raw_data', 'status', 
                             'review_notes', 'reviewed_at', 'reviewed_by', 'created_at', 'updated_at'}
            
            details = {
                k: v for k, v in work_order.raw_data.items() 
                if k not in excluded_fields 
                and v is not None 
                and str(v).strip() != ''
            }
            
            # Split details into two columns
            mid_point = len(details) // 2
            keys = list(details.keys())
            
            col1, col2 = st.columns(2)
            
            with col1:
                for key in keys[:mid_point]:
                    st.markdown(f"**{key}:** {details[key]}")
            
            with col2:
                for key in keys[mid_point:]:
                    st.markdown(f"**{key}:** {details[key]}")
        
        # Matches Column
        with matches_col:
            st.markdown("### Review Matches")
            
            # Existing Matches Table first
            if matches := work_order.matches:
                st.markdown("#### Current Matches")
                
                review_service = MatchReviewService(session)
                
                # Initialize match statuses in session state if not present
                if 'match_statuses' not in st.session_state:
                    st.session_state.match_statuses = {}
                
                # Fetch all assets once to avoid multiple queries
                assets = await get_assets(session)
                asset_dict = {asset.client_id: asset.name for asset in assets}
                
                for match in matches:
                    # Generate a unique key that includes the status
                    container_key = f"match_container_{match.id}_{match.review_status}"
                    
                    with st.container():
                        # Fetch asset name using asset_client_id
                        asset_name = asset_dict.get(match.asset_client_id, "Unknown Asset")
                        
                        # Create the colored container with the current status
                        background_color = (
                            '#d4edda' if match.review_status == 'ACCEPTED'
                            else '#f8d7da' if match.review_status == 'REJECTED'
                            else '#f8f9fa'
                        )
                        
                        st.markdown(
                            f"""
                            <div style="padding: 10px; border-radius: 5px; background-color: {background_color};"
                                 key="{container_key}">
                                <strong>Asset Client ID:</strong> {match.asset_client_id}<br>
                                <strong>Asset Name:</strong> {asset_name}<br>
                                <strong>Confidence:</strong> {match.matching_confidence_score:.0%}<br>
                                <strong>Status:</strong> {match.review_status or 'PENDING'}<br>
                                <strong>Match Reasoning:</strong> {match.matching_reasoning}<br>
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                        
                        # Action buttons
                        col1, col2, col3 = st.columns([1, 1, 1])
                        
                        with col1:
                            if st.button("✅ Accept", 
                                       key=f"accept_{match.id}",
                                       disabled=match.review_status == 'ACCEPTED'):
                                logger.info(f"Accept button clicked for match {match.id}")
                                try:
                                    async with AsyncSessionLocal() as update_session:
                                        stmt = update(WorkOrderMatch).where(
                                            WorkOrderMatch.id == match.id
                                        ).values(
                                            review_status='ACCEPTED',
                                            reviewed_at=datetime.utcnow()
                                        )
                                        await update_session.execute(stmt)
                                        await update_session.commit()
                                        logger.info(f"Successfully updated match {match.id} to ACCEPTED")
                                        st.success("Match accepted")
                                        st.rerun()
                                except Exception as e:
                                    logger.exception("Error accepting match")
                                    st.error(f"Error: {str(e)}")
                        
                        with col2:
                            if st.button("🗑️ Reject", 
                                       key=f"reject_{match.id}",
                                       disabled=match.review_status == 'REJECTED'):
                                logger.info(f"Reject button clicked for match {match.id}")
                                try:
                                    async with AsyncSessionLocal() as update_session:
                                        stmt = update(WorkOrderMatch).where(
                                            WorkOrderMatch.id == match.id
                                        ).values(
                                            review_status='REJECTED',
                                            reviewed_at=datetime.utcnow()
                                        )
                                        await update_session.execute(stmt)
                                        await update_session.commit()
                                        logger.info(f"Successfully updated match {match.id} to REJECTED")
                                        st.success("Match rejected")
                                        st.rerun()
                                except Exception as e:
                                    logger.exception("Error rejecting match")
                                    st.error(f"Error: {str(e)}")
                        
                        with col3:
                            if st.button("🔄 Reset", 
                                       key=f"reset_{match.id}",
                                       disabled=match.review_status == 'PENDING'):
                                logger.info(f"Reset button clicked for match {match.id}")
                                try:
                                    async with AsyncSessionLocal() as update_session:
                                        stmt = update(WorkOrderMatch).where(
                                            WorkOrderMatch.id == match.id
                                        ).values(
                                            review_status='PENDING',
                                            reviewed_at=datetime.utcnow()
                                        )
                                        await update_session.execute(stmt)
                                        await update_session.commit()
                                        logger.info(f"Successfully updated match {match.id} to PENDING")
                                        st.success("Match reset")
                                        st.rerun()
                                except Exception as e:
                                    logger.exception("Error resetting match")
                                    st.error(f"Error: {str(e)}")
            
            # Add New Match section
            with st.expander("➕ Add New Match"):
                try:
                    assets = await get_assets(session)
                    asset_options = {f"{asset.client_id}": asset for asset in assets}
                    
                    selected_asset = st.selectbox(
                        "Asset",
                        options=[""] + list(asset_options.keys()),
                        key=f"selected_asset_{work_order.id}"
                    )
                    
                    if selected_asset:
                        with st.form(key=f"new_match_form_{work_order.id}"):
                            confidence_score = st.slider(
                                "Confidence Score", 
                                min_value=0.0, 
                                max_value=1.0, 
                                value=0.8
                            )
                            
                            matching_reasoning = st.text_area("Matching Reasoning")
                            
                            submitted = st.form_submit_button("Add Match")
                            
                            if submitted:
                                try:
                                    async with AsyncSessionLocal() as new_session:
                                        async with new_session.begin():
                                            new_match = WorkOrderMatch(
                                                id=str(uuid.uuid4()),
                                                work_order_id=work_order.id,
                                                asset_client_id=selected_asset,
                                                matching_confidence_score=confidence_score,
                                                matching_reasoning=matching_reasoning,
                                                review_status='PENDING'
                                            )
                                            new_session.add(new_match)
                                            await new_session.commit()
                                            
                                        st.success("Match added successfully!")
                                        st.rerun()
                                        
                                except Exception as e:
                                    st.error(f"Error adding match: {str(e)}")
                                    logger.exception("Error adding match")
                except Exception as e:
                    st.error(f"Error selecting asset: {str(e)}")
            
            # At the start of the matches section, handle the reset
            if st.session_state.get(f"match_added_{work_order.id}"):
                # Clear the flag
                del st.session_state[f"match_added_{work_order.id}"]
                # Close the form
                st.session_state[f"show_match_form_{work_order.id}"] = False
            
            # Check if all matches have been reviewed (either accepted or rejected)
            all_matches_reviewed = all(
                match.review_status in ['ACCEPTED', 'REJECTED'] 
                for match in matches
            )

            # Review notes input
            review_notes = st.text_area(
                "Review Notes",
                key=f"notes_{work_order.id}",
                placeholder="Add any notes about this review..."
            )

            # Submit button - disabled if not all matches are reviewed
            if st.button("Submit Review", 
                        key=f"submit_{work_order.id}", 
                        type="primary",
                        disabled=not all_matches_reviewed):
                if not all_matches_reviewed:
                    st.warning("Please review all matches before submitting.")
                else:
                    try:
                        # Collect all match decisions based on their current review status
                        match_decisions = {
                            match.id: match.review_status == 'ACCEPTED'
                            for match in matches
                        }
                        
                        async with AsyncSessionLocal() as review_session:
                            async with review_session.begin():
                                review_service = MatchReviewService(review_session)
                                success = await review_service.submit_review(
                                    work_order_id=work_order.id,
                                    match_decisions=match_decisions,
                                    review_notes=review_notes
                                )
                                
                                if success:
                                    st.success("Review submitted successfully!")
                                else:
                                    st.error("Failed to submit review")
                        
                        st.rerun()
                    except Exception as e:
                        logger.exception("Error submitting review")
                        st.error(f"Error submitting review: {str(e)}")

            # Add a message to show how many matches still need review
            pending_matches = sum(1 for match in matches if match.review_status == 'PENDING')
            if pending_matches > 0:
                st.warning(f"⚠️ {pending_matches} match{'es' if pending_matches != 1 else ''} still need{'s' if pending_matches == 1 else ''} to be reviewed")
        
        # Navigation buttons
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if current_index > 0:
                if st.button("← Previous"):
                    st.session_state.current_wo_index -= 1
                    st.rerun()
        
        with col3:
            if current_index < len(work_orders) - 1:
                if st.button("Next →"):
                    st.session_state.current_wo_index += 1
                    st.rerun()
            else:
                st.success("All work orders reviewed!")

if __name__ == "__main__":
    asyncio.run(render_work_order_review()) 