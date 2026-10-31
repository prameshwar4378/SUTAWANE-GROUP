"""
Multi-Session Student Account Statement & Batchwise Financial Ledger Aggregation Service.
Aggregates complete multi-session enrollments, batch fee plans, installment schedules,
payments audit trail, and historical dues into a unified, consolidated ledger payload.
"""

import os
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Student, StudentAdmission, SystemSetting, Payment
from .export_theme import get_logo_path

MONEY_ZERO = Decimal('0.00')


def get_system_settings_dict():
    """Retrieves institutional metadata from SystemSetting table with robust defaults."""
    defaults = {
        'institute_name': 'Sutawane Classes',
        'tagline': 'Excellence in Coaching & Board Preparations',
        'phone': '+91 98765 43210',
        'email': 'contact@sutawaneclasses.com',
        'address': 'Main Head Office, Maharashtra',
        'website': 'www.sutawaneclasses.com',
        'receipt_footer': 'Fees once paid are non-refundable. Thank you!',
    }
    try:
        settings_map = {s.key: s.value for s in SystemSetting.objects.all()}
        for k, v in settings_map.items():
            if v and v.strip():
                defaults[k] = v.strip()
    except Exception:
        pass
    return defaults


def resolve_student_photo_path(photo_url):
    """
    Resolves local filesystem path for a student's photo.
    Returns absolute path if file exists on disk, else None.
    """
    if not photo_url:
        return None
    clean_url = str(photo_url).strip()
    if clean_url.startswith('/media/'):
        rel = clean_url[len('/media/'):].replace('/', os.sep)
        disk_path = os.path.join(settings.MEDIA_ROOT, rel)
        if os.path.exists(disk_path):
            return disk_path
    elif os.path.isabs(clean_url) and os.path.exists(clean_url):
        return clean_url
    return None


