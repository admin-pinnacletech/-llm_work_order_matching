import streamlit as st
from typing import List
from work_order_review.database.models import WorkOrder

def render_batch_selector(work_orders: List[WorkOrder]) -> List[WorkOrder]:
    """Render batch selection controls and return selected work orders."""
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📋 Select All", use_container_width=True):
            st.session_state.selected_work_orders = work_orders
            
    with col2:
        if st.button("❌ Clear Selection", use_container_width=True):
            st.session_state.selected_work_orders = []
    
    # Batch size selector
    batch_size = st.number_input(
        "Batch Size",
        min_value=1,
        max_value=len(work_orders),
        value=min(3, len(work_orders)),
        step=1
    )
    
    if st.button("🎯 Select Batch", type="primary", use_container_width=True):
        st.session_state.selected_work_orders = work_orders[:batch_size]
    
    return st.session_state.get('selected_work_orders', []) 