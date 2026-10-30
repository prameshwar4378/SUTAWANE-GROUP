"""
Sutawane Classes Management Software - Real-Time Automated Cache Invalidation Signals.

Listens to ORM change events (post_save and post_delete) on critical ERP models
and triggers instant O(1) cache namespace invalidations.

Precaution for Production:
Every handler is wrapped in a fail-safe try/except block with error logging.
Database transactions and model saves are NEVER blocked or aborted if a cache
signal encounter an issue.
"""

import logging
from decimal import Decimal
from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    Payment,
    PaymentAllocation,
    Expense,
    StudentAdmission,
    Student,
    FeePlan,
    Installment,
    FeeDiscount,
    PreviousSessionDue,
    Branch,
    AcademicSession,
    SystemSetting,
    User,
)
from .cache_utils import (
    invalidate_financial_cache,
    invalidate_student_cache,
    invalidate_context_cache,
    invalidate_license_cache,
    invalidate_public_cache,
)

logger = logging.getLogger('MyApp.signals')


# -----------------------------------------------------------------------------
# Financial & Accounting Signals (Payments, Allocations, Expenses)
# -----------------------------------------------------------------------------

@receiver([post_save, post_delete], sender=Payment)
def on_payment_changed(sender, instance, **kwargs):
    """
    Triggered when a payment is recorded, reversed, or deleted.
    Instantly purges dashboard metrics, cash movement reports, student dues, and ledger caches.
    """
    try:
        invalidate_financial_cache()
    except Exception as exc:
        logger.warning("Error in Payment cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=PaymentAllocation)
def on_payment_allocation_changed(sender, instance, **kwargs):
    """
    Triggered when an installment payment allocation is created or adjusted.
    """
    try:
        invalidate_financial_cache()
    except Exception as exc:
        logger.warning("Error in PaymentAllocation cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=Expense)
def on_expense_changed(sender, instance, **kwargs):
    """
    Triggered when an expense is entered, edited, or deleted.
    Instantly purges dashboard KPI cards, expense summaries, and profit/loss reports.
    """
    try:
        invalidate_financial_cache()
    except Exception as exc:
        logger.warning("Error in Expense cache invalidation signal: %s", exc)


# -----------------------------------------------------------------------------
# Student & Fee Structure Signals (Admissions, FeePlans, Installments, Discounts)
# -----------------------------------------------------------------------------

@receiver([post_save, post_delete], sender=StudentAdmission)
def on_admission_changed(sender, instance, **kwargs):
    """
    Triggered when a student is admitted, promoted, or status changes.
    """
    try:
        invalidate_student_cache()
        invalidate_financial_cache()
        invalidate_public_cache()
    except Exception as exc:
        logger.warning("Error in StudentAdmission cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=Student)
def on_student_changed(sender, instance, **kwargs):
    """
    Triggered when student profile details (name, phone, roll number) are updated.
    """
    try:
        invalidate_student_cache()
    except Exception as exc:
        logger.warning("Error in Student cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=FeePlan)
@receiver([post_save, post_delete], sender=Installment)
@receiver([post_save, post_delete], sender=FeeDiscount)
@receiver([post_save, post_delete], sender=PreviousSessionDue)
def on_fee_structure_changed(sender, instance, **kwargs):
    """
    Triggered when fee plans, installment due dates, discounts, or previous dues change.
    """
    try:
        invalidate_financial_cache()
    except Exception as exc:
        logger.warning("Error in Fee structure cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=FeeDiscount)
def sync_fee_plan_on_discount_change(sender, instance, **kwargs):
    """
    Auto-healing synchronization: guarantees that whenever a FeeDiscount is added,
    modified, or deleted, FeePlan.total_discount and FeePlan.net_payable are mathematically refreshed.
    """
    try:
        if instance.fee_plan_id:
            fp = instance.fee_plan
            tot_disc = fp.discounts.aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')
            net = max(Decimal('0.00'), (fp.total_fees or Decimal('0.00')) - tot_disc)
            if fp.total_discount != tot_disc or fp.net_payable != net:
                fp.total_discount = tot_disc
                fp.net_payable = net
                fp.save(update_fields=['total_discount', 'net_payable', 'updated_at'])
    except Exception as exc:
        logger.warning("Error auto-syncing FeePlan discount totals in signal: %s", exc)


# -----------------------------------------------------------------------------
# Core Configuration & Context Signals (Branches, Sessions, Settings, Users)
# -----------------------------------------------------------------------------

@receiver([post_save, post_delete], sender=Branch)
def on_branch_changed(sender, instance, **kwargs):
    """
    Triggered when a branch center is created or updated.
    """
    try:
        invalidate_context_cache()
        invalidate_financial_cache()
        invalidate_public_cache()
    except Exception as exc:
        logger.warning("Error in Branch cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=AcademicSession)
def on_academic_session_changed(sender, instance, **kwargs):
    """
    Triggered when an academic session is created, activated, or adjusted.
    """
    try:
        invalidate_context_cache()
        invalidate_financial_cache()
    except Exception as exc:
        logger.warning("Error in AcademicSession cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=SystemSetting)
def on_system_setting_changed(sender, instance, **kwargs):
    """
    Triggered when system branding, institute name, logo, or license info is modified.
    """
    try:
        invalidate_context_cache()
        if instance.key and instance.key.startswith('license_'):
            invalidate_license_cache()
    except Exception as exc:
        logger.warning("Error in SystemSetting cache invalidation signal: %s", exc)


@receiver([post_save, post_delete], sender=User)
def on_user_changed(sender, instance, **kwargs):
    """
    Triggered when a user account, password, or permissions change.
    """
    try:
        invalidate_context_cache()
    except Exception as exc:
        logger.warning("Error in User cache invalidation signal: %s", exc)