def build_student_ledger_payload(student_id):
    """
    Constructs the complete multi-session and batchwise financial statement payload
    for the specified student ID.
    
    Structure:
    - student: dict of basic student bio and contacts
    - institute: dict of institute settings and logo
    - lifetime_summary: lifetime totals (agreed, paid, pending, clearance %)
    - sessions: list of academic session groups, each containing enrolled batches
    - previous_dues: list of historical carry-forward dues
    - payments_ledger: chronological audit trail of all receipts with running totals
    """
    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return None

    inst_settings = get_system_settings_dict()
    logo_path = get_logo_path()
    photo_disk_path = resolve_student_photo_path(student.photo_url)

    # Student Initials for fallback avatar
    name_parts = (student.full_name or 'S').strip().split()
    if len(name_parts) >= 2:
        initials = (name_parts[0][0] + name_parts[-1][0]).upper()
    elif name_parts:
        initials = name_parts[0][:2].upper()
    else:
        initials = "SC"

    # All admissions across ALL sessions, ordered chronologically
    admissions_qs = student.admissions.select_related(
        'branch', 'session', 'fee_plan'
    ).prefetch_related(
        'payments',
        'payments__allocations__installment',
        'fee_plan__installments',
        'fee_plan__installments__allocations__payment',
        'fee_plan__discounts'
    ).order_by('session__start_date', 'created_at')

    # All student payment receipts across all sessions (audit trail includes reversed/refunded)
    all_payments_qs = student.payments.exclude(
        receipt_number__startswith='STRESS-'
    ).exclude(
        notes__icontains='Capability testing dummy'
    ).select_related(
        'branch', 'session', 'admission', 'admission__session', 'previous_due', 'reversed_by'
    ).prefetch_related(
        'allocations__installment'
    ).order_by('payment_date', 'created_at')

    all_payments = list(all_payments_qs)

    # Previous dues across all sessions
    all_previous_dues = list(student.previous_dues.select_related('original_session', 'current_session').all())

    # Build Session -> Batches grouping
    sessions_dict = {}
    total_admission_payable = MONEY_ZERO
    total_admission_paid = MONEY_ZERO

    for adm in admissions_qs:
        session = adm.session
        s_id = str(session.id)
        if s_id not in sessions_dict:
            sessions_dict[s_id] = {
                'session_id': session.id,
                'session_name': session.display_name or session.name,
                'session_code': session.name,
                'is_current': session.is_current,
                'start_date': session.start_date,
                'batches': [],
                'total_payable': MONEY_ZERO,
                'total_paid': MONEY_ZERO,
                'total_pending': MONEY_ZERO,
            }

        fp = getattr(adm, 'fee_plan', None)
        adm_payable = fp.net_payable if (fp and fp.net_payable) else MONEY_ZERO
        total_fees = fp.total_fees if (fp and fp.total_fees) else MONEY_ZERO
        total_discount = fp.total_discount if (fp and fp.total_discount) else MONEY_ZERO

        # Payments explicitly tied to this admission
        adm_payments_list = [p for p in adm.payments.all() if not p.is_reversed]
        adm_paid = sum((p.total_amount for p in adm_payments_list), MONEY_ZERO)
        adm_pending = max(MONEY_ZERO, adm_payable - adm_paid)

        total_admission_payable += adm_payable
        total_admission_paid += adm_paid

        # Installments
        installments_list = []
        if fp:
            for inst in sorted(fp.installments.all(), key=lambda x: x.installment_no):
                inst_paid = sum((a.allocated_amount for a in inst.allocations.all() if not a.payment.is_reversed), MONEY_ZERO)
                inst_pending = max(MONEY_ZERO, inst.amount_due - inst_paid)
                is_cleared = (inst_pending <= 0) or (adm_pending <= 0)
                status = 'PAID' if is_cleared else inst.status
                installments_list.append({
                    'id': inst.id,
                    'installment_no': inst.installment_no,
                    'label': inst.label,
                    'due_date': inst.due_date,
                    'amount_due': inst.amount_due,
                    'paid_amount': inst_paid,
                    'pending_amount': inst_pending,
                    'status': status,
                    'is_cleared': is_cleared,
                })

        # Discounts
        discounts_list = []
        if fp:
            for disc in fp.discounts.all():
                discounts_list.append({
                    'reason': disc.reason,
                    'amount': disc.amount,
                    'approved_date': disc.approved_date,
                    'notes': disc.notes or '',
                })

        # Payments for this batch
        batch_payments = []
        for p in sorted(adm_payments_list, key=lambda x: x.payment_date):
            alloc_notes = []
            for alloc in p.allocations.all():
                alloc_notes.append(f"{alloc.installment.label}: Rs.{int(alloc.allocated_amount)}")
            batch_payments.append({
                'id': p.id,
                'receipt_number': p.receipt_number,
                'payment_date': p.payment_date,
                'payment_mode': p.get_payment_mode_display(),
                'reference_number': p.reference_number or '-',
                'received_by': p.received_by_display,
                'received_by_role': p.received_by_role_display,
                'amount': p.total_amount,
                'notes': p.notes or '',
                'allocations_summary': ', '.join(alloc_notes) if alloc_notes else 'General Fee Payment',
            })

        batch_clearance_pct = round((adm_paid / adm_payable * 100), 1) if adm_payable > 0 else 100.0
        batch_status = 'CLEARED' if adm_pending <= 0 else ('PARTIAL' if adm_paid > 0 else 'UNPAID')

        batch_info = {
            'admission_id': adm.id,
            'standard': adm.standard,
            'roll_number': adm.roll_number,
            'branch_name': adm.branch.name if adm.branch else 'Main Campus',
            'branch_code': adm.branch.code if adm.branch else 'MC',
            'is_active': adm.is_active,
            'admission_date': adm.admission_date,
            'total_fees': total_fees,
            'total_discount': total_discount,
            'net_payable': adm_payable,
            'paid_amount': adm_paid,
            'pending_amount': adm_pending,
            'clearance_percentage': batch_clearance_pct,
            'status': batch_status,
            'installments': installments_list,
            'discounts': discounts_list,
            'payments': batch_payments,
        }

        sessions_dict[s_id]['batches'].append(batch_info)
        sessions_dict[s_id]['total_payable'] += adm_payable
        sessions_dict[s_id]['total_paid'] += adm_paid
        sessions_dict[s_id]['total_pending'] += adm_pending

    # Finalize session totals & clearance rates
    sessions_list = list(sessions_dict.values())
    for s_grp in sessions_list:
        s_payable = s_grp['total_payable']
        s_paid = s_grp['total_paid']
        s_grp['clearance_percentage'] = round((s_paid / s_payable * 100), 1) if s_payable > 0 else 100.0
        s_grp['status'] = 'CLEARED' if s_grp['total_pending'] <= 0 else ('PARTIAL' if s_paid > 0 else 'UNPAID')

    # Previous session dues processing
    previous_dues_list = []
    total_prev_outstanding = MONEY_ZERO
    total_prev_collected = MONEY_ZERO

    for due in all_previous_dues:
        out_amt = due.outstanding_amount or MONEY_ZERO
        col_amt = due.collected_amount or MONEY_ZERO
        due_pend = max(MONEY_ZERO, out_amt - col_amt)
        total_prev_outstanding += out_amt
        total_prev_collected += col_amt
        previous_dues_list.append({
            'id': due.id,
            'original_session': due.original_session.display_name or due.original_session.name,
            'current_session': due.current_session.display_name or due.current_session.name,
            'outstanding_amount': out_amt,
            'collected_amount': col_amt,
            'pending_amount': due_pend,
            'description': due.description or 'Historical fee balance carried forward',
            'status': 'CLEARED' if due_pend <= 0 else ('PARTIAL' if col_amt > 0 else 'PENDING'),
        })

    # Consolidated Lifetime Financials (Synchronized single-source-of-truth)
    lifetime_agreed = total_admission_payable + total_prev_outstanding
    lifetime_paid = total_admission_paid + total_prev_collected
    lifetime_pending = max(MONEY_ZERO, lifetime_agreed - lifetime_paid)
    lifetime_clearance_pct = round((lifetime_paid / lifetime_agreed * 100), 1) if lifetime_agreed > 0 else 100.0

    if lifetime_pending <= 0 and lifetime_agreed > 0:
        status_label = "FULLY CLEARED"
        status_color = "emerald"
    elif lifetime_paid > 0:
        status_label = "PARTIALLY PAID"
        status_color = "amber"
    else:
        status_label = "FEES UNPAID"
        status_color = "rose"

    # All-time receipts chronological ledger with running total
    payments_ledger = []
    running_sum = MONEY_ZERO
    for idx, p in enumerate(all_payments, start=1):
        if not p.is_reversed:
            running_sum += p.total_amount
        sess_name = p.session.display_name if p.session else (p.admission.session.display_name if p.admission and p.admission.session else '-')
        batch_std = p.admission.standard if p.admission else ('Previous Due' if p.previous_due else 'Direct Payment')
        br_name = p.branch.name if p.branch else (p.admission.branch.name if p.admission and p.admission.branch else '-')
        
        alloc_items = []
        for alloc in p.allocations.all():
            alloc_items.append(f"{alloc.installment.label}: Rs.{int(alloc.allocated_amount)}")

        payments_ledger.append({
            'index': idx,
            'receipt_number': p.receipt_number,
            'payment_date': p.payment_date,
            'session_name': sess_name,
            'standard': batch_std,
            'branch_name': br_name,
            'payment_mode': p.get_payment_mode_display(),
            'reference_number': p.reference_number or '-',
            'received_by': p.received_by_display,
            'received_by_role': p.received_by_role_display,
            'amount': p.total_amount,
            'running_total': running_sum,
            'is_reversed': p.is_reversed,
            'reversal_reason': p.reversal_reason or '',
            'reversed_at': p.reversed_at,
            'reversed_by': p.reversed_by.name if p.reversed_by else '',
            'allocations_summary': ', '.join(alloc_items) if alloc_items else ('Refunded / Returned' if p.is_reversed else 'General Collection'),
            'notes': p.notes or '',
        })

    # Primary branch from active admission or first admission
    primary_branch = None
    active_adm = admissions_qs.filter(is_active=True).first() or admissions_qs.last()
    if active_adm and active_adm.branch:
        primary_branch = active_adm.branch.name

    payload = {
        'student': {
            'id': student.id,
            'student_code': student.student_code,
            'full_name': student.full_name,
            'parent_phone': student.parent_phone,
            'student_phone': student.student_phone or '-',
            'address': student.address or '-',
            'date_of_birth': student.date_of_birth,
            'photo_url': student.photo_url,
            'photo_disk_path': photo_disk_path,
            'initials': initials,
            'primary_branch': primary_branch or 'Main Campus',
        },
        'institute': {
            'name': inst_settings.get('institute_name', 'Sutawane Classes'),
            'tagline': inst_settings.get('tagline', 'Excellence in Coaching & Board Preparations'),
            'phone': inst_settings.get('phone', '+91 98765 43210'),
            'email': inst_settings.get('email', 'contact@sutawaneclasses.com'),
            'address': inst_settings.get('address', 'Main Head Office, Maharashtra'),
            'website': inst_settings.get('website', 'www.sutawaneclasses.com'),
            'receipt_footer': inst_settings.get('receipt_footer', 'Fees once paid are non-refundable. Thank you!'),
            'logo_path': logo_path,
        },
        'generated_at': timezone.localtime(),
        'generated_at_str': timezone.localtime().strftime('%d %b %Y, %I:%M %p'),
        'lifetime_summary': {
            'agreed_fees': lifetime_agreed,
            'paid_fees': lifetime_paid,
            'pending_fees': lifetime_pending,
            'clearance_percentage': lifetime_clearance_pct,
            'status_label': status_label,
            'status_color': status_color,
            'total_sessions_count': len(sessions_list),
            'total_batches_count': admissions_qs.count(),
            'total_receipts_count': len(all_payments),
            'previous_dues_total': total_prev_outstanding,
            'previous_dues_collected': total_prev_collected,
            'previous_dues_pending': max(MONEY_ZERO, total_prev_outstanding - total_prev_collected),
        },
        'sessions': sessions_list,
        'previous_dues': previous_dues_list,
        'payments_ledger': payments_ledger,
    }

    return payload
