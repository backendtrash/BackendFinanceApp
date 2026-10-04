from fastapi  import APIRouter, Depends, HTTPException, status
from typing   import Optional
from uuid     import UUID
from datetime import date
import logging

from app.auth.dependencies      import get_current_user, AuthenticatedUser
from app.sinking_funds          import service
from app.sinking_funds.schemas  import (
    SinkingFundCreate,
    SinkingFundUpdate,
    ContributeRequest,
    PayoutRequest,
    ReleaseRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="List sinking funds with computed progress",
)
async def list_sinking_funds(
    include_inactive: bool = False,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.list_sinking_funds(
        user_id=current_user.user_id,
        include_inactive=include_inactive,
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a sinking fund",
)
async def create_sinking_fund(
    body: SinkingFundCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return await service.create_sinking_fund(
            user_id=current_user.user_id,
            data=body,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{fund_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a single sinking fund",
)
async def get_sinking_fund(
    fund_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    fund = await service.get_fund_by_id(
        fund_id=fund_id,
        user_id=current_user.user_id,
    )
    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return fund


@router.patch(
    "/{fund_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a sinking fund",
)
async def update_sinking_fund(
    fund_id: UUID,
    body: SinkingFundUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    fund = await service.update_sinking_fund(
        fund_id=fund_id,
        user_id=current_user.user_id,
        data=body,
    )
    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return fund


@router.delete(
    "/{fund_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a sinking fund",
)
async def delete_sinking_fund(
    fund_id: UUID,
    on_balance: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Refuses with 409 while the fund still holds money, unless on_balance
    says what to do with it:
      release — return it to spendable as an earning
      keep    — write it off as spent
    Archiving via PATCH is_active=false is the softer alternative.
    """
    if on_balance is not None and on_balance not in ("keep", "release"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="on_balance must be 'keep' or 'release'",
        )

    deleted, reason = await service.delete_sinking_fund(
        fund_id=fund_id,
        user_id=current_user.user_id,
        on_balance=on_balance,
    )

    if not deleted and reason == "has_balance":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This fund still holds money. Archive it instead, or pass "
                "?on_balance=release to return the balance to spendable, "
                "or ?on_balance=keep to write it off."
            ),
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )


@router.post(
    "/{fund_id}/contribute",
    status_code=status.HTTP_201_CREATED,
    summary="Set money aside into a fund",
)
async def contribute(
    fund_id: UUID,
    body: ContributeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Creates a real expense linked to the fund — net balance drops now."""
    try:
        result = await service.contribute(
            fund_id=fund_id,
            user_id=current_user.user_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return result


@router.post(
    "/{fund_id}/payout",
    status_code=status.HTTP_201_CREATED,
    summary="Pay the bill out of the fund",
)
async def payout(
    fund_id: UUID,
    body: PayoutRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Creates no expense, so net balance does not move — the money already
    left as contributions. A shortfall is covered by a top-up contribution
    first, and only that part hits net balance.
    """
    try:
        result = await service.payout(
            fund_id=fund_id,
            user_id=current_user.user_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return result


@router.post(
    "/{fund_id}/release",
    status_code=status.HTTP_201_CREATED,
    summary="Return fund money to the spendable pool",
)
async def release(
    fund_id: UUID,
    body: ReleaseRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Creates an offsetting earning. Distorts income analytics by design —
    warn the user before calling this."""
    try:
        result = await service.release(
            fund_id=fund_id,
            user_id=current_user.user_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return result


@router.post(
    "/{fund_id}/renew",
    status_code=status.HTTP_200_OK,
    summary="Roll the fund into its next cycle",
)
async def renew(
    fund_id: UUID,
    due_date: Optional[date] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    fund = await service.renew_fund(
        fund_id=fund_id,
        user_id=current_user.user_id,
        due_date=due_date,
    )
    if not fund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sinking fund {fund_id} not found",
        )
    return fund


@router.get(
    "/{fund_id}/activity",
    status_code=status.HTTP_200_OK,
    summary="Merged contribution and payout ledger",
)
async def get_activity(
    fund_id: UUID,
    limit:  int = 50,
    offset: int = 0,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_activity(
        fund_id=fund_id,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
