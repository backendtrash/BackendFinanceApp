from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
import logging

from app.auth.dependencies import get_current_user, AuthenticatedUser
from app.analytics.schemas import (
    DashboardSummary,
    MonthlyAnalytics,
    WeeklyAnalytics,
    CategoryAnalytics,
    ProjectedAnalytics,
    BudgetProgressAnalytics,
    CarryForwardStatus,
    CarryForwardApply,
)
from app.analytics import service

# ── Logger ────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────
router = APIRouter()


# ── Dashboard Summary ─────────────────────────────────────────────────────
@router.get(
    "/dashboard",
    response_model=DashboardSummary,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard summary cards for current month",
)
async def get_dashboard(
    year:  Optional[int] = Query(None, description="Year  (defaults to current)"),
    month: Optional[int] = Query(None, description="Month (defaults to current)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns summary cards for the dashboard:
    total income, total expenses, net balance, savings rate.
    Defaults to current month if year/month not provided.
    """
    from datetime import date
    today = date.today()
    year  = year  or today.year
    month = month or today.month

    if not 1 <= month <= 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month must be between 1 and 12",
        )

    return await service.get_dashboard_summary(
        user_id=current_user.user_id,
        year=year,
        month=month,
    )


# ── Monthly Analytics ─────────────────────────────────────────────────────
@router.get(
    "/monthly",
    response_model=MonthlyAnalytics,
    status_code=status.HTTP_200_OK,
    summary="Get monthly income vs expenses chart data",
)
async def get_monthly_analytics(
    months_back: int = Query(12, description="Number of months to include"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns monthly income vs expenses for the last N months.
    Used to render the monthly trend chart on the dashboard.
    """
    if not 1 <= months_back <= 24:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="months_back must be between 1 and 24",
        )

    return await service.get_monthly_analytics(
        user_id=current_user.user_id,
        months_back=months_back,
    )


# ── Weekly Analytics ──────────────────────────────────────────────────────
@router.get(
    "/weekly",
    response_model=WeeklyAnalytics,
    status_code=status.HTTP_200_OK,
    summary="Get weekly cash flow chart data",
)
async def get_weekly_analytics(
    weeks_back: int = Query(12, description="Number of weeks to include"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns weekly income vs expenses for the last N weeks.
    Used to render the weekly cash flow chart.
    """
    if not 1 <= weeks_back <= 52:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="weeks_back must be between 1 and 52",
        )

    return await service.get_weekly_analytics(
        user_id=current_user.user_id,
        weeks_back=weeks_back,
    )


# ── Category Analytics ────────────────────────────────────────────────────
@router.get(
    "/categories",
    response_model=CategoryAnalytics,
    status_code=status.HTTP_200_OK,
    summary="Get spending breakdown by category",
)
async def get_category_analytics(
    year:        Optional[int] = Query(None, description="Year"),
    month:       Optional[int] = Query(None, description="Month"),
    months_back: int           = Query(1,    description="Months to include"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns expense breakdown by category as percentages and amounts.
    Used to render the category pie/bar chart.
    Defaults to current month.
    """
    return await service.get_category_analytics(
        user_id=current_user.user_id,
        months_back=months_back,
        year=year,
        month=month,
    )


# ── Projected vs Real ─────────────────────────────────────────────────────
@router.get(
    "/projected",
    response_model=ProjectedAnalytics,
    status_code=status.HTTP_200_OK,
    summary="Get projected vs real spending comparison",
)
async def get_projected_analytics(
    months_ahead: int = Query(3,  description="Future months to project"),
    months_back:  int = Query(3,  description="Past months to compare"),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Compares projected spending from recurring rules vs actual spending.
    Past months: real vs projected comparison.
    Future months: projection only from active recurring rules.
    Used to render the projected vs real chart.
    """
    if not 1 <= months_ahead <= 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="months_ahead must be between 1 and 12",
        )

    if not 1 <= months_back <= 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="months_back must be between 1 and 12",
        )

    return await service.get_projected_analytics(
        user_id=current_user.user_id,
        months_ahead=months_ahead,
        months_back=months_back,
    )


# ── Budget Progress ───────────────────────────────────────────────────────
@router.get(
    "/budget-progress",
    response_model=BudgetProgressAnalytics,
    status_code=status.HTTP_200_OK,
    summary="Get all budgets with current spending progress",
)
async def get_budget_progress(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns all active budgets with current period spending progress.
    Sorted by pct_spent descending — most critical budgets first.
    Used to render the budget overview screen.
    """
    return await service.get_budget_progress_analytics(
        user_id=current_user.user_id,
    )

@router.get(
    "/dashboard-weekly",
    status_code=status.HTTP_200_OK,
    summary="Get weekly income vs expenses vs projected for a month",
)
async def dashboard_weekly(
    year:         int,
    month:        int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    # Fetch user preference for week start day
    from app.preferences import service as pref_service
    prefs         = await pref_service.get_preferences(current_user.user_id)
    week_start    = prefs.get("week_start_day", 1)

    return await service.get_dashboard_weekly(
        user_id=current_user.user_id,
        year=year,
        month=month,
        week_start_day=week_start,
    )

@router.get(
    "/net-worth",
    status_code=status.HTTP_200_OK,
    summary="Get cumulative net worth over time",
)
async def net_worth_history(
    months_back:  int = 12,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_net_worth_history(
        user_id=current_user.user_id,
        months_back=months_back,
    )

@router.get(
    "/year-over-year",
    status_code=status.HTTP_200_OK,
    summary="Compare current month vs same month last year",
)
async def year_over_year(
    year:         int,
    month:        int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_year_over_year(
        user_id=current_user.user_id,
        year=year,
        month=month,
    )

@router.get(
    "/trends",
    status_code=status.HTTP_200_OK,
    summary="Get spending trends per category",
)
async def spending_trends(
    months_back:  int = 6,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return await service.get_spending_trends(
        user_id=current_user.user_id,
        months_back=months_back,
    )


# ── Carry-Forward ─────────────────────────────────────────────────────────
@router.get(
    "/carry-forward",
    response_model=CarryForwardStatus,
    status_code=status.HTTP_200_OK,
    summary="Get carry-forward status for a month (read-only)",
)
async def get_carry_forward(
    year:  int,
    month: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    return await service.get_carry_forward_status(
        user_id=current_user.user_id,
        year=year,
        month=month,
    )


@router.post(
    "/carry-forward",
    response_model=CarryForwardStatus,
    status_code=status.HTTP_200_OK,
    summary="Apply carry-forward balance from previous month (idempotent)",
)
async def post_carry_forward(
    body: CarryForwardApply,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    if not 1 <= body.month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    return await service.apply_carry_forward(
        user_id=current_user.user_id,
        year=body.year,
        month=body.month,
    )