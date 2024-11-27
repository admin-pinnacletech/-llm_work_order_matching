import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sqlalchemy import select, func, text
from work_order_review.database.config import AsyncSessionLocal
from work_order_review.database.models import ModelMetrics, WorkOrderMatch, WorkOrder
from work_order_review.ui.components.layout import render_header

async def render_model_metrics():
    st.title("Model Performance Metrics")
    render_header()
    
    if not all(key in st.session_state for key in ['tenant_id', 'scenario_id']):
        st.error("Please select a scenario first")
        return
    
    async with AsyncSessionLocal() as session:
        # Get overall statistics
        stats_query = text("""
            SELECT 
                COUNT(DISTINCT wm.work_order_id) as total_processed,
                AVG(CASE WHEN wm.review_status = 'ACCEPTED' THEN 1 ELSE 0 END) as acceptance_rate,
                AVG(wm.matching_confidence_score) as avg_confidence,
                COUNT(CASE WHEN wm.review_status = 'ACCEPTED' THEN 1 END) as total_accepted,
                COUNT(CASE WHEN wm.review_status = 'REJECTED' THEN 1 END) as total_rejected
            FROM work_order_matches wm
            JOIN work_orders wo ON wo.id = wm.work_order_id
            WHERE wo.tenant_id = :tenant_id 
            AND wo.facility_scenario_id = :scenario_id
        """)
        
        result = await session.execute(stats_query, {
            'tenant_id': st.session_state.tenant_id,
            'scenario_id': st.session_state.scenario_id
        })
        stats = result.mappings().first()
        
        # Display metrics in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Processed", f"{stats['total_processed']:,}")
        with col2:
            st.metric("Acceptance Rate", f"{stats['acceptance_rate']*100:.1f}%")
        with col3:
            st.metric("Avg Confidence", f"{stats['avg_confidence']*100:.1f}%")
        with col4:
            st.metric("Total Matches", f"{(stats['total_accepted'] + stats['total_rejected']):,}")
        
        # Time series of acceptance rates
        st.subheader("Acceptance Rate Over Time")
        
        timeseries_query = text("""
            SELECT 
                date(wm.created_at) as date,
                COUNT(DISTINCT wm.work_order_id) as work_orders_processed,
                AVG(CASE WHEN wm.review_status = 'ACCEPTED' THEN 1 ELSE 0 END) as daily_acceptance_rate,
                AVG(wm.matching_confidence_score) as avg_confidence
            FROM work_order_matches wm
            JOIN work_orders wo ON wo.id = wm.work_order_id
            WHERE wo.tenant_id = :tenant_id 
            AND wo.facility_scenario_id = :scenario_id
            GROUP BY date(wm.created_at)
            ORDER BY date
        """)
        
        result = await session.execute(timeseries_query, {
            'tenant_id': st.session_state.tenant_id,
            'scenario_id': st.session_state.scenario_id
        })
        
        df_time = pd.DataFrame(result.mappings().all())
        
        if not df_time.empty:
            # Ensure the 'date' column is a datetime type
            df_time['date'] = pd.to_datetime(df_time['date'])
            
            # Create two-line plot
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_time['date'],
                y=df_time['daily_acceptance_rate'],
                name='Acceptance Rate',
                line=dict(color='#2ecc71')
            ))
            fig.add_trace(go.Scatter(
                x=df_time['date'],
                y=df_time['avg_confidence'],
                name='Avg Confidence',
                line=dict(color='#3498db')
            ))
            
            fig.update_layout(
                title='Daily Acceptance Rate and Confidence',
                xaxis_title='Date',
                yaxis_title='Rate',
                yaxis_tickformat=',.0%'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Confidence Score Distribution
            st.subheader("Confidence Score Distribution")
            
            confidence_query = text("""
                SELECT 
                    matching_confidence_score,
                    review_status
                FROM work_order_matches wm
                JOIN work_orders wo ON wo.id = wm.work_order_id
                WHERE wo.tenant_id = :tenant_id 
                AND wo.facility_scenario_id = :scenario_id
                AND review_status IN ('ACCEPTED', 'REJECTED')
            """)
            
            result = await session.execute(confidence_query, {
                'tenant_id': st.session_state.tenant_id,
                'scenario_id': st.session_state.scenario_id
            })
            
            df_confidence = pd.DataFrame(result.mappings().all())
            
            if not df_confidence.empty:
                fig = px.histogram(
                    df_confidence,
                    x='matching_confidence_score',
                    color='review_status',
                    nbins=20,
                    title='Distribution of Confidence Scores by Review Status',
                    labels={'matching_confidence_score': 'Confidence Score', 'count': 'Number of Matches'},
                    color_discrete_map={'ACCEPTED': '#2ecc71', 'REJECTED': '#e74c3c'}
                )
                
                fig.update_layout(
                    xaxis_tickformat=',.0%',
                    bargap=0.1
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Recent Performance Table
            st.subheader("Recent Performance")
            df_time['acceptance_rate'] = df_time['daily_acceptance_rate'].map('{:.1%}'.format)
            df_time['avg_confidence'] = df_time['avg_confidence'].map('{:.1%}'.format)
            df_time['date'] = df_time['date'].dt.strftime('%Y-%m-%d')
            
            st.dataframe(
                df_time.rename(columns={
                    'date': 'Date',
                    'work_orders_processed': 'Work Orders',
                    'acceptance_rate': 'Acceptance Rate',
                    'avg_confidence': 'Avg Confidence'
                }).sort_values('Date', ascending=False),
                use_container_width=True
            )

if __name__ == "__main__":
    import asyncio
    asyncio.run(render_model_metrics())