from datetime import datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from work_order_review.database.models import WorkOrderMatch, WorkOrder, WorkOrderStatus
import logging
from typing import Dict, List
from sqlalchemy import select
from work_order_review.database.models import ModelMetrics
from sqlalchemy.sql import text
import uuid
from work_order_review.database.models import CorrectiveAction

logger = logging.getLogger(__name__)

class MatchReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def _update_model_metrics(self, work_order_id: str, match_decisions: Dict[str, bool]):
        """Update model metrics based on review decisions"""
        try:
            # Get all matches for this work order
            stmt = select(WorkOrderMatch).where(WorkOrderMatch.work_order_id == work_order_id)
            result = await self.session.execute(stmt)
            matches = result.scalars().all()
            
            # Calculate metrics
            total_matches = len(matches)
            accepted_matches = sum(1 for m in matches if m.review_status == 'ACCEPTED')
            rejected_matches = sum(1 for m in matches if m.review_status == 'REJECTED')
            confidence_scores = [m.matching_confidence_score for m in matches]
            
            # Create or update metrics
            metrics = ModelMetrics(
                work_order_id=work_order_id,
                suggested_matches_count=total_matches,
                accepted_matches_count=accepted_matches,
                rejected_matches_count=rejected_matches,
                confidence_scores=confidence_scores
            )
            self.session.add(metrics)
            
        except Exception as e:
            logger.error(f"Error updating model metrics: {str(e)}")
    
    async def submit_review(
        self, 
        work_order_id: str, 
        match_decisions: Dict[str, bool], 
        review_notes: str,
        summary: str = None,
        downtime_hours: float = None,
        cost: float = None,
        corrective_actions: List[str] = None,
        tenant_id: str = None,
        facility_scenario_id: str = None
    ) -> bool:
        """Submit a work order review with all associated data."""
        try:
            # Update work order status and review details
            update_stmt = text("""
                UPDATE work_orders 
                SET status = :status,
                    review_notes = :review_notes,
                    reviewed_at = :reviewed_at,
                    reviewed_by = :reviewed_by,
                    llm_summary = :summary,
                    llm_downtime_hours = :downtime_hours,
                    llm_cost = :cost
                WHERE id = :work_order_id
            """)
            
            await self.session.execute(
                update_stmt,
                {
                    'status': WorkOrderStatus.REVIEWED.value,
                    'review_notes': review_notes,
                    'reviewed_at': datetime.utcnow(),
                    'reviewed_by': 'user',  # TODO: Add actual user ID
                    'work_order_id': work_order_id,
                    'summary': summary,
                    'downtime_hours': downtime_hours,
                    'cost': cost
                }
            )

            # Update corrective actions if provided
            if corrective_actions is not None:
                # Delete existing corrective actions
                delete_stmt = text("""
                    DELETE FROM corrective_actions 
                    WHERE work_order_id = :work_order_id
                """)
                await self.session.execute(delete_stmt, {'work_order_id': work_order_id})
                
                # Insert new corrective actions
                for action in corrective_actions:
                    new_action = CorrectiveAction(
                        id=str(uuid.uuid4()),
                        work_order_id=work_order_id,
                        action=action,
                        tenant_id=tenant_id,
                        facility_scenario_id=facility_scenario_id
                    )
                    self.session.add(new_action)

            # Process match decisions
            for match_id, is_accepted in match_decisions.items():
                stmt = update(WorkOrderMatch).where(
                    WorkOrderMatch.id == match_id
                ).values(
                    review_status='ACCEPTED' if is_accepted else 'REJECTED',
                    reviewed_at=datetime.utcnow()
                )
                await self.session.execute(stmt)
            
            await self.session.commit()
            return True
            
        except Exception as e:
            logger.exception("Error submitting review")
            await self.session.rollback()
            return False
    
    async def update_match_status(self, match_id: str, new_status: str) -> bool:
        try:
            stmt = update(WorkOrderMatch).where(
                WorkOrderMatch.id == match_id
            ).values(
                review_status=new_status,
                reviewed_at=datetime.utcnow()
            )
            await self.session.execute(stmt)
            return True
            
        except Exception as e:
            logger.exception(f"Error updating match {match_id} to status {new_status}")
            return False 