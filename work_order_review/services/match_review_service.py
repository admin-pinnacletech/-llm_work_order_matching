from datetime import datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from work_order_review.database.models import WorkOrderMatch, WorkOrder, WorkOrderStatus
import logging

logger = logging.getLogger(__name__)

class MatchReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def update_match_status(self, match_id: str, new_status: str, reviewer: str = None) -> bool:
        try:
            # Get the match to find its work order
            match = await self.session.get(WorkOrderMatch, match_id)
            if not match:
                logger.error(f"Match {match_id} not found")
                return False

            # Update the match's work order status
            stmt = update(WorkOrder).where(
                WorkOrder.id == match.work_order_id
            ).values(
                status=WorkOrderStatus.REVIEWED.value,
                reviewed_at=datetime.utcnow(),
                reviewed_by=reviewer
            )
            await self.session.execute(stmt)
            await self.session.commit()
            return True
        except Exception as e:
            logger.exception(f"Error updating match {match_id} to status {new_status}")
            await self.session.rollback()
            return False 