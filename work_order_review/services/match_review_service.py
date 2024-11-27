from datetime import datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from work_order_review.database.models import WorkOrderMatch, WorkOrder, WorkOrderStatus
import logging
from typing import Dict
from sqlalchemy import select
from work_order_review.database.models import ModelMetrics

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
    
    async def submit_review(self, work_order_id: str, match_decisions: Dict[str, bool], review_notes: str = None) -> bool:
        """Submit a work order review with match decisions"""
        try:
            # Update match statuses
            for match_id, is_accepted in match_decisions.items():
                status = 'ACCEPTED' if is_accepted else 'REJECTED'
                stmt = update(WorkOrderMatch).where(
                    WorkOrderMatch.id == match_id
                ).values(
                    review_status=status,
                    reviewed_at=datetime.utcnow()
                )
                await self.session.execute(stmt)
            
            # Update work order status
            stmt = update(WorkOrder).where(
                WorkOrder.id == work_order_id
            ).values(
                status=WorkOrderStatus.REVIEWED.value,
                review_notes=review_notes,
                reviewed_at=datetime.utcnow()
            )
            await self.session.execute(stmt)
            
            # Update metrics
            await self._update_model_metrics(work_order_id, match_decisions)
            
            return True
            
        except Exception as e:
            logger.exception(f"Error submitting review for work order {work_order_id}")
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