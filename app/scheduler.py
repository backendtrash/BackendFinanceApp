from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger
import logging

logger = logging.getLogger(__name__)

# ── Scheduler singleton ───────────────────────────────────────────────────
scheduler = AsyncIOScheduler()


async def run_recurring_rules() -> None:
    """
    Daily job that processes all due recurring rules.
    Runs at midnight every day.
    Creates expense/earning transactions for all rules
    where next_due_date <= today.
    """
    logger.info("⏰ Scheduler: processing due recurring rules...")
    try:
        from app.recurring.service import process_due_rules
        # No user_id: the nightly job is the one caller that legitimately
        # processes every user's rules.
        result = await process_due_rules()
        logger.info(
            f"✅ Scheduler: processed {result['processed']} rules, "
            f"created {result['created']} transactions, "
            f"errors: {result['errors']}"
        )
    except Exception as e:
        logger.error(f"❌ Scheduler: recurring rules job failed: {e}")


async def run_budget_alerts() -> None:
    """
    Daily job that checks all active budgets for threshold breaches.
    Runs at 8am every day so users get morning alerts.
    """
    logger.info("⏰ Scheduler: checking budget alerts...")
    try:
        from app.database      import supabase_admin
        from app.budgets.service import check_all_budgets_after_expense

        # Fetch all users who have active budgets
        result = (
            supabase_admin
            .table("budgets")
            .select("user_id")
            .eq("is_active", True)
            .execute()
        )

        # Get unique user IDs
        user_ids = list({
            row["user_id"]
            for row in (result.data or [])
        })

        for user_id in user_ids:
            await check_all_budgets_after_expense(user_id)

        logger.info(
            f"✅ Scheduler: checked budgets for {len(user_ids)} users"
        )
    except Exception as e:
        logger.error(f"❌ Scheduler: budget alerts job failed: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    """
    Configures and returns the scheduler with all jobs.

    Jobs:
      - process_recurring_rules: daily at 00:00 (midnight)
      - check_budget_alerts:     daily at 08:00 (morning)

    Timezone: UTC — Railway servers run in UTC.
    Your local time is UTC-6 (Mexico City).
    Midnight UTC = 6pm Mexico time.
    Adjust hour values if you prefer a different local time.
    """
    scheduler.add_job(
        run_recurring_rules,
        trigger  = CronTrigger(hour=0, minute=0),
        id       = "process_recurring_rules",
        name     = "Process Due Recurring Rules",
        replace_existing = True,
    )

    scheduler.add_job(
        run_budget_alerts,
        trigger  = CronTrigger(hour=8, minute=0),
        id       = "check_budget_alerts",
        name     = "Check Budget Alerts",
        replace_existing = True,
    )

    logger.info("📅 Scheduler configured with 2 jobs")
    return scheduler