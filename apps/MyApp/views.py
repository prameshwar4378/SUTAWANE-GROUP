import os
import re
import uuid
import json
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timezone as dt_timezone, timedelta
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.conf import settings
from django.core.paginator import Paginator

from .models import (
    Branch, AcademicSession, Student, StudentAdmission,
    FeePlan, Installment, Payment, Expense, ExpenseCategory, ExpenseAttachment,
    Course, User, SystemSetting,
    PaymentAllocation, FeeDiscount, PreviousSessionDue, ReceiptCounter
)
from .auth_utils import (
    hash_password, verify_password, get_license_status,
    generate_and_send_developer_otp, verify_developer_otp,
    AUTHORIZED_DEVELOPER_EMAIL
)
from .whatsapp import (
    format_whatsapp_number, generate_whatsapp_url,
    build_receipt_whatsapp_message, build_fee_reminder_whatsapp_message,
    build_admission_whatsapp_message, build_general_notice_whatsapp_message
)
from .dues_export import export_dues_to_excel, export_dues_to_pdf
from .expenses_export import export_expenses_to_excel, export_expenses_to_pdf
from .students_export import export_students_to_excel, export_students_to_pdf
from .payments_export import export_payments_to_excel, export_payments_to_pdf
import calendar
from .reports_export import (
    export_session_audit_excel,
    export_session_audit_pdf,
    export_payment_modes_excel,
    export_payment_modes_pdf,
    export_expense_categories_excel,
    export_expense_categories_pdf,
    export_statement_excel,
    export_statement_pdf,
)
from .backup_service import (
    get_storage_paths, get_dir_stats, format_bytes,
    create_full_backup_snapshot, execute_restore_from_file,
    list_backups, delete_backup,
)

SYSTEM_ADMIN_ROLES = {'CLASS_OWNER', 'DEVELOPER', 'SUPER_ADMIN'}
MONEY_QUANTUM = Decimal('0.01')
MONEY_ZERO = Decimal('0.00')


def parse_non_negative_money(raw_value, *, default=MONEY_ZERO, allow_blank=True):
    """Parse a form money value without accepting malformed or negative input."""
    value = '' if raw_value is None else str(raw_value).strip()
    if not value:
        if allow_blank:
            return default
        raise ValueError('A monetary amount is required.')
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a valid monetary amount.')
    if not amount.is_finite() or amount < 0:
        raise ValueError('Monetary amounts cannot be negative.')
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def parse_form_date(value, *, default=None):
    """Parse a date-only form value into an aware midnight datetime."""
    value = (value or '').strip()
    if not value:
        return default
    try:
        return timezone.make_aware(datetime.strptime(value, '%Y-%m-%d'))
    except (TypeError, ValueError):
        raise ValueError('Enter a valid date in YYYY-MM-DD format.')


def can_manage_system(request):
    """Return whether the authenticated account may change system data."""
    current_user = getattr(request, 'current_user', None)
    return bool(current_user and current_user.role in SYSTEM_ADMIN_ROLES)



# -------------------------------------------------------------------
# Authentication Views (Login, Logout, Developer OTP)
# -------------------------------------------------------------------

def landing_view(request):
    """Public product introduction; private application routes remain below."""
    user_id = request.session.get('user_id')
    if user_id:
        user = User.objects.filter(id=user_id, is_active=True).first()
        if user:
            if user.is_developer:
                return redirect('developer_portal')
            return redirect('dashboard')
    return render(request, 'landing.html')


def public_batches_view(request):
    """Public Showcase of Batches & Structured Academic Programs."""
    return render(request, 'batches.html')


def public_photo_gallery_view(request):
    """Public Showcase of Campus & Achievement Photos."""
    return render(request, 'photo_gallery.html')


def public_video_gallery_view(request):
    """Public Showcase of Video Lectures & Topper Interviews."""
    return render(request, 'video_gallery.html')


def public_about_us_view(request):
    """Public Showcase of Institutional Heritage, Director Vision & Faculty."""
    return render(request, 'about_us.html')


def public_contact_us_view(request):
    """Public Contact Desk & Campus Directory."""
    return render(request, 'contact_us.html')

def login_view(request):
    """
    User & Developer Authentication matching React LoginPage.tsx.
    """
    # If already logged in, redirect to workspace or developer portal
    user_id = request.session.get('user_id')
    if user_id:
        user = User.objects.filter(id=user_id, is_active=True).first()
        if user:
            if user.is_developer:
                return redirect('developer_portal')
            return redirect('dashboard')

    requested_next = request.GET.get('next') or request.POST.get('next') or '/app/'
    next_url = requested_next if url_has_allowed_host_and_scheme(
        requested_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ) else '/app/'
    license_status = get_license_status()

    if request.method == 'POST':
        login_type = request.POST.get('login_type', 'owner')

        # 1. CLASS OWNER PASSWORD LOGIN
        if login_type == 'owner':
            username = request.POST.get('username', '').strip().lower()
            password = request.POST.get('password', '')

            if not username or not password:
                return render(request, 'login.html', {
                    'error_msg': 'Please enter both username and password.',
                    'license': license_status,
                    'entered_username': username,
                    'next_url': next_url,
                })

            user = User.objects.filter(username=username).first()
            if not user or not verify_password(password, user.password, user.salt):
                return render(request, 'login.html', {
                    'error_msg': 'Invalid username or password.',
                    'license': license_status,
                    'entered_username': username,
                    'next_url': next_url,
                })

            if not user.is_active:
                return render(request, 'login.html', {
                    'error_msg': 'Your user account has been disabled. Please contact the developer.',
                    'license': license_status,
                    'entered_username': username,
                    'next_url': next_url,
                })

            # Developer is prohibited from password login
            if user.is_developer:
                return render(request, 'login.html', {
                    'error_msg': 'Developer password login is disabled. Please switch to the "Developer (OTP)" tab to authenticate with your verified email.',
                    'license': license_status,
                    'entered_username': username,
                    'next_url': next_url,
                })

            # Check license block for class owner
            if not license_status['isActive'] or license_status['isExpired']:
                return render(request, 'login.html', {
                    'error_msg': 'Software subscription plan is expired or inactive. Call support team to renew your subscription.',
                    'license': license_status,
                    'entered_username': username,
                    'next_url': next_url,
                })

            # Log user in
            request.session['user_id'] = str(user.id)
            request.session['user_role'] = user.role
            request.session['user_name'] = user.name
            messages.success(request, f"Welcome back, {user.name}!")
            return redirect(next_url)

        # 2. DEVELOPER OTP LOGIN
        elif login_type == 'developer':
            email = request.POST.get('email', '').strip().lower()
            otp_code = request.POST.get('otp_code', '').strip()

            if not email or not otp_code:
                return render(request, 'login.html', {
                    'error_msg': 'Please enter your developer email and the 6-digit verification code.',
                    'license': license_status,
                    'entered_email': email,
                    'next_url': next_url,
                    'active_tab': 'developer',
                })

            success, msg = verify_developer_otp(email, otp_code)
            if not success:
                return render(request, 'login.html', {
                    'error_msg': msg,
                    'license': license_status,
                    'entered_email': email,
                    'next_url': next_url,
                    'active_tab': 'developer',
                })

            # Developer verified, fetch or ensure developer user exists
            dev_user = User.objects.filter(role='DEVELOPER').first()
            if not dev_user:
                dev_hash, dev_salt = hash_password('developer@123')
                dev_user = User.objects.create(
                    username='developer',
                    name='Software Developer',
                    password=dev_hash,
                    salt=dev_salt,
                    role='DEVELOPER',
                    is_active=True,
                )

            request.session['user_id'] = str(dev_user.id)
            request.session['user_role'] = dev_user.role
            request.session['user_name'] = dev_user.name
            messages.success(request, "Developer authentication successful. Access granted.")
            explicit_next = request.POST.get('next', '').strip() or request.GET.get('next', '').strip()
            target_url = explicit_next if explicit_next and explicit_next not in ('/login/', '/app/') else 'developer_portal'
            return redirect(target_url)

    return render(request, 'login.html', {
        'license': license_status,
        'next_url': next_url,
        'active_tab': request.GET.get('tab', 'owner'),
    })


def logout_view(request):
    """
    Clears session and logs user out.
    """
    request.session.flush()
    messages.info(request, "You have been safely signed out.")
    return redirect('login')


@require_POST
def api_developer_send_otp_view(request):
    """
    Dispatches single-use OTP code to authorized developer email.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
        email = body.get('email', '').strip()
    except Exception:
        email = request.POST.get('email', '').strip()

    if not email:
        return JsonResponse({'success': False, 'error': 'Developer email is required.'})

    success, code, msg = generate_and_send_developer_otp(email)
    if success:
        return JsonResponse({'success': True, 'message': msg})
    return JsonResponse({'success': False, 'error': msg})


@require_POST
def api_developer_verify_otp_view(request):
    """
    Asynchronously verifies developer OTP and authenticates developer session.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
        email = body.get('email', '').strip().lower()
        otp_code = str(body.get('otp_code', '')).strip()
        next_url = body.get('next', '').strip()
    except Exception:
        email = request.POST.get('email', '').strip().lower()
        otp_code = str(request.POST.get('otp_code', '')).strip()
        next_url = request.POST.get('next', '').strip()

    if not email or not otp_code:
        return JsonResponse({'success': False, 'error': 'Please enter both developer email and 6-digit verification code.'})

    success, msg = verify_developer_otp(email, otp_code)
    if not success:
        return JsonResponse({'success': False, 'error': msg})

    # Ensure developer user exists
    dev_user = User.objects.filter(role='DEVELOPER').first()
    if not dev_user:
        dev_hash, dev_salt = hash_password('developer@123')
        dev_user = User.objects.create(
            username='developer',
            name='Software Developer',
            password=dev_hash,
            salt=dev_salt,
            role='DEVELOPER',
            is_active=True,
        )

    request.session['user_id'] = str(dev_user.id)
    request.session['user_role'] = dev_user.role
    request.session['user_name'] = dev_user.name
    messages.success(request, "Developer authentication successful. Access granted.")

    redirect_url = next_url if next_url and next_url != '/login/' else '/developer-portal/'
    return JsonResponse({
        'success': True,
        'message': 'Developer authentication successful.',
        'redirect_url': redirect_url
    })


# -------------------------------------------------------------------
# Developer Management Portal
# -------------------------------------------------------------------

def developer_portal_view(request):
    """
    Super-administrative Developer Portal matching React DeveloperPortalPage.tsx.
    Restricted strictly to authenticated DEVELOPER role.
    """
    user_id = request.session.get('user_id')
    current_user = User.objects.filter(id=user_id, role='DEVELOPER', is_active=True).first()
    if not current_user:
        messages.error(request, "Access Denied: Developer privileges required.")
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Update License Validity / Status
        if action == 'update_license':
            is_active_val = request.POST.get('is_active') == 'true'
            developer_note = request.POST.get('developer_note', '').strip()
            expiry_date_input = request.POST.get('expiry_date')
            extend_days = request.POST.get('extend_days')

            # Calculate expiry
            if extend_days:
                days = int(extend_days)
                new_expiry = timezone.now() + timedelta(days=days)
                expiry_str = new_expiry.strftime('%Y-%m-%d %H:%M:%S.%f')
            elif expiry_date_input:
                expiry_str = f"{expiry_date_input} 23:59:59.000000"
            else:
                expiry_str = None

            if expiry_str:
                SystemSetting.objects.update_or_create(
                    key='license_expiry_date',
                    defaults={'value': expiry_str}
                )

            SystemSetting.objects.update_or_create(
                key='license_is_active',
                defaults={'value': 'true' if is_active_val else 'false'}
            )

            if developer_note:
                SystemSetting.objects.update_or_create(
                    key='license_developer_note',
                    defaults={'value': developer_note}
                )

            messages.success(request, "Software license configuration updated successfully.")
            return redirect('developer_portal')

        # 2. Reset User Password
        elif action == 'reset_password':
            target_user_id = request.POST.get('user_id')
            new_password = request.POST.get('new_password', '').strip()

            target_user = get_object_or_404(User, id=target_user_id)
            if new_password:
                new_hash, new_salt = hash_password(new_password)
                target_user.password = new_hash
                target_user.salt = new_salt
                target_user.save()
                messages.success(request, f"Password successfully reset for @{target_user.username}!")
            return redirect('developer_portal')

    # Gather data for Developer Portal
    license_status = get_license_status()
    all_users = User.objects.all().order_by('role', 'username')

    stats = {
        'students_count': Student.objects.count(),
        'admissions_count': StudentAdmission.objects.count(),
        'payments_count': Payment.objects.count(),
        'expenses_count': Expense.objects.count(),
        'courses_count': Course.objects.count(),
        'branches_count': Branch.objects.count(),
    }

    context = {
        'license': license_status,
        'users': all_users,
        'stats': stats,
    }
    return render(request, 'developer_portal.html', context)


# -------------------------------------------------------------------
# Dashboard & Core Workspace Views
# -------------------------------------------------------------------

def format_relative_activity_time(dt):
    """Formats an activity datetime to a relative human-readable label."""
    if not dt:
        return ''
    now = timezone.localtime()
    dt_local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    diff_sec = int((now - dt_local).total_seconds())
    diff_min = diff_sec // 60
    time_str = dt_local.strftime('%I:%M %p')

    if 0 <= diff_sec < 60:
        return 'Just now'
    if 1 <= diff_min < 60:
        return f"{diff_min}m ago ({time_str})"
    if dt_local.date() == now.date():
        return f"Today at {time_str}"
    if dt_local.date() == (now.date() - timedelta(days=1)):
        return f"Yesterday at {time_str}"
    return dt_local.strftime('%d %b %Y • %I:%M %p')


def clean_referer_url(referer, strip_params=None):
    """
    Cleans URL parameters (such as branch_id, session_id, page) from referer URL
    so that switching branch/session doesn't carry over stale in-page GET filters.
    """
    if not referer:
        return '/app/'
    try:
        parsed = urlparse(referer)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if strip_params:
            for p in strip_params:
                qs.pop(p, None)
        new_query = urlencode(qs, doseq=True)
        path = parsed.path
        if path == '/' or not path:
            path = '/app/'
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, new_query, parsed.fragment))
    except Exception:
        return '/app/'


def get_active_scope(request):
    """
    Centralized data isolation resolver across the entire application.
    Resolves currently active (branch_id, session_id, active_branch, active_session).

    Precedence & Isolation Rules:
    1. If branch_id is provided in GET, use it. Otherwise, read request.session['selected_branch_id'] (default 'ALL').
       If branch_id != 'ALL', validates that the branch exists and is active.
    2. If session_id is provided in GET, use it. Otherwise, read request.session['selected_session_id'].
       If no session is in cookies, default to the current active session (or 'ALL' if none).
       If session_id != 'ALL', validates that the academic session exists.
    3. Returns:
       (branch_id, session_id, active_branch, active_session)
       - branch_id: 'ALL' or str(uuid)
       - session_id: 'ALL' or str(uuid)
       - active_branch: Branch instance or None
       - active_session: AcademicSession instance or None
    """
    # 1. Branch Resolution
    branch_id = request.GET.get('branch_id')
    if branch_id is None:
        branch_id = request.session.get('selected_branch_id', 'ALL')

    active_branch = None
    if branch_id and branch_id != 'ALL':
        active_branch = Branch.objects.filter(id=branch_id, is_active=True).first()
        if not active_branch:
            branch_id = 'ALL'

    # 2. Session Resolution
    session_id = request.GET.get('session_id')
    if session_id is None or session_id == 'CURRENT':
        session_id = request.session.get('selected_session_id')
        if not session_id:
            curr = AcademicSession.objects.filter(is_current=True, isActive=True).first()
            if curr:
                session_id = str(curr.id)
                request.session['selected_session_id'] = session_id
            else:
                session_id = 'ALL'

    active_session = None
    if session_id and session_id != 'ALL':
        active_session = AcademicSession.objects.filter(id=session_id).first()
        if not active_session:
            curr = AcademicSession.objects.filter(is_current=True, isActive=True).first()
            if curr:
                session_id = str(curr.id)
                active_session = curr
                request.session['selected_session_id'] = session_id
            else:
                session_id = 'ALL'

    return branch_id, session_id, active_branch, active_session


def dashboard_view(request):
    """
    Main Executive Dashboard View.
    100% visual and logical parity with React DashboardPage.tsx:
    - Scope Banner & Fast Action Buttons
    - Row 1: Today's Financial Movement (Collections, Expenses, Net Liquid, Overdue Dues)
    - Row 2: Session Cumulative Macro Metrics (Expected Fees, Collected, Outstanding, Active Students)
    - Row 3: Monthly Financial Trend Chart (Past 6 Months Collections vs Expenses) & Live Activity Feed
    - Row 4: Multi-Branch Performance Comparison (when All Branches selected)
    """
    # 1. Resolve Active Scope (Branch & Session)
    selected_branch_id, selected_session_id, active_branch, active_session = get_active_scope(request)

    is_all_branches = (selected_branch_id == 'ALL')
    is_all_sessions = (selected_session_id == 'ALL')

    # 2. Base Querysets with Scope Isolation
    admissions_qs = StudentAdmission.objects.filter(is_active=True).select_related('student', 'branch', 'session', 'fee_plan')
    payments_qs = Payment.objects.filter(is_reversed=False).select_related('student', 'branch', 'session')
    expenses_qs = Expense.objects.select_related('category', 'branch').all()

    if not is_all_branches:
        admissions_qs = admissions_qs.filter(branch_id=selected_branch_id)
        payments_qs = payments_qs.filter(branch_id=selected_branch_id)
        expenses_qs = expenses_qs.filter(branch_id=selected_branch_id)

    if not is_all_sessions and active_session:
        admissions_qs = admissions_qs.filter(session_id=active_session.id)
        payments_qs = payments_qs.filter(session_id=active_session.id)
        if active_session.start_date and active_session.end_date:
            expenses_qs = expenses_qs.filter(expense_date__range=[active_session.start_date, active_session.end_date])

    now = timezone.localtime()
    today_date = now.date()

    # 3. Today's Inflows, Outflows & Net Movement
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    today_payments = payments_qs.filter(payment_date__range=[start_of_today, end_of_today])
    today_collections = sum(p.total_amount for p in today_payments)

    today_expenses_list = expenses_qs.filter(expense_date__range=[start_of_today, end_of_today])
    today_expenses = sum(e.amount for e in today_expenses_list)
    today_net_movement = today_collections - today_expenses

    # 4. Month's Inflows, Outflows & Net Movement
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_m = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    end_of_month = (next_m - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

    month_payments = payments_qs.filter(payment_date__range=[start_of_month, end_of_month])
    month_collections = sum(p.total_amount for p in month_payments)

    month_expenses_list = expenses_qs.filter(expense_date__range=[start_of_month, end_of_month])
    month_expenses = sum(e.amount for e in month_expenses_list)
    month_net_movement = month_collections - month_expenses

    # 5. Session Cumulative Macro Metrics
    active_students_count = admissions_qs.count()
    total_expected_fees = sum(
        adm.fee_plan.net_payable for adm in admissions_qs if hasattr(adm, 'fee_plan')
    )
    # Fee-plan collection metrics must exclude payments made against carried-forward
    # previous-session dues. Those receipts are cash movement, but not current
    # admission fee collections.
    current_fee_payments_qs = payments_qs.filter(
        admission__isnull=False,
        admission__session_id=active_session.id if active_session and not is_all_sessions else None,
    ) if active_session and not is_all_sessions else payments_qs.filter(admission__isnull=False)
    total_collected_fees = sum(p.total_amount for p in current_fee_payments_qs)
    total_pending_fees = max(MONEY_ZERO, total_expected_fees - total_collected_fees)

    # 6. Installments Due Today & Overdue Dues
    due_today_count = 0
    due_today_amount = MONEY_ZERO
    overdue_count = 0
    overdue_amount = MONEY_ZERO

    installments = Installment.objects.filter(
        fee_plan__admission__in=admissions_qs
    ).select_related('fee_plan').prefetch_related('allocations__payment')

    for inst in installments:
        paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
        bal = max(MONEY_ZERO, inst.amount_due - paid)
        if bal > 0 and inst.due_date:
            inst_date = timezone.localtime(inst.due_date).date()
            if inst_date == today_date:
                due_today_count += 1
                due_today_amount += bal
            elif inst_date < today_date:
                overdue_count += 1
                overdue_amount += bal

    # 7. Monthly Financial Trend (Past 6 Months)
    monthly_trend = []
    max_trend_val = 1.0

    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1

        m_start = timezone.make_aware(datetime(year, month, 1, 0, 0, 0))
        if month == 12:
            next_month_start = timezone.make_aware(datetime(year + 1, 1, 1, 0, 0, 0))
        else:
            next_month_start = timezone.make_aware(datetime(year, month + 1, 1, 0, 0, 0))
        m_end = next_month_start - timedelta(microseconds=1)

        m_label = m_start.strftime('%b %y')

        m_coll_filter = Payment.objects.filter(is_reversed=False, payment_date__range=[m_start, m_end])
        m_exp_filter = Expense.objects.filter(expense_date__range=[m_start, m_end])

        if not is_all_branches:
            m_coll_filter = m_coll_filter.filter(branch_id=selected_branch_id)
            m_exp_filter = m_exp_filter.filter(branch_id=selected_branch_id)

        if not is_all_sessions and active_session:
            m_coll_filter = m_coll_filter.filter(session_id=active_session.id)

        m_coll = sum(p.total_amount for p in m_coll_filter)
        m_exp = sum(e.amount for e in m_exp_filter)
        max_trend_val = max(float(max_trend_val), float(m_coll), float(m_exp))

        monthly_trend.append({
            'month': m_label,
            'month_short': m_start.strftime('%b'),
            'month_full': m_start.strftime('%B %Y'),
            'collections': float(m_coll),
            'expenses': float(m_exp),
            'net': float(m_coll - m_exp),
        })

    trend_total_collections = sum(m['collections'] for m in monthly_trend)
    trend_total_expenses = sum(m['expenses'] for m in monthly_trend)
    trend_net_movement = trend_total_collections - trend_total_expenses
    trend_has_data = (trend_total_collections > 0 or trend_total_expenses > 0)

    # Normalized percentages for responsive SVG/CSS chart
    max_trend_float = float(max_trend_val) if max_trend_val else 1.0
    for mt in monthly_trend:
        mt['coll_pct'] = round((mt['collections'] / max_trend_float) * 85, 1) if max_trend_float > 0 else 0
        mt['exp_pct'] = round((mt['expenses'] / max_trend_float) * 85, 1) if max_trend_float > 0 else 0

    # 8. Live Recent Transactions Feed (Latest 10 Actions)
    recent_payments = Payment.objects.select_related('student', 'branch').all()
    recent_expenses = Expense.objects.select_related('category', 'branch').all()

    if not is_all_branches:
        recent_payments = recent_payments.filter(branch_id=selected_branch_id)
        recent_expenses = recent_expenses.filter(branch_id=selected_branch_id)

    if not is_all_sessions and active_session:
        recent_payments = recent_payments.filter(session_id=active_session.id)

    recent_payments = recent_payments.order_by('-created_at')[:15]
    recent_expenses = recent_expenses.order_by('-created_at')[:15]

    merged_activity = []
    for p in recent_payments:
        act_dt = p.reversed_at if (p.is_reversed and p.reversed_at) else (p.created_at or p.payment_date)
        merged_activity.append({
            'id': p.id,
            'type': 'FEE_REVERSAL' if p.is_reversed else 'FEE_COLLECTION',
            'title': f"Fee Reversed: {p.student.full_name}" if p.is_reversed else f"Fee: {p.student.full_name}",
            'subtitle': f"Receipt: {p.receipt_number} ({p.payment_mode}) • {p.reversal_reason}" if p.is_reversed else f"Receipt: {p.receipt_number} ({p.payment_mode})",
            'amount': p.total_amount,
            'timestamp': act_dt,
            'time_display': format_relative_activity_time(act_dt),
            'branch_name': p.branch.name if p.branch else 'Main Center',
            'payment_mode': p.payment_mode,
            'student_id': p.student_id,
            'is_income': not p.is_reversed,
            'is_reversed': p.is_reversed,
        })

    for e in recent_expenses:
        act_dt = e.created_at or e.expense_date
        merged_activity.append({
            'id': e.id,
            'type': 'EXPENSE',
            'title': f"Expense: {e.description}",
            'subtitle': f"Category: {e.category.name if e.category else 'General'} ({e.payment_mode}{(' • ' + e.vendor) if e.vendor else ''})",
            'amount': e.amount,
            'timestamp': act_dt,
            'time_display': format_relative_activity_time(act_dt),
            'branch_name': e.branch.name if e.branch else 'Main Center',
            'payment_mode': e.payment_mode,
            'student_id': None,
            'is_income': False,
            'is_reversed': False,
        })

    merged_activity.sort(key=lambda x: x['timestamp'] or timezone.now(), reverse=True)
    recent_transactions = merged_activity[:10]

    # 9. Multi-Branch Consolidated Performance Comparison
    branch_comparison = []
    if is_all_branches:
        active_branches = Branch.objects.filter(is_active=True).order_by('name')
        for b in active_branches:
            b_adms = StudentAdmission.objects.filter(branch=b, is_active=True)
            if not is_all_sessions and active_session:
                b_adms = b_adms.filter(session=active_session)
            b_expected = sum(adm.fee_plan.net_payable for adm in b_adms if hasattr(adm, 'fee_plan'))

            b_payments = Payment.objects.filter(branch=b, is_reversed=False)
            if not is_all_sessions and active_session:
                b_payments = b_payments.filter(session=active_session)
            b_collections = sum(p.total_amount for p in b_payments)

            b_expenses_q = Expense.objects.filter(branch=b)
            if not is_all_sessions and active_session and active_session.start_date and active_session.end_date:
                b_expenses_q = b_expenses_q.filter(expense_date__range=[active_session.start_date, active_session.end_date])
            b_expenses = sum(e.amount for e in b_expenses_q)

            branch_comparison.append({
                'branch_id': b.id,
                'branch_name': b.name,
                'branch_code': b.code,
                'active_students': b_adms.count(),
                'total_collections': b_collections,
                'total_expenses': b_expenses,
                'net_movement': b_collections - b_expenses,
                'pending_dues': max(MONEY_ZERO, b_expected - b_collections),
            })

    context = {
        'today': {
            'collections': today_collections,
            'expenses': today_expenses,
            'net_movement': today_net_movement,
            'transaction_count': today_payments.count() + today_expenses_list.count(),
        },
        'month': {
            'collections': month_collections,
            'expenses': month_expenses,
            'net_movement': month_net_movement,
        },
        'session_stats': {
            'active_students_count': active_students_count,
            'total_expected_fees': total_expected_fees,
            'total_collected_fees': total_collected_fees,
            'total_pending_fees': total_pending_fees,
        },
        'dues': {
            'due_today_count': due_today_count,
            'due_today_amount': due_today_amount,
            'overdue_count': overdue_count,
            'overdue_amount': overdue_amount,
        },
        'monthly_trend': monthly_trend,
        'trend_summary': {
            'total_collections': trend_total_collections,
            'total_expenses': trend_total_expenses,
            'net_movement': trend_net_movement,
            'has_data': trend_has_data,
        },
        'recent_transactions': recent_transactions,
        'branch_comparison': branch_comparison,
        'selected_branch': active_branch,
        'selected_session': active_session,
        'is_all_branches': is_all_branches,
        'is_all_sessions': is_all_sessions,
        # Legacy backwards compatibility
        'total_students': active_students_count,
        'total_collections': total_collected_fees,
        'total_expenses': sum(e.amount for e in expenses_qs),
        'total_dues': total_pending_fees,
    }

    if request.GET.get('format') == 'json':
        # Serialize datetime objects for JSON
        serialized_recent = []
        for t in recent_transactions:
            tc = dict(t)
            if 'timestamp' in tc and isinstance(tc['timestamp'], (datetime, timezone.datetime)):
                tc['timestamp'] = tc['timestamp'].isoformat()
            serialized_recent.append(tc)

        return JsonResponse({
            'today': {
                'collections': today_collections,
                'expenses': today_expenses,
                'netMovement': today_net_movement,
                'net_movement': today_net_movement,
                'transactionCount': today_payments.count() + today_expenses_list.count(),
            },
            'month': {
                'collections': month_collections,
                'expenses': month_expenses,
                'netMovement': month_net_movement,
                'net_movement': month_net_movement,
            },
            'session': {
                'activeStudentsCount': active_students_count,
                'totalExpectedFees': total_expected_fees,
                'totalCollectedFees': total_collected_fees,
                'totalPendingFees': total_pending_fees,
            },
            'dues': {
                'dueTodayCount': due_today_count,
                'dueTodayAmount': due_today_amount,
                'overdueCount': overdue_count,
                'overdueAmount': overdue_amount,
            },
            'monthlyTrend': monthly_trend,
            'trendSummary': {
                'totalCollections': trend_total_collections,
                'totalExpenses': trend_total_expenses,
                'netMovement': trend_net_movement,
                'hasData': trend_has_data,
            },
            'branchComparison': branch_comparison,
            'recentTransactions': serialized_recent,
        })

    return render(request, 'dashboard.html', context)


def switch_branch_view(request, branch_id):
    request.session['selected_branch_id'] = str(branch_id)
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(clean_referer_url(referer, strip_params=['branch_id', 'page']))


def switch_session_view(request, session_id):
    if session_id == 'ALL':
        request.session['selected_session_id'] = 'ALL'
    else:
        selected = AcademicSession.objects.filter(id=session_id, isActive=True).first()
        if selected:
            request.session['selected_session_id'] = str(selected.id)
        else:
            messages.error(request, 'The selected academic session is not active or no longer exists.')
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(clean_referer_url(referer, strip_params=['session_id', 'page']))


def toggle_sidebar_view(request):
    collapsed = not request.session.get('is_sidebar_collapsed', False)
    request.session['is_sidebar_collapsed'] = collapsed
    return JsonResponse({'is_collapsed': collapsed})


@require_GET
def quick_search_api_view(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse([], safe=False)

    branch_id, session_id, active_branch, active_session = get_active_scope(request)

    admissions = StudentAdmission.objects.filter(is_active=True).select_related('student', 'branch', 'session')

    if branch_id and branch_id != 'ALL':
        admissions = admissions.filter(branch_id=branch_id)

    if session_id and session_id != 'ALL':
        admissions = admissions.filter(session_id=session_id)

    terms = q.split()
    for term in terms:
        admissions = admissions.filter(
            Q(student__full_name__icontains=term) |
            Q(roll_number__icontains=term) |
            Q(student__student_code__icontains=term) |
            Q(student__parent_phone__icontains=term) |
            Q(standard__icontains=term)
        )

    results = []
    for adm in admissions[:15]:
        st = adm.student
        net_payable = adm.fee_plan.net_payable if hasattr(adm, 'fee_plan') else MONEY_ZERO
        paid = sum(p.total_amount for p in adm.payments.filter(is_reversed=False))
        pending = max(MONEY_ZERO, net_payable - paid)

        results.append({
            'id': st.id,
            'admission_id': adm.id,
            'full_name': st.full_name,
            'roll_number': adm.roll_number,
            'student_code': st.student_code,
            'standard': adm.standard,
            'branch_name': adm.branch.name,
            'photo_url': st.photo_url or '',
            'pending_fees': pending,
        })

    return JsonResponse(results, safe=False)


# -------------------------------------------------------------------
# Navigation Placeholders
# -------------------------------------------------------------------

def placeholder_view(request, title="Section Under Development"):
    return render(request, 'placeholder.html', {'title': title})

def generate_student_code():
    year = datetime.now().year
    import random
    while True:
        code = f"SC-{year}-{random.randint(1000, 9999)}"
        if not Student.objects.filter(student_code=code).exists():
            return code


def extract_branch_code(branch) -> str:
    """
    Extracts a clean, short branch code (e.g., 'VAI', 'CC', 'EB', 'MAIN').
    Strips test suffixes like '_TEST_STEP14_REPORTS' and ensures uppercase alphanumeric.
    """
    if not branch:
        return 'MAIN'

    code = getattr(branch, 'code', None)
    if code and str(code).strip():
        c = str(code).strip().upper()
        if '_' in c:
            c = c.split('_')[0]
        c = re.sub(r'[^A-Z0-9]', '', c)
        if c:
            return c[:6]

    name = getattr(branch, 'name', None)
    if name and str(name).strip():
        n = str(name).strip().upper()
        if '_' in n:
            n = n.split('_')[0]
        n = re.sub(r'[^A-Z0-9]', '', n)
        if n:
            return n[:4]

    return 'MAIN'


def generate_next_roll_number(branch=None, session=None) -> str:
    """
    Generates a sequential short roll number in format: <branchcode>-<rollnumber>
    e.g. VAI-1, VAI-2, CC-1
    """
    if not branch:
        branch = (
            Branch.objects.filter(is_active=True).order_by('name').first()
            or Branch.objects.first()
        )
    if not branch:
        return "SC-1"

    branch_code = extract_branch_code(branch)
    qs = StudentAdmission.objects.filter(branch=branch)
    session_rolls = set(qs.filter(session=session).values_list('roll_number', flat=True)) if session else set()

    max_num = 0
    pattern = re.compile(rf'^{re.escape(branch_code)}-(\d+)$', re.IGNORECASE)
    for roll in qs.values_list('roll_number', flat=True):
        if roll:
            m = pattern.match(str(roll).strip())
            if m:
                try:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass

    next_num = max_num + 1
    while f"{branch_code}-{next_num}" in session_rolls:
        next_num += 1

    return f"{branch_code}-{next_num}"


def api_next_roll_number_view(request):
    """
    Returns the next auto-suggested roll number in short branchcode-rollnumber format (e.g. VAI-1).
    Query parameters:
    - branch_id: UUID or ID of the selected branch
    - session_id: UUID or ID of the selected session (optional)
    """
    branch_id = request.GET.get('branch_id')
    session_id = request.GET.get('session_id')

    branch = None
    if branch_id and branch_id != 'ALL':
        branch = Branch.objects.filter(id=branch_id).first()
    if not branch:
        scope_b_id, _, scope_b, _ = get_active_scope(request)
        branch = scope_b or Branch.objects.filter(is_active=True).first()

    session = None
    if session_id and session_id != 'ALL':
        session = AcademicSession.objects.filter(id=session_id).first()

    suggested_roll = generate_next_roll_number(branch, session)
    return JsonResponse({
        'roll_number': suggested_roll,
        'branch_code': extract_branch_code(branch),
    })


def students_list_view(request):
    """
    Student Directory, Search, Advanced Filtering, and Admission Workflow matching StudentsPage.tsx.
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. New Student Admission
        if action == 'create':
            full_name = request.POST.get('full_name', '').strip()
            roll_number = request.POST.get('roll_number', '').strip()
            standard = request.POST.get('standard', '').strip()
            branch_id = request.POST.get('branch_id', '').strip()
            session_id = request.POST.get('session_id', '').strip()
            parent_phone = request.POST.get('parent_phone', '').strip()
            student_phone = request.POST.get('student_phone', '').strip() or None
            address = request.POST.get('address', '').strip() or None
            total_fees_str = request.POST.get('total_fees', '').strip()
            due_date_str = request.POST.get('due_date', '').strip()

            if not full_name or not parent_phone:
                messages.error(request, "Full student name and parent phone are required.")
                return redirect('students_list')

            scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)

            # Resolve branch
            branch = None
            if branch_id and branch_id != 'ALL':
                branch = Branch.objects.filter(id=branch_id, is_active=True).first()
            if not branch:
                branch = scope_b or Branch.objects.filter(is_active=True).first()
            if not branch:
                messages.error(request, "No active branch found. Please create a branch first.")
                return redirect('students_list')

            # Resolve session
            session = None
            if session_id and session_id != 'ALL':
                session = AcademicSession.objects.filter(id=session_id, isActive=True).first()
            if not session:
                session = scope_s or AcademicSession.objects.filter(is_current=True, isActive=True).first()
            if not session:
                messages.error(request, "No academic session found. Please configure a session first.")
                return redirect('students_list')

            # Auto-generate short sequential roll number if not provided (e.g. VAI-1)
            if not roll_number:
                roll_number = generate_next_roll_number(branch, session)

            # Check roll number uniqueness within this branch + session
            if StudentAdmission.objects.filter(branch=branch, session=session, roll_number=roll_number).exists():
                messages.error(request, f"Roll number '{roll_number}' already exists in {branch.name} for session {session.name}.")
                return redirect('students_list')

            try:
                total_fees = parse_non_negative_money(total_fees_str)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('students_list')

            try:
                due_datetime = parse_form_date(
                    due_date_str,
                    default=timezone.now() + timedelta(days=30),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('students_list')

            # Photo upload
            photo_url = None
            if request.FILES.get('photo'):
                photo_file = request.FILES['photo']
                ext = os.path.splitext(photo_file.name)[1] or '.jpg'
                filename = f"photo-new-{uuid.uuid4()}-{int(datetime.now().timestamp())}{ext}"
                photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
                os.makedirs(photos_dir, exist_ok=True)
                filepath = os.path.join(photos_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in photo_file.chunks():
                        dest.write(chunk)
                photo_url = f"/media/photos/{filename}"

            with transaction.atomic():
                # Create Student
                student = Student.objects.create(
                    student_code=generate_student_code(),
                    full_name=full_name,
                    parent_phone=parent_phone,
                    student_phone=student_phone,
                    address=address,
                    photo_url=photo_url,
                )

                # Create StudentAdmission
                admission = StudentAdmission.objects.create(
                    student=student,
                    branch=branch,
                    session=session,
                    roll_number=roll_number,
                    standard=standard or 'Class 10',
                    admission_date=timezone.now(),
                    is_active=True,
                )

                # Create FeePlan
                fee_plan = FeePlan.objects.create(
                    admission=admission,
                    session=session,
                    total_fees=total_fees,
                    total_discount=MONEY_ZERO,
                    net_payable=total_fees,
                )

                # Create initial Installment
                Installment.objects.create(
                    fee_plan=fee_plan,
                    installment_no=1,
                    label='Session Fee',
                    due_date=due_datetime,
                    amount_due=total_fees,
                )

            messages.success(request, f"Student '{student.full_name}' admitted successfully into {branch.name} ({admission.standard})!")
            return redirect('student_detail', student_id=student.id)

        # 2. Toggle Archive / Active Status
        elif action == 'toggle_archive':
            student_id = request.POST.get('student_id')
            student = get_object_or_404(Student, id=student_id)
            has_active = student.admissions.filter(is_active=True).exists()
            new_active = not has_active
            student.admissions.all().update(is_active=new_active)
            status_word = "reactivated" if new_active else "archived"
            messages.success(request, f"Student '{student.full_name}' has been {status_word} successfully.")
            return redirect('students_list')

        # 3. Permanent Cascade Delete
        elif action == 'delete':
            student_id = request.POST.get('student_id')
            student = get_object_or_404(Student, id=student_id)
            name = student.full_name

            # Cascade delete related records cleanly
            for adm in student.admissions.all():
                if hasattr(adm, 'fee_plan'):
                    fp = adm.fee_plan
                    for inst in fp.installments.all():
                        inst.allocations.all().delete()
                    fp.installments.all().delete()
                    fp.discounts.all().delete()
                    fp.delete()
                adm.payments.all().delete()
            student.previous_dues.all().delete()
            student.payments.all().delete()
            student.admissions.all().delete()

            # Remove physical photo if exists
            if student.photo_url and student.photo_url.startswith('/media/'):
                rel_path = student.photo_url.replace('/media/', '', 1)
                full_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass

            student.delete()
            messages.success(request, f"Student '{name}' and all associated fee records were permanently deleted.")
            return redirect('students_list')

    # GET: Filter and assemble student list
    branch_id, session_id, active_branch, active_session = get_active_scope(request)

    try:
        page_size = int(request.GET.get('page_size', 25))
        if page_size not in (10, 25, 50, 100):
            page_size = 25
    except (TypeError, ValueError):
        page_size = 25

    try:
        page_num = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page_num = 1

    standard_filter = request.GET.get('standard', 'ALL')
    status_filter = request.GET.get('status', 'true')
    fee_status_filter = request.GET.get('fee_status', 'ALL')
    search_q = request.GET.get('q', '').strip()

    admissions_qs = StudentAdmission.objects.select_related(
        'student', 'branch', 'session', 'fee_plan'
    ).prefetch_related(
        'payments', 'fee_plan__installments', 'fee_plan__installments__allocations', 'student__previous_dues'
    )

    if branch_id and branch_id != 'ALL':
        admissions_qs = admissions_qs.filter(branch_id=branch_id)

    if session_id and session_id != 'ALL':
        admissions_qs = admissions_qs.filter(session_id=session_id)

    if standard_filter and standard_filter != 'ALL':
        admissions_qs = admissions_qs.filter(standard=standard_filter)

    if status_filter == 'true':
        admissions_qs = admissions_qs.filter(is_active=True)
    elif status_filter == 'false':
        admissions_qs = admissions_qs.filter(is_active=False)

    if search_q:
        terms = search_q.split()
        for term in terms:
            admissions_qs = admissions_qs.filter(
                Q(student__full_name__icontains=term) |
                Q(roll_number__icontains=term) |
                Q(student__student_code__icontains=term) |
                Q(student__parent_phone__icontains=term) |
                Q(student__student_phone__icontains=term) |
                Q(standard__icontains=term)
            )

    admissions_qs = admissions_qs.order_by('-created_at')

    students_data = []
    total_session_fees = MONEY_ZERO
    total_session_paid = MONEY_ZERO
    total_session_pending = MONEY_ZERO
    total_overall_pending = MONEY_ZERO
    active_count = 0
    archived_count = 0

    for adm in admissions_qs:
        st = adm.student
        plan = getattr(adm, 'fee_plan', None)
        tot_fees = plan.net_payable if plan else MONEY_ZERO
        pd_fees = sum(p.total_amount for p in adm.payments.all() if not p.is_reversed)
        pen_fees = max(MONEY_ZERO, tot_fees - pd_fees)

        # Previous dues carried into this admission's session only.
        prev_dues_qs = st.previous_dues.all()
        if adm.session_id and session_id != 'ALL':
            prev_dues_qs = prev_dues_qs.filter(current_session_id=adm.session_id)
        prev_dues = sum((max(MONEY_ZERO, d.outstanding_amount - d.collected_amount) for d in prev_dues_qs), MONEY_ZERO)

        # Overall consolidated pending dues across all academic sessions of this student
        st_all_admissions = st.admissions.all()
        ov_pending = sum(
            max(MONEY_ZERO, (a.fee_plan.net_payable if hasattr(a, 'fee_plan') and a.fee_plan else MONEY_ZERO) - sum((p.total_amount for p in a.payments.all() if not p.is_reversed), MONEY_ZERO))
            for a in st_all_admissions
        ) + sum((max(MONEY_ZERO, d.outstanding_amount - d.collected_amount) for d in st.previous_dues.all()), MONEY_ZERO)

        # Fee status
        if pen_fees <= 0 and tot_fees > 0:
            calc_fee_status = 'PAID'
        elif pd_fees > 0 and pen_fees > 0:
            calc_fee_status = 'PARTIAL'
        elif pd_fees == 0 and tot_fees > 0:
            calc_fee_status = 'UNPAID'
        else:
            calc_fee_status = 'PAID'

        # Fee Status Filter check
        if fee_status_filter == 'PAID' and calc_fee_status != 'PAID':
            continue
        elif fee_status_filter == 'PARTIAL' and calc_fee_status != 'PARTIAL':
            continue
        elif fee_status_filter == 'UNPAID' and calc_fee_status != 'UNPAID':
            continue
        elif fee_status_filter == 'HAS_DUES' and ov_pending <= 0:
            continue

        if adm.is_active:
            active_count += 1
            total_session_fees += tot_fees
            total_session_pending += pen_fees
            total_overall_pending += (pen_fees + prev_dues)
        else:
            archived_count += 1

        total_session_paid += pd_fees

        # Earliest unpaid installment due date
        next_due_date = None
        due_status = 'PAID'
        if pen_fees > 0 and plan and plan.installments.exists():
            for inst in plan.installments.all():
                inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                if inst.amount_due > inst_paid:
                    next_due_date = inst.due_date
                    due_status = inst.status
                    break

        students_data.append({
            'admission': adm,
            'student': st,
            'total_fees': tot_fees,
            'paid_fees': pd_fees,
            'pending_fees': pen_fees,
            'previous_dues': prev_dues,
            'overall_pending': ov_pending,
            'fee_status': calc_fee_status,
            'next_due_date': next_due_date,
            'due_status': due_status,
        })

    total_count = len(students_data)

    # EXPORT HANDLING (Excel & Landscape PDF)
    export_type = request.GET.get('export')
    if export_type in ('excel', 'pdf'):
        branch_name_label = 'All Branches'
        if branch_id and branch_id != 'ALL':
            b_match = Branch.objects.filter(id=branch_id).first()
            if b_match:
                branch_name_label = b_match.name

        session_name_label = 'All Sessions'
        if session_id and session_id != 'ALL':
            s_match = AcademicSession.objects.filter(id=session_id).first()
            if s_match:
                session_name_label = s_match.name

        meta = {
            'institute_name': 'Sutawane Classes Vaijapur',
            'branch_name': branch_name_label,
            'session_name': session_name_label,
            'records_count': len(students_data),
        }
        today_str = datetime.now().strftime('%Y%m%d')

        if export_type == 'excel':
            xlsx_bytes = export_students_to_excel(students_data, meta)
            filename = f"Students_Directory_{branch_name_label.replace(' ', '_')}_{today_str}.xlsx"
            response = HttpResponse(
                xlsx_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        elif export_type == 'pdf':
            pdf_bytes = export_students_to_pdf(students_data, meta)
            filename = f"Students_Directory_{branch_name_label.replace(' ', '_')}_{today_str}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    paginator = Paginator(students_data, page_size)
    try:
        page_obj = paginator.get_page(page_num)
    except Exception:
        page_obj = paginator.get_page(1)

    courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')
    branches = Branch.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-start_date')

    # Auto-generate a suggested roll number for the admission modal in format: branchcode-rollnumber (e.g. VAI-1)
    target_branch = active_branch or branches.first()
    suggested_roll = generate_next_roll_number(target_branch, active_session)

    context = {
        'students_data': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'paginator': paginator,
        'metrics': {
            'total_count': total_count,
            'active_count': active_count,
            'archived_count': archived_count,
            'total_session_fees': total_session_fees,
            'total_session_paid': total_session_paid,
            'total_session_pending': total_session_pending,
            'total_overall_pending': total_overall_pending,
        },
        'courses': courses,
        'branches': branches,
        'sessions': sessions,
        'suggested_roll': suggested_roll,
        'filters': {
            'branch_id': branch_id,
            'session_id': session_id,
            'standard': standard_filter,
            'status': status_filter,
            'fee_status': fee_status_filter,
            'q': search_q,
            'page_size': page_size,
            'page': page_num,
        }
    }
    return render(request, 'students.html', context)


def student_detail_view(request, student_id):
    """
    Comprehensive Student Profile, Multi-Session Ledgers, Installments & Receipts matching StudentDetailPage.tsx.
    """
    student = get_object_or_404(Student, id=student_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Update Bio & Admission Details
        if action == 'update_profile':
            full_name = request.POST.get('full_name', '').strip()
            parent_phone = request.POST.get('parent_phone', '').strip()
            student_phone = request.POST.get('student_phone', '').strip() or None
            address = request.POST.get('address', '').strip() or None
            roll_number = request.POST.get('roll_number', '').strip()
            standard = request.POST.get('standard', '').strip()

            if not full_name or not parent_phone:
                messages.error(request, "Full name and parent phone are required.")
                return redirect('student_detail', student_id=student.id)

            admission_id = request.POST.get('admission_id')
            current_adm = student.admissions.filter(id=admission_id).first() if admission_id else student.admissions.filter(is_active=True).first()

            if roll_number and current_adm and roll_number != current_adm.roll_number:
                collision = StudentAdmission.objects.filter(
                    branch=current_adm.branch,
                    session=current_adm.session,
                    roll_number=roll_number
                ).exclude(id=current_adm.id).exists()
                if collision:
                    messages.error(request, f"Roll number '{roll_number}' is already taken in this branch and session.")
                    return redirect('student_detail', student_id=student.id)

            student.full_name = full_name
            student.parent_phone = parent_phone
            student.student_phone = student_phone
            student.address = address
            student.save()

            if current_adm:
                if roll_number:
                    current_adm.roll_number = roll_number
                if standard:
                    current_adm.standard = standard
                current_adm.save()

            messages.success(request, f"Profile for '{student.full_name}' updated successfully.")
            return redirect('student_detail', student_id=student.id)

        # 2. Upload Student Photograph
        elif action == 'upload_photo':
            if request.FILES.get('photo'):
                photo_file = request.FILES['photo']
                ext = os.path.splitext(photo_file.name)[1] or '.jpg'
                filename = f"photo-{student.id}-{int(datetime.now().timestamp())}{ext}"
                photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
                os.makedirs(photos_dir, exist_ok=True)

                # Remove previous photo if exists
                if student.photo_url and student.photo_url.startswith('/media/'):
                    old_path = os.path.join(settings.MEDIA_ROOT, student.photo_url.replace('/media/', '', 1))
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

                filepath = os.path.join(photos_dir, filename)
                try:
                    from PIL import Image, ImageOps
                    img = Image.open(photo_file)
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail((800, 800), Image.Resampling.LANCZOS)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    img.save(filepath, 'JPEG', quality=88, optimize=True)
                except Exception:
                    with open(filepath, 'wb+') as dest:
                        for chunk in photo_file.chunks():
                            dest.write(chunk)
                student.photo_url = f"/media/photos/{filename}"
                student.save()
                messages.success(request, "Student photograph uploaded successfully!")
            return redirect('student_detail', student_id=student.id)

        # 3. Delete Photo
        elif action == 'delete_photo':
            if student.photo_url and student.photo_url.startswith('/media/'):
                old_path = os.path.join(settings.MEDIA_ROOT, student.photo_url.replace('/media/', '', 1))
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            student.photo_url = None
            student.save()
            messages.success(request, "Student photograph removed.")
            return redirect('student_detail', student_id=student.id)

        # 4. Update Fee Due Date
        elif action == 'update_due_date':
            installment_id = request.POST.get('installment_id')
            new_due_date = request.POST.get('due_date')
            if installment_id and new_due_date:
                inst = Installment.objects.filter(id=installment_id).first()
                if inst:
                    try:
                        inst.due_date = parse_form_date(new_due_date)
                    except ValueError as exc:
                        messages.error(request, str(exc))
                        return redirect('student_detail', student_id=student.id)
                    inst.save()
                    messages.success(request, f"Fee due date updated to {new_due_date}.")
            return redirect('student_detail', student_id=student.id)

        # 5. Toggle Archive
        elif action == 'toggle_archive':
            has_active = student.admissions.filter(is_active=True).exists()
            new_active = not has_active
            student.admissions.all().update(is_active=new_active)
            status_word = "reactivated" if new_active else "archived"
            messages.success(request, f"Student '{student.full_name}' {status_word} successfully.")
            return redirect('student_detail', student_id=student.id)

        # 6. Delete Student
        elif action == 'delete':
            with transaction.atomic():
                for adm in student.admissions.all():
                    if hasattr(adm, 'fee_plan'):
                        fp = adm.fee_plan
                        for inst in fp.installments.all():
                            inst.allocations.all().delete()
                        fp.installments.all().delete()
                        fp.discounts.all().delete()
                        fp.delete()
                    adm.payments.all().delete()
                student.previous_dues.all().delete()
                student.payments.all().delete()
                student.admissions.all().delete()
                student.delete()
            if student.photo_url and student.photo_url.startswith('/media/'):
                old_path = os.path.join(settings.MEDIA_ROOT, student.photo_url.replace('/media/', '', 1))
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            messages.success(request, "Student and all linked records permanently deleted.")
            return redirect('students_list')

    # GET: Assemble full profile details
    admissions = student.admissions.select_related('branch', 'session', 'fee_plan').prefetch_related(
        'payments', 'fee_plan__installments', 'fee_plan__installments__allocations', 'fee_plan__discounts'
    ).order_by('-created_at')

    admission_id = request.GET.get('admission_id')
    current_adm = None
    if admission_id:
        current_adm = admissions.filter(id=admission_id).first()

    if not current_adm:
        scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
        if scope_s_id and scope_s_id != 'ALL':
            current_adm = admissions.filter(session_id=scope_s_id).first()
        if not current_adm and scope_b_id and scope_b_id != 'ALL':
            current_adm = admissions.filter(branch_id=scope_b_id).first()

    if not current_adm:
        current_adm = admissions.filter(is_active=True).first() or admissions.first()

    # Enrich admissions with financial snapshot for multi-session tab switcher
    admissions_list = list(admissions)
    for adm in admissions_list:
        fp = getattr(adm, 'fee_plan', None)
        adm_payable = fp.net_payable if fp and fp.net_payable else MONEY_ZERO
        adm_payments = [p for p in adm.payments.all() if not p.is_reversed]
        adm_paid = sum((p.total_amount for p in adm_payments), MONEY_ZERO)
        adm_pending = max(MONEY_ZERO, adm_payable - adm_paid)
        adm.adm_payable = adm_payable
        adm.adm_paid = adm_paid
        adm.adm_pending = adm_pending
        adm.adm_is_cleared = (adm_pending <= 0 and adm_payable > 0)
        adm.is_selected = bool(current_adm and adm.id == current_adm.id)
        adm.is_latest = bool(len(admissions_list) > 0 and adm.id == admissions_list[0].id)

    # Fee summary for current admission
    fee_plan = getattr(current_adm, 'fee_plan', None) if current_adm else None
    total_fees = fee_plan.total_fees if fee_plan else MONEY_ZERO
    total_discount = fee_plan.total_discount if fee_plan else MONEY_ZERO
    net_payable = fee_plan.net_payable if fee_plan else MONEY_ZERO

    session_payments = current_adm.payments.filter(is_reversed=False).order_by('-payment_date') if current_adm else []
    total_paid = sum(p.total_amount for p in session_payments)
    session_pending = max(MONEY_ZERO, net_payable - total_paid)

    # Consolidated financial calculation across ALL academic sessions for this student
    all_previous_dues = student.previous_dues.select_related('original_session', 'current_session')
    all_prev_total = sum((d.outstanding_amount for d in all_previous_dues), MONEY_ZERO)
    all_prev_collected = sum((d.collected_amount for d in all_previous_dues), MONEY_ZERO)
    all_previous_dues_pending = sum((max(MONEY_ZERO, d.outstanding_amount - d.collected_amount) for d in all_previous_dues), MONEY_ZERO)

    lifetime_total_fees = sum((adm.adm_payable for adm in admissions_list), MONEY_ZERO) + all_prev_total
    lifetime_paid_fees = sum((adm.adm_paid for adm in admissions_list), MONEY_ZERO) + all_prev_collected
    lifetime_pending_fees = sum((adm.adm_pending for adm in admissions_list), MONEY_ZERO) + all_previous_dues_pending

    # True consolidated overall pending across all academic sessions & historical dues
    overall_pending = lifetime_pending_fees

    # Previous session dues for the currently selected session view (if any legacy record)
    previous_due_session_id = current_adm.session_id if current_adm else scope_s_id
    previous_dues = all_previous_dues
    if previous_due_session_id and previous_due_session_id != 'ALL':
        previous_dues = previous_dues.filter(current_session_id=previous_due_session_id)
    previous_dues_pending = sum((max(MONEY_ZERO, d.outstanding_amount - d.collected_amount) for d in previous_dues), MONEY_ZERO)

    # Dues in all other academic sessions outside the current view
    other_sessions_pending = max(MONEY_ZERO, overall_pending - session_pending)

    # Installment schedule
    installments_data = []
    next_due_date = None
    next_due_status = 'PAID'
    if fee_plan:
        for inst in fee_plan.installments.all().order_by('installment_no'):
            paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
            balance = max(MONEY_ZERO, inst.amount_due - paid)
            is_cleared = balance <= 0 or session_pending <= 0
            status = 'PAID' if is_cleared else inst.status
            if not is_cleared and next_due_date is None:
                next_due_date = inst.due_date
                next_due_status = status
            installments_data.append({
                'installment': inst,
                'paid': paid,
                'balance': balance,
                'status': status,
                'is_cleared': is_cleared,
            })

    # All student payment receipts
    all_payments = student.payments.select_related(
        'branch', 'session', 'admission'
    ).prefetch_related('allocations__installment').order_by('-payment_date')

    courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-start_date')
    branches = Branch.objects.filter(is_active=True).order_by('name')

    paid_percentage = round((float(total_paid) / float(net_payable) * 100), 1) if net_payable and float(net_payable) > 0 else (100.0 if total_paid and float(total_paid) > 0 else 0.0)
    pending_percentage = round(max(0.0, 100.0 - float(paid_percentage)), 1)

    overall_paid_percentage = round((float(lifetime_paid_fees) / float(lifetime_total_fees) * 100), 1) if lifetime_total_fees and float(lifetime_total_fees) > 0 else (100.0 if lifetime_paid_fees and float(lifetime_paid_fees) > 0 else 0.0)
    overall_pending_percentage = round(max(0.0, 100.0 - float(overall_paid_percentage)), 1)

    context = {
        'student': student,
        'current_admission': current_adm,
        'all_admissions': admissions_list,
        'fee_summary': {
            'total_fees': total_fees,
            'total_discount': total_discount,
            'net_payable': net_payable,
            'total_paid': total_paid,
            'session_pending': session_pending,
            'other_sessions_pending': other_sessions_pending,
            'previous_dues_pending': previous_dues_pending,
            'overall_pending': overall_pending,
            'lifetime_total_fees': lifetime_total_fees,
            'lifetime_paid_fees': lifetime_paid_fees,
            'lifetime_pending_fees': lifetime_pending_fees,
            'paid_percentage': paid_percentage,
            'pending_percentage': pending_percentage,
            'overall_paid_percentage': overall_paid_percentage,
            'overall_pending_percentage': overall_pending_percentage,
        },
        'installments_data': installments_data,
        'payments': all_payments,
        'previous_dues': previous_dues,
        'next_due_date': next_due_date,
        'next_due_status': next_due_status,
        'courses': courses,
        'sessions': sessions,
        'branches': branches,
    }
    return render(request, 'student_detail.html', context)


# -------------------------------------------------------------
# Student Academic Promotion Views (Individual & Batch)
# -------------------------------------------------------------

def suggest_next_standard(standard: str) -> str:
    """
    Standard progression mapping matching React suggestNextStandard.
    """
    mapping = {
        'Class 8': 'Class 9',
        'Class 9': 'Class 10',
        'Class 10': 'Class 11 Science',
        'Class 11 Science': 'Class 12 Science',
        'Class 11 Commerce': 'Class 12 Commerce',
        'Class 11': 'Class 12',
        'MHT-CET / JEE Foundation': 'MHT-CET / JEE Target Batch',
    }
    return mapping.get(standard, standard)


def student_promotion_preview_view(request, student_id):
    """
    Live promotion preview endpoint for single student.
    Matches React /students/:id/promotion-preview and PromoteStudentModal.tsx.
    """
    student = get_object_or_404(Student, id=student_id)
    current_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.order_by('-created_at').first()

    # Dues calculation from current admission
    fee_plan = getattr(current_adm, 'fee_plan', None) if current_adm else None
    total_fees = fee_plan.net_payable if fee_plan else MONEY_ZERO
    paid = sum((p.total_amount for p in current_adm.payments.filter(is_reversed=False)), MONEY_ZERO) if current_adm else MONEY_ZERO
    current_pending_due = max(MONEY_ZERO, total_fees - paid)

    # Sessions
    sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
    target_session_id = request.GET.get('target_session_id')
    target_session = None

    if target_session_id:
        target_session = AcademicSession.objects.filter(id=target_session_id).first()

    if not target_session and sessions:
        # Pick session different from current admission session
        target_session = next((s for s in sessions if not current_adm or s.id != current_adm.session_id), sessions[0])

    is_already_promoted = False
    if target_session:
        is_already_promoted = student.admissions.filter(session=target_session).exists()

    suggested_standard = suggest_next_standard(current_adm.standard if current_adm else '')
    branches = Branch.objects.filter(is_active=True).order_by('name')
    target_branch = current_adm.branch if current_adm else (branches.first() if branches else None)

    # Clean short roll number: branchcode-rollnumber (e.g. VAI-1)
    if current_adm and current_adm.roll_number and not current_adm.roll_number.startswith('SC-') and not current_adm.roll_number.endswith('-N'):
        if target_session and not StudentAdmission.objects.filter(branch=target_branch, session=target_session, roll_number=current_adm.roll_number).exists():
            suggested_roll = current_adm.roll_number
        else:
            suggested_roll = generate_next_roll_number(target_branch, target_session)
    else:
        suggested_roll = generate_next_roll_number(target_branch, target_session)

    courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')
    standard_in_courses = courses.filter(name=suggested_standard).exists()
    matched_course = courses.filter(name=suggested_standard).first()
    suggested_fees = matched_course.default_fee if (matched_course and matched_course.default_fee) else (total_fees if total_fees > 0 else 30000.0)

    context = {
        'student': student,
        'current_admission': current_adm,
        'current_pending_due': current_pending_due,
        'sessions': sessions,
        'target_session': target_session,
        'is_already_promoted': is_already_promoted,
        'suggested_standard': suggested_standard,
        'suggested_roll': suggested_roll,
        'suggested_fees': suggested_fees,
        'courses': courses,
        'standard_in_courses': standard_in_courses,
        'branches': branches,
    }

    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'studentId': student.id,
            'fullName': student.full_name,
            'studentCode': student.student_code,
            'currentStandard': current_adm.standard if current_adm else '',
            'currentRollNumber': current_adm.roll_number if current_adm else '',
            'currentPendingDue': float(current_pending_due),
            'suggestedStandard': suggested_standard,
            'suggestedRoll': suggested_roll,
            'suggestedFees': suggested_fees,
            'isAlreadyPromoted': is_already_promoted,
        })

    return render(request, 'modals/promote_student_modal.html', context)


def promote_student_view(request, student_id):
    """
    Executes student promotion to next academic session.
    Matches React POST /students/:id/promote.
    """
    student = get_object_or_404(Student, id=student_id)

    if request.method != 'POST':
        return redirect('student_detail', student_id=student.id)

    target_session_id = request.POST.get('target_session_id')
    target_branch_id = request.POST.get('target_branch_id')
    target_standard = request.POST.get('target_standard', '').strip()
    new_roll_number = request.POST.get('new_roll_number', '').strip()
    try:
        new_total_fees = parse_non_negative_money(request.POST.get('new_total_fees', 0.0))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('student_detail', student_id=student.id)
    carry_forward_due = request.POST.get('carry_forward_due') in ('true', 'on', True)
    due_notes = request.POST.get('due_notes', '').strip()

    prev_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.order_by('-created_at').first()
    branch_id = target_branch_id or (prev_adm.branch_id if prev_adm else None)

    target_branch_obj = Branch.objects.filter(id=branch_id).first() if branch_id else None
    target_session = AcademicSession.objects.filter(id=target_session_id, isActive=True).first() if target_session_id else None

    # Auto-generate short sequential roll number if not provided (e.g. VAI-1)
    if not new_roll_number and target_branch_obj and target_session:
        new_roll_number = generate_next_roll_number(target_branch_obj, target_session)

    # Validation
    error_msg = None
    if not target_session_id or not target_standard or not new_roll_number:
        error_msg = 'Target academic session, promoted class, and new roll number are required.'

    if not target_session:
        error_msg = 'Selected target academic session not found.'

    if not error_msg and student.admissions.filter(session_id=target_session_id).exists():
        error_msg = f"Student {student.full_name} is already admitted in {target_session.name}."

    if not error_msg and StudentAdmission.objects.filter(branch_id=branch_id, session_id=target_session_id, roll_number=new_roll_number).exists():
        error_msg = f"Roll number '{new_roll_number}' is already in use in target branch and session."

    if error_msg:
        if request.headers.get('HX-Request'):
            sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
            courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')
            branches = Branch.objects.filter(is_active=True).order_by('name')
            fee_plan = getattr(prev_adm, 'fee_plan', None) if prev_adm else None
            total_fees = fee_plan.net_payable if fee_plan else MONEY_ZERO
            paid = sum((p.total_amount for p in prev_adm.payments.filter(is_reversed=False)), MONEY_ZERO) if prev_adm else MONEY_ZERO
            current_pending_due = max(MONEY_ZERO, total_fees - paid)
            context = {
                'student': student,
                'current_admission': prev_adm,
                'current_pending_due': current_pending_due,
                'sessions': sessions,
                'target_session': target_session,
                'is_already_promoted': False,
                'suggested_standard': target_standard,
                'suggested_roll': new_roll_number,
                'suggested_fees': new_total_fees,
                'courses': courses,
                'standard_in_courses': True,
                'branches': branches,
                'form_error': error_msg,
            }
            return render(request, 'modals/promote_student_modal.html', context)
        messages.error(request, error_msg)
        return redirect('student_detail', student_id=student.id)

    # Compute previous pending dues strictly from previous admission
    prev_plan_fees = prev_adm.fee_plan.net_payable if (prev_adm and hasattr(prev_adm, 'fee_plan')) else MONEY_ZERO
    prev_paid = sum((p.total_amount for p in prev_adm.payments.filter(is_reversed=False)), MONEY_ZERO) if prev_adm else MONEY_ZERO
    prev_pending_due = max(MONEY_ZERO, prev_plan_fees - prev_paid)

    with transaction.atomic():
        previous_due_recorded = MONEY_ZERO
        # Independent session accounting: Previous session dues remain strictly on the previous
        # admission fee plan without creating synthetic duplicate PreviousSessionDue records.

        # 1. Create new StudentAdmission in target session
        new_admission = StudentAdmission.objects.create(
            student=student,
            branch_id=branch_id,
            session=target_session,
            roll_number=new_roll_number,
            standard=target_standard,
            admission_date=timezone.now(),
            is_active=True,
        )

        # 2. Create fresh FeePlan for target session
        new_fee_plan = FeePlan.objects.create(
            admission=new_admission,
            session=target_session,
            total_fees=new_total_fees,
            total_discount=MONEY_ZERO,
            net_payable=new_total_fees,
        )

        # 3. Create flexible open installment
        Installment.objects.create(
            fee_plan=new_fee_plan,
            installment_no=1,
            label='Session Fee',
            due_date=timezone.now(),
            amount_due=new_total_fees,
        )

    if request.headers.get('HX-Request'):
        context = {
            'success': True,
            'student': student,
            'new_admission': new_admission,
            'previous_due_recorded': previous_due_recorded,
        }
        return render(request, 'modals/promote_student_modal.html', context)

    messages.success(
        request,
        f"Successfully promoted {student.full_name} to {new_admission.standard} for session {target_session.name}!"
    )
    return redirect('student_detail', student_id=student.id)


def batch_promote_modal_view(request):
    """
    Renders batch promotion modal with live selection preview and aggregate dues.
    Matches React BatchPromoteModal.tsx.
    """
    student_ids = request.POST.getlist('student_ids') or request.GET.getlist('student_ids')
    if not student_ids:
        raw_ids = request.POST.get('student_ids', '') or request.GET.get('student_ids', '')
        if raw_ids:
            student_ids = [s.strip() for s in raw_ids.split(',') if s.strip()]

    selected_students = []
    total_dues_across_selected = MONEY_ZERO

    for s_id in student_ids:
        st = Student.objects.filter(id=s_id).first()
        if not st:
            continue
        adm = st.admissions.filter(is_active=True).order_by('-created_at').first() or st.admissions.order_by('-created_at').first()
        fee_plan = getattr(adm, 'fee_plan', None) if adm else None
        total_f = fee_plan.net_payable if fee_plan else MONEY_ZERO
        paid = sum((p.total_amount for p in adm.payments.filter(is_reversed=False)), MONEY_ZERO) if adm else MONEY_ZERO
        pending = max(MONEY_ZERO, total_f - paid)
        total_dues_across_selected += pending

        selected_students.append({
            'id': st.id,
            'full_name': st.full_name,
            'roll_number': adm.roll_number if adm else '—',
            'standard': adm.standard if adm else '—',
            'branch_name': adm.branch.name if adm and adm.branch else '',
            'pending_fees': pending,
        })

    sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
    target_session = next((s for s in sessions if not s.is_current), sessions[0] if sessions else None)
    branches = Branch.objects.filter(is_active=True).order_by('name')
    courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')
    default_fees = courses.first().default_fee if courses.first() and courses.first().default_fee else 30000.0

    context = {
        'selected_students': selected_students,
        'total_dues_across_selected': total_dues_across_selected,
        'sessions': sessions,
        'target_session': target_session,
        'branches': branches,
        'courses': courses,
        'default_fees': default_fees,
    }
    return render(request, 'modals/batch_promote_modal.html', context)


def batch_promote_view(request):
    """
    Executes batch promotion for selected students.
    Matches React POST /students/batch-promote.
    """
    if request.method != 'POST':
        return redirect('students_list')

    student_ids = request.POST.getlist('student_ids')
    target_session_id = request.POST.get('target_session_id')
    target_branch_id = request.POST.get('target_branch_id')
    target_standard = request.POST.get('target_standard', '').strip()
    try:
        default_total_fees = parse_non_negative_money(request.POST.get('default_total_fees', 0.0))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('students_list')
    carry_forward_dues = request.POST.get('carry_forward_dues') in ('true', 'on', True)

    target_session = AcademicSession.objects.filter(id=target_session_id, isActive=True).first() if target_session_id else None

    if not student_ids or not target_session or not target_standard:
        if request.headers.get('HX-Request'):
            return render(request, 'modals/batch_promote_modal.html', {
                'form_error': 'Student selection, target session, and target standard are required.',
                'sessions': AcademicSession.objects.filter(isActive=True).order_by('-start_date'),
                'branches': Branch.objects.filter(is_active=True).order_by('name'),
                'courses': Course.objects.filter(is_active=True).order_by('sort_order', 'name'),
            })
        messages.error(request, 'Target academic session and standard class are required.')
        return redirect('students_list')

    promoted_count = 0
    skipped_list = []

    for s_id in student_ids:
        student = Student.objects.filter(id=s_id).first()
        if not student:
            skipped_list.append({'name': s_id, 'reason': 'Student record not found'})
            continue

        prev_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.order_by('-created_at').first()
        if not prev_adm:
            skipped_list.append({'name': student.full_name, 'reason': 'No prior admission record found'})
            continue

        # Check if already admitted in target session
        if student.admissions.filter(session=target_session).exists():
            skipped_list.append({'name': student.full_name, 'reason': f'Already enrolled in {target_session.name}'})
            continue

        branch_id = prev_adm.branch_id if (not target_branch_id or target_branch_id == 'KEEP') else target_branch_id

        # Unique roll number generation in short format: branchcode-rollnumber (e.g. VAI-1)
        target_branch = Branch.objects.filter(id=branch_id).first()
        base_roll = prev_adm.roll_number if prev_adm else None
        if base_roll and not base_roll.startswith('SC-') and not base_roll.endswith('-N') and not StudentAdmission.objects.filter(branch_id=branch_id, session=target_session, roll_number=base_roll).exists():
            new_roll = base_roll
        else:
            new_roll = generate_next_roll_number(target_branch, target_session)

        # Calculate previous dues
        prev_fees = prev_adm.fee_plan.net_payable if hasattr(prev_adm, 'fee_plan') else MONEY_ZERO
        prev_paid = sum((p.total_amount for p in prev_adm.payments.filter(is_reversed=False)), MONEY_ZERO)
        prev_pending = max(MONEY_ZERO, prev_fees - prev_paid)

        with transaction.atomic():
            # Independent session accounting: Previous session dues remain strictly on the previous
            # admission fee plan without creating synthetic duplicate PreviousSessionDue records.

            new_adm = StudentAdmission.objects.create(
                student=student,
                branch_id=branch_id,
                session=target_session,
                roll_number=new_roll,
                standard=target_standard,
                admission_date=timezone.now(),
                is_active=True,
            )

            new_plan = FeePlan.objects.create(
                admission=new_adm,
                session=target_session,
                total_fees=default_total_fees,
                total_discount=MONEY_ZERO,
                net_payable=default_total_fees,
            )

            Installment.objects.create(
                fee_plan=new_plan,
                installment_no=1,
                label='Session Fee',
                due_date=timezone.now(),
                amount_due=default_total_fees,
            )

        promoted_count += 1

    result_summary = {
        'promoted_count': promoted_count,
        'skipped_count': len(skipped_list),
        'skipped_list': skipped_list,
        'total_requested': len(student_ids),
        'target_standard': target_standard,
        'session_name': target_session.name,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'modals/batch_promote_modal.html', {'result_summary': result_summary})

    messages.success(request, f"Successfully promoted {promoted_count} students to {target_standard} ({target_session.name})!")
    return redirect('students_list')


def courses_list_view(request):
    """
    Standard Classes & Courses Management matching CoursesPage.tsx.
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper() or None
            description = request.POST.get('description', '').strip() or None
            default_fee_str = request.POST.get('default_fee', '').strip()
            sort_order_str = request.POST.get('sort_order', '0').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name:
                messages.error(request, "Class / Course name is required.")
                return redirect('courses_list')

            if Course.objects.filter(name__iexact=name).exists():
                messages.error(request, f"Course '{name}' already exists.")
                return redirect('courses_list')

            try:
                default_fee = parse_non_negative_money(default_fee_str, default=None)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('courses_list')
            try:
                sort_order = int(sort_order_str)
            except ValueError:
                sort_order = 0

            course = Course.objects.create(
                name=name,
                code=code,
                description=description,
                default_fee=default_fee,
                sort_order=sort_order,
                is_active=is_active,
            )
            messages.success(request, f"Course '{course.name}' created successfully.")
            return redirect('courses_list')

        elif action == 'update':
            course_id = request.POST.get('course_id')
            course = get_object_or_404(Course, id=course_id)
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper() or None
            description = request.POST.get('description', '').strip() or None
            default_fee_str = request.POST.get('default_fee', '').strip()
            sort_order_str = request.POST.get('sort_order', '0').strip()
            is_active = request.POST.get('is_active') == 'on'

            if not name:
                messages.error(request, "Class / Course name is required.")
                return redirect('courses_list')

            if name.lower() != course.name.lower() and Course.objects.filter(name__iexact=name).exclude(id=course.id).exists():
                messages.error(request, f"Course '{name}' already exists.")
                return redirect('courses_list')

            # Synchronize student admissions if standard name changed
            if name != course.name:
                StudentAdmission.objects.filter(standard=course.name).update(standard=name)

            course.name = name
            course.code = code
            course.description = description
            try:
                course.default_fee = parse_non_negative_money(default_fee_str, default=None)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('courses_list')
            try:
                course.sort_order = int(sort_order_str)
            except ValueError:
                pass
            course.is_active = is_active
            course.save()
            messages.success(request, f"Course '{course.name}' updated successfully.")
            return redirect('courses_list')

        elif action == 'toggle_status':
            course_id = request.POST.get('course_id')
            course = get_object_or_404(Course, id=course_id)
            course.is_active = not course.is_active
            course.save()
            status_text = "Active" if course.is_active else "Inactive"
            messages.success(request, f"Course '{course.name}' status set to {status_text}.")
            return redirect('courses_list')

        elif action == 'delete':
            course_id = request.POST.get('course_id')
            course = get_object_or_404(Course, id=course_id)
            enrolled_count = StudentAdmission.objects.filter(standard=course.name).count()
            if enrolled_count > 0:
                messages.error(request, f"Cannot delete course '{course.name}' because {enrolled_count} student admission(s) are currently enrolled. Deactivate it instead.")
            else:
                name = course.name
                course.delete()
                messages.success(request, f"Course '{name}' deleted successfully.")
            return redirect('courses_list')

    # GET
    search_q = request.GET.get('q', '').strip()
    courses_qs = Course.objects.all().order_by('sort_order', 'name')
    if search_q:
        courses_qs = courses_qs.filter(
            Q(name__icontains=search_q) |
            Q(code__icontains=search_q) |
            Q(description__icontains=search_q)
        )

    all_courses = Course.objects.all()
    total_courses = all_courses.count()
    active_count = all_courses.filter(is_active=True).count()
    inactive_count = total_courses - active_count

    courses_data = []
    for c in courses_qs:
        enrolled_count = StudentAdmission.objects.filter(standard=c.name).count()
        courses_data.append({
            'course': c,
            'enrolled_count': enrolled_count,
        })

    overall_enrolled = StudentAdmission.objects.count()

    context = {
        'courses_data': courses_data,
        'total_courses': total_courses,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'total_enrolled': overall_enrolled,
        'search_q': search_q,
    }
    return render(request, 'courses.html', context)

# -------------------------------------------------------------
# Fee Accounting, Collection & Receipt Architecture (Step 9)
# -------------------------------------------------------------

def number_to_words_inr(amount: float) -> str:
    """
    Converts numeric amount to official Indian Rupee Words matching React numberToWordsINR.
    """
    num = int(amount)
    if num == 0:
        return 'Rupees Zero Only'

    a = [
        '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
        'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
        'Seventeen', 'Eighteen', 'Nineteen'
    ]
    b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    if len(str(num)) > 9:
        return f"Rupees {num:,} Only"

    def in_words(n: int) -> str:
        s = ''
        if n >= 10000000:
            s += f"{in_words(n // 10000000)} Crore "
            n %= 10000000
        if n >= 100000:
            s += f"{in_words(n // 100000)} Lakh "
            n %= 100000
        if n >= 1000:
            s += f"{in_words(n // 1000)} Thousand "
            n %= 1000
        if n >= 100:
            s += f"{in_words(n // 100)} Hundred "
            n %= 100
        if n > 0:
            if s != '':
                s += 'and '
            if n < 20:
                s += a[n]
            else:
                s += b[n // 10]
                if n % 10:
                    s += f" {a[n % 10]}"
        return s.strip()

    words = in_words(num)
    return f"Rupees {words} Only"


def extract_academic_year(session) -> str:
    """
    Extracts a clean academic year string in YYYY-YY format (e.g., '2026-27').
    Handles '2026-27', '2026-2027', '2026-27_TEST_STEP14_REPORTS', etc.
    """
    if session:
        # 1. Match from session.name
        name_str = str(getattr(session, 'name', '') or '').strip()
        m = re.search(r'(\d{4})[-/](\d{2,4})', name_str)
        if m:
            y1, y2 = m.group(1), m.group(2)
            if len(y2) == 4:
                y2 = y2[-2:]
            return f"{y1}-{y2}"

        # 2. Match from session.display_name
        disp_str = str(getattr(session, 'display_name', '') or '').strip()
        m = re.search(r'(\d{4})[-/](\d{2,4})', disp_str)
        if m:
            y1, y2 = m.group(1), m.group(2)
            if len(y2) == 4:
                y2 = y2[-2:]
            return f"{y1}-{y2}"

        # 3. Match from session.start_date
        s_date = getattr(session, 'start_date', None)
        if s_date:
            try:
                y = s_date.year
                return f"{y}-{str(y + 1)[-2:]}"
            except Exception:
                pass

    now = timezone.now()
    y = now.year
    return f"{y}-{str(y + 1)[-2:]}"


def generate_sequential_receipt_number(branch, session) -> str:
    """
    Thread-safe atomic sequential receipt number generator.
    Format: academicyear-branchcode-receipt number
    Example: 2026-27-VAI-REC1
    """
    if not branch:
        branch = Branch.objects.filter(is_active=True).first() or Branch.objects.first()
    if not session:
        session = (
            AcademicSession.objects.filter(is_current=True, isActive=True).first()
            or AcademicSession.objects.filter(isActive=True).first()
            or AcademicSession.objects.first()
        )

    academic_year = extract_academic_year(session)
    branch_code = extract_branch_code(branch)
    prefix = f"{academic_year}-{branch_code}-REC"

    if branch and session:
        with transaction.atomic():
            counter, _ = ReceiptCounter.objects.select_for_update().get_or_create(
                branch=branch,
                session=session,
                defaults={'prefix': prefix, 'last_number': 0}
            )
            while True:
                counter.last_number += 1
                receipt_no = f"{prefix}{counter.last_number}"
                if not Payment.objects.filter(receipt_number=receipt_no).exists():
                    break

            counter.prefix = prefix
            counter.save()
            return receipt_no
    else:
        # Fallback when no Branch/Session entity exists in database
        seq = Payment.objects.count() + 1
        while True:
            receipt_no = f"{prefix}{seq}"
            if not Payment.objects.filter(receipt_number=receipt_no).exists():
                return receipt_no
            seq += 1


def fee_collect_view(request):
    """
    Fee Collection & Receipts Register matching CollectFeesPage.tsx.
    Supports:
    - Tab 1: Collection Entry Form (with auto FIFO installment allocation, overpayment guard, duplicate check, and next promise due date)
    - Tab 2: Payment Receipts History (with 4 KPI cards, filters, and printable receipt modals)
    - Reversal / Voiding of receipts with reasons and ledger rollbacks
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Reverse Payment
        if action == 'reverse_payment':
            payment_id = request.POST.get('payment_id')
            reversal_reason = request.POST.get('reversal_reason', '').strip()

            payment = get_object_or_404(Payment, id=payment_id)
            if payment.is_reversed:
                messages.warning(request, f"Receipt #{payment.receipt_number} is already voided.")
                return redirect(f"{request.path}?tab=history")

            with transaction.atomic():
                payment.is_reversed = True
                payment.reversal_reason = reversal_reason or "Cancelled by administrator"
                payment.reversed_at = timezone.now()
                payment.save()

                # If towards previous due, restore collected amount
                if payment.previous_due:
                    pd = payment.previous_due
                    pd.collected_amount = max(MONEY_ZERO, pd.collected_amount - payment.total_amount)
                    pd.save()

            messages.success(request, f"Receipt #{payment.receipt_number} voided and reversed successfully. Ledgers updated.")
            return redirect(f"{request.path}?tab=history")

        # 2. Collect Payment
        elif action == 'collect_payment':
            student_id = request.POST.get('student_id')
            target_type = request.POST.get('target_type', 'ADMISSION')
            admission_id = request.POST.get('admission_id')
            previous_due_id = request.POST.get('previous_due_id')
            amount_str = request.POST.get('amount', '0').strip()
            payment_mode = request.POST.get('payment_mode', 'UPI')
            payment_date_str = request.POST.get('payment_date')
            reference_number = request.POST.get('reference_number', '').strip() or None
            notes = request.POST.get('notes', '').strip() or None
            next_due_date_str = request.POST.get('next_due_date', '').strip()
            allow_duplicate = request.POST.get('allow_duplicate') in ('true', 'on', True)

            try:
                amount = parse_non_negative_money(amount_str)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(f"{request.path}?tab=collect&student_id={student_id}")

            student = get_object_or_404(Student, id=student_id)

            if amount <= 0:
                messages.error(request, "Please enter a valid positive payment amount.")
                return redirect(f"{request.path}?tab=collect&student_id={student.id}")

            # Parse payment date
            try:
                parsed_payment_date = parse_form_date(payment_date_str, default=timezone.now())
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(f"{request.path}?tab=collect&student_id={student.id}")

            # Duplicate safety check within 5 minutes
            if not allow_duplicate:
                five_mins_ago = timezone.now() - timedelta(minutes=5)
                duplicate_payment = Payment.objects.filter(
                    student=student,
                    total_amount=amount,
                    payment_mode=payment_mode,
                    created_at__gte=five_mins_ago,
                    is_reversed=False
                ).first()
                if duplicate_payment:
                    msg = f"A payment of ₹{amount:,.0f} via {payment_mode} was recorded just now (Receipt #{duplicate_payment.receipt_number}). If intentional, confirm duplicate payment."
                    messages.warning(request, msg)
                    return redirect(f"{request.path}?tab=collect&student_id={student.id}&amount={amount}&confirm_duplicate=true")

            # Route A: Previous Session Due Payment
            if target_type == 'PREVIOUS_DUE' and previous_due_id:
                _, scope_s_id, _, _ = get_active_scope(request)
                prev_due_lookup = {'id': previous_due_id, 'student': student}
                if scope_s_id and scope_s_id != 'ALL':
                    prev_due_lookup['current_session_id'] = scope_s_id
                prev_due = get_object_or_404(PreviousSessionDue, **prev_due_lookup)
                due_remaining = max(MONEY_ZERO, prev_due.outstanding_amount - prev_due.collected_amount)

                if amount > due_remaining:
                    messages.error(request, f"Payment amount (₹{amount:,.0f}) exceeds remaining previous session due balance (₹{due_remaining:,.0f}).")
                    return redirect(f"{request.path}?tab=collect&student_id={student.id}")

                active_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.first()
                target_branch = active_adm.branch if active_adm else Branch.objects.filter(is_active=True).first()
                target_session = prev_due.current_session

                with transaction.atomic():
                    receipt_no = generate_sequential_receipt_number(target_branch, target_session)
                    payment = Payment.objects.create(
                        student=student,
                        branch=target_branch,
                        session=target_session,
                        previous_due=prev_due,
                        receipt_number=receipt_no,
                        total_amount=amount,
                        payment_mode=payment_mode,
                        payment_date=parsed_payment_date,
                        reference_number=reference_number,
                        notes=notes or f"Payment towards carried-forward dues from {prev_due.original_session.name}",
                    )
                    prev_due.collected_amount += amount
                    prev_due.save()

                messages.success(request, f"Payment of ₹{amount:,.0f} recorded! Receipt #{receipt_no} generated.")
                return redirect(f"{request.path}?tab=history&q={receipt_no}&open_receipt={payment.id}")

            # Route B: Admission Installment Payment
            target_adm = None
            if admission_id:
                target_adm = student.admissions.filter(id=admission_id).first()
            if not target_adm:
                target_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.first()

            if not target_adm:
                messages.error(request, "Student has no admission records.")
                return redirect('fee_collect')

            fee_plan = getattr(target_adm, 'fee_plan', None)
            net_payable = fee_plan.net_payable if fee_plan else MONEY_ZERO
            already_paid = sum(p.total_amount for p in target_adm.payments.filter(is_reversed=False))
            pending_due = max(MONEY_ZERO, net_payable - already_paid)

            if amount > pending_due:
                messages.error(request, f"Payment amount (₹{amount:,.0f}) exceeds remaining balance (₹{pending_due:,.0f}) for {target_adm.session.name}. Overpayment is prevented.")
                return redirect(f"{request.path}?tab=collect&student_id={student.id}")

            if fee_plan:
                installment_capacity = sum(
                    max(
                        MONEY_ZERO,
                        inst.amount_due - sum(
                            (a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False)),
                            MONEY_ZERO,
                        ),
                    )
                    for inst in fee_plan.installments.all()
                )
                if amount > installment_capacity + Decimal('0.005'):
                    messages.error(
                        request,
                        "This fee plan's installment balances cannot fully accept the payment. "
                        "Please correct the installments before collecting the payment."
                    )
                    return redirect(f"{request.path}?tab=collect&student_id={student.id}")

            next_due_datetime = None
            if next_due_date_str:
                try:
                    next_due_datetime = parse_form_date(next_due_date_str)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect(f"{request.path}?tab=collect&student_id={student.id}")

            with transaction.atomic():
                receipt_no = generate_sequential_receipt_number(target_adm.branch, target_adm.session)
                payment = Payment.objects.create(
                    student=student,
                    branch=target_adm.branch,
                    session=target_adm.session,
                    admission=target_adm,
                    receipt_number=receipt_no,
                    total_amount=amount,
                    payment_mode=payment_mode,
                    payment_date=parsed_payment_date,
                    reference_number=reference_number,
                    notes=notes,
                )

                # Allocate payment across installments using FIFO
                if fee_plan:
                    remaining_amount = amount
                    for inst in fee_plan.installments.all().order_by('installment_no'):
                        if remaining_amount <= 0:
                            break
                        inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                        needed = max(MONEY_ZERO, inst.amount_due - inst_paid)
                        if needed > 0:
                            alloc_now = min(remaining_amount, needed)
                            PaymentAllocation.objects.create(
                                payment=payment,
                                installment=inst,
                                allocated_amount=alloc_now,
                            )
                            remaining_amount -= alloc_now

                    if remaining_amount > 0.005:
                        raise RuntimeError("Payment allocation invariant failed after validation.")

                    # Update next promise due date if balance remains
                    if next_due_datetime and (pending_due - amount) > 0:
                        for inst in fee_plan.installments.all().order_by('installment_no'):
                            inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                            if inst.amount_due > inst_paid:
                                inst.due_date = next_due_datetime
                                inst.save()
                                break

            messages.success(request, f"Payment of ₹{amount:,.0f} recorded! Receipt #{receipt_no} generated.")
            return redirect(f"{request.path}?tab=history&q={receipt_no}&open_receipt={payment.id}")

    # GET: Assemble View
    tab = request.GET.get('tab', 'collect')
    student_id = request.GET.get('student_id')
    admission_id = request.GET.get('admission_id')
    previous_due_id = request.GET.get('previous_due_id')
    prefill_amount = request.GET.get('amount', '')
    confirm_duplicate = request.GET.get('confirm_duplicate') == 'true'
    open_receipt_id = request.GET.get('open_receipt')

    branches = Branch.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-start_date')
    courses = Course.objects.filter(is_active=True).order_by('sort_order', 'name')

    selected_student = None
    target_admission = None
    target_previous_due = None
    all_admissions = []
    installments_data = []
    fee_summary = {
        'total_fees': 0.0,
        'paid_fees': 0.0,
        'pending_fees': 0.0,
        'other_sessions_pending': 0.0,
        'previous_dues_pending': 0.0,
        'overall_pending': 0.0,
        'lifetime_total_fees': 0.0,
        'lifetime_paid_fees': 0.0,
        'lifetime_pending_fees': 0.0,
    }
    amount_in_words = ''

    if student_id:
        selected_student = Student.objects.filter(id=student_id).prefetch_related(
            'admissions__branch', 'admissions__session', 'admissions__fee_plan__installments__allocations__payment',
            'previous_dues__original_session', 'previous_dues__current_session', 'payments'
        ).first()

        if selected_student:
            scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
            if admission_id:
                target_admission = selected_student.admissions.filter(id=admission_id).first()
            if not target_admission:
                if scope_s_id and scope_s_id != 'ALL':
                    target_admission = selected_student.admissions.filter(session_id=scope_s_id).first()
                if not target_admission and scope_b_id and scope_b_id != 'ALL':
                    target_admission = selected_student.admissions.filter(branch_id=scope_b_id).first()
            if not target_admission:
                target_admission = selected_student.admissions.filter(is_active=True).order_by('-created_at').first() or selected_student.admissions.first()

            # Multi-session tab switcher data
            admissions_qs = selected_student.admissions.select_related('branch', 'session', 'fee_plan').prefetch_related(
                'payments', 'fee_plan__installments'
            ).order_by('-created_at')
            all_admissions = list(admissions_qs)
            for adm in all_admissions:
                adm_fp = getattr(adm, 'fee_plan', None)
                adm_tot = adm_fp.net_payable if adm_fp and adm_fp.net_payable else MONEY_ZERO
                adm_payments = [p for p in adm.payments.all() if not p.is_reversed]
                adm_paid = sum((p.total_amount for p in adm_payments), MONEY_ZERO)
                adm_pend = max(MONEY_ZERO, adm_tot - adm_paid)
                adm.adm_total = adm_tot
                adm.adm_paid = adm_paid
                adm.adm_pending = adm_pend
                adm.is_selected = bool(target_admission and adm.id == target_admission.id)
                adm.is_latest = bool(all_admissions and adm == all_admissions[0])

            if previous_due_id:
                previous_due_filter = {'id': previous_due_id}
                if target_admission:
                    previous_due_filter['current_session_id'] = target_admission.session_id
                elif scope_s_id and scope_s_id != 'ALL':
                    previous_due_filter['current_session_id'] = scope_s_id
                target_previous_due = selected_student.previous_dues.filter(**previous_due_filter).first()

            fp = getattr(target_admission, 'fee_plan', None) if target_admission else None
            tot_f = fp.net_payable if fp else MONEY_ZERO
            paid_f = sum((p.total_amount for p in target_admission.payments.filter(is_reversed=False)), MONEY_ZERO) if target_admission else MONEY_ZERO
            pend_f = max(MONEY_ZERO, tot_f - paid_f)

            # Pure session-based calculation: each session strictly manages its own fees
            other_sessions_pending = sum((adm.adm_pending for adm in all_admissions if target_admission and adm.id != target_admission.id), MONEY_ZERO)
            lifetime_total_fees = sum((adm.adm_total for adm in all_admissions), MONEY_ZERO)
            lifetime_paid_fees = sum((adm.adm_paid for adm in all_admissions), MONEY_ZERO)
            lifetime_pending_fees = sum((adm.adm_pending for adm in all_admissions), MONEY_ZERO)

            fee_summary = {
                'total_fees': tot_f,
                'paid_fees': paid_f,
                'pending_fees': pend_f,
                'other_sessions_pending': other_sessions_pending,
                'previous_dues_pending': other_sessions_pending,  # alias for backward-compatibility
                'overall_pending': lifetime_pending_fees,
                'lifetime_total_fees': lifetime_total_fees,
                'lifetime_paid_fees': lifetime_paid_fees,
                'lifetime_pending_fees': lifetime_pending_fees,
            }

            if not prefill_amount:
                if pend_f > 0:
                    prefill_amount = str(int(pend_f))

            if prefill_amount:
                try:
                    amount_in_words = number_to_words_inr(float(prefill_amount))
                except Exception:
                    pass

            if fp:
                for inst in fp.installments.all().order_by('installment_no'):
                    inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                    inst_bal = max(MONEY_ZERO, inst.amount_due - inst_paid)
                    is_cleared = inst_bal <= 0 or pend_f <= 0
                    status = 'PAID' if is_cleared else inst.status
                    installments_data.append({
                        'installment': inst,
                        'paid': inst_paid,
                        'balance': inst_bal,
                        'is_cleared': is_cleared,
                        'status': status,
                    })

    # History Tab Assembly
    payments_qs = Payment.objects.select_related(
        'student', 'branch', 'session', 'admission', 'previous_due'
    ).prefetch_related('allocations__installment').order_by('-payment_date', '-created_at')

    # Filters with Scope Isolation
    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    q_search = request.GET.get('q', '').strip()
    filter_mode = request.GET.get('payment_mode', 'ALL')
    filter_branch = request.GET.get('branch_id')
    if filter_branch is None:
        filter_branch = scope_b_id

    filter_session = request.GET.get('session_id')
    if filter_session is None or filter_session == 'CURRENT':
        filter_session = scope_s_id

    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if filter_branch and filter_branch != 'ALL':
        payments_qs = payments_qs.filter(branch_id=filter_branch)
    if filter_session and filter_session != 'ALL':
        payments_qs = payments_qs.filter(session_id=filter_session)
    if filter_mode and filter_mode != 'ALL':
        payments_qs = payments_qs.filter(payment_mode=filter_mode)

    if date_from:
        try:
            d_from = timezone.make_aware(datetime.strptime(date_from, '%Y-%m-%d'))
            payments_qs = payments_qs.filter(payment_date__gte=d_from)
        except Exception:
            pass

    if date_to:
        try:
            d_to = timezone.make_aware(datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            payments_qs = payments_qs.filter(payment_date__lte=d_to)
        except Exception:
            pass

    if q_search:
        payments_qs = payments_qs.filter(
            Q(receipt_number__icontains=q_search) |
            Q(student__full_name__icontains=q_search) |
            Q(student__student_code__icontains=q_search) |
            Q(student__parent_phone__icontains=q_search) |
            Q(reference_number__icontains=q_search) |
            Q(admission__roll_number__icontains=q_search) |
            Q(admission__standard__icontains=q_search)
        )

    # Server-Side Column Sorting
    sort_by = request.GET.get('sort', '').lower()
    sort_dir = request.GET.get('dir', 'desc').lower()
    sort_map = {
        'receipt': 'receipt_number',
        'date': 'payment_date',
        'student': 'student__full_name',
        'roll': 'admission__roll_number',
        'class': 'admission__standard',
        'branch': 'branch__name',
        'mode': 'payment_mode',
        'amount': 'total_amount',
        'status': 'is_reversed',
    }
    if sort_by in sort_map:
        field = sort_map[sort_by]
        prefix = '-' if sort_dir == 'desc' else ''
        payments_qs = payments_qs.order_by(f"{prefix}{field}")
    else:
        payments_qs = payments_qs.order_by('-payment_date', '-created_at')

    # Export handling (Excel / PDF)
    export_type = request.GET.get('export', '').lower()
    if export_type in ('excel', 'pdf'):
        export_payments = list(payments_qs)
        branch_name_label = 'All Branches'
        if filter_branch and filter_branch != 'ALL':
            b_match = Branch.objects.filter(id=filter_branch).first()
            if b_match:
                branch_name_label = b_match.name

        session_name_label = 'All Sessions'
        if filter_session and filter_session != 'ALL':
            s_match = AcademicSession.objects.filter(id=filter_session).first()
            if s_match:
                session_name_label = s_match.name

        today_str = timezone.now().strftime("%d_%b_%Y")
        meta = {
            'branch_name': branch_name_label,
            'session_name': session_name_label,
        }

        if export_type == 'excel':
            excel_bytes = export_payments_to_excel(export_payments, meta)
            filename = f"Fee_Collections_Ledger_{branch_name_label.replace(' ', '_')}_{today_str}.xlsx"
            response = HttpResponse(
                excel_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        elif export_type == 'pdf':
            pdf_bytes = export_payments_to_pdf(export_payments, meta)
            filename = f"Fee_Collections_Ledger_{branch_name_label.replace(' ', '_')}_{today_str}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    try:
        page_size = int(request.GET.get('page_size', 25))
        if page_size not in (10, 25, 50, 100):
            page_size = 25
    except (TypeError, ValueError):
        page_size = 25

    try:
        page_num = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page_num = 1

    paginator = Paginator(payments_qs, page_size)
    try:
        page_obj = paginator.get_page(page_num)
    except Exception:
        page_obj = paginator.get_page(1)

    local_now = timezone.localtime()
    local_today = local_now.date()
    start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)

    total_collected_sum = sum((p.total_amount for p in payments_qs.filter(is_reversed=False)), MONEY_ZERO)
    today_payments_qs = payments_qs.filter(
        is_reversed=False
    ).filter(
        Q(payment_date__range=[start_of_today, end_of_today]) | Q(payment_date__date=local_today)
    ).distinct()
    today_collected_sum = sum((p.total_amount for p in today_payments_qs), MONEY_ZERO)
    total_receipts_count = payments_qs.count()
    reversed_receipts_count = payments_qs.filter(is_reversed=True).count()

    context = {
        'active_tab': tab,
        'selected_student': selected_student,
        'student_id': student_id,
        'target_admission': target_admission,
        'target_previous_due': target_previous_due,
        'all_admissions': all_admissions,
        'prefill_amount': prefill_amount,
        'confirm_duplicate': confirm_duplicate,
        'amount_in_words': amount_in_words,
        'fee_summary': fee_summary,
        'installments_data': installments_data,
        'payments': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'open_receipt_id': open_receipt_id,
        'kpis': {
            'total_collected': total_collected_sum,
            'today_collected': today_collected_sum,
            'total_receipts': total_receipts_count,
            'reversed_receipts': reversed_receipts_count,
        },
        'branches': branches,
        'sessions': sessions,
        'courses': courses,
        'filters': {
            'q': q_search,
            'payment_mode': filter_mode,
            'branch_id': filter_branch,
            'session_id': filter_session,
            'date_from': date_from,
            'date_to': date_to,
            'sort': sort_by,
            'dir': sort_dir,
            'page_size': page_size,
            'page': page_num,
        },
    }
    return render(request, 'fee_collect.html', context)


def collect_fee_modal_view(request, student_id):
    """
    Renders and processes standalone Collect Fee modal dialog via HTMX directly on Student Profile.
    Does NOT redirect away from student profile.
    Maintains pure independent session accounting.
    """
    student = get_object_or_404(Student, id=student_id)

    # Multi-session data for student
    admissions_qs = student.admissions.select_related('branch', 'session', 'fee_plan').prefetch_related(
        'payments', 'fee_plan__installments'
    ).order_by('-created_at')
    all_admissions = list(admissions_qs)

    for adm in all_admissions:
        adm_fp = getattr(adm, 'fee_plan', None)
        adm_tot = adm_fp.net_payable if adm_fp and adm_fp.net_payable else MONEY_ZERO
        adm_payments = [p for p in adm.payments.all() if not p.is_reversed]
        adm_paid = sum((p.total_amount for p in adm_payments), MONEY_ZERO)
        adm.adm_total = adm_tot
        adm.adm_paid = adm_paid
        adm.adm_pending = max(MONEY_ZERO, adm_tot - adm_paid)

    if request.method == 'POST':
        admission_id = request.POST.get('admission_id')
        target_adm = None
        if admission_id:
            target_adm = student.admissions.filter(id=admission_id).first()
        if not target_adm:
            target_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.first()

        for adm in all_admissions:
            adm.is_selected = bool(target_adm and adm.id == target_adm.id)

        fee_plan = getattr(target_adm, 'fee_plan', None) if target_adm else None
        tot_f = fee_plan.net_payable if fee_plan else MONEY_ZERO
        already_paid = sum((p.total_amount for p in target_adm.payments.filter(is_reversed=False)), MONEY_ZERO) if target_adm else MONEY_ZERO
        pending_due = max(MONEY_ZERO, tot_f - already_paid)

        other_sessions_pending = sum((adm.adm_pending for adm in all_admissions if target_adm and adm.id != target_adm.id), MONEY_ZERO)
        overall_pending = sum((adm.adm_pending for adm in all_admissions), MONEY_ZERO)

        amount_str = request.POST.get('amount', '').strip()
        payment_mode = request.POST.get('payment_mode', 'UPI')
        reference_number = request.POST.get('reference_number', '').strip() or None
        payment_date_str = request.POST.get('payment_date', '').strip()
        next_due_date_str = request.POST.get('next_due_date', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        form_error = None
        amount = MONEY_ZERO
        try:
            amount = Decimal(amount_str)
            if amount <= MONEY_ZERO:
                form_error = "Payment amount must be greater than zero."
        except Exception:
            form_error = "Please enter a valid numeric payment amount."

        if not form_error and amount > pending_due + Decimal('0.005'):
            form_error = f"Amount ₹{amount:,.0f} exceeds pending session due of ₹{pending_due:,.0f} for {target_adm.session.name}."

        parsed_payment_date = timezone.now()
        if not form_error and payment_date_str:
            try:
                parsed_payment_date = parse_form_date(payment_date_str)
            except ValueError as exc:
                form_error = str(exc)

        if form_error:
            context = {
                'student': student,
                'current_admission': target_adm,
                'all_admissions': all_admissions,
                'agreed_fees': tot_f,
                'paid_fees': already_paid,
                'pending_fees': pending_due,
                'other_sessions_pending': other_sessions_pending,
                'overall_pending': overall_pending,
                'amount_to_pay': amount_str,
                'form_error': form_error,
            }
            return render(request, 'modals/collect_fee_modal.html', context)

        next_due_datetime = None
        if next_due_date_str:
            try:
                next_due_datetime = parse_form_date(next_due_date_str)
            except ValueError:
                pass

        with transaction.atomic():
            receipt_no = generate_sequential_receipt_number(target_adm.branch, target_adm.session)
            payment = Payment.objects.create(
                student=student,
                branch=target_adm.branch,
                session=target_adm.session,
                admission=target_adm,
                receipt_number=receipt_no,
                total_amount=amount,
                payment_mode=payment_mode,
                payment_date=parsed_payment_date,
                reference_number=reference_number,
                notes=notes,
            )

            # Allocate across installments using FIFO
            if fee_plan:
                remaining_amount = amount
                for inst in fee_plan.installments.all().order_by('installment_no'):
                    if remaining_amount <= 0:
                        break
                    inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                    needed = max(MONEY_ZERO, inst.amount_due - inst_paid)
                    if needed > 0:
                        alloc_now = min(remaining_amount, needed)
                        PaymentAllocation.objects.create(
                            payment=payment,
                            installment=inst,
                            allocated_amount=alloc_now,
                        )
                        remaining_amount -= alloc_now

                # Update next due date if specified
                if next_due_datetime and (pending_due - amount) > 0:
                    for inst in fee_plan.installments.all().order_by('installment_no'):
                        inst_paid = sum(a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False))
                        if inst.amount_due > inst_paid:
                            inst.due_date = next_due_datetime
                            inst.save()
                            break

        remaining_after = max(MONEY_ZERO, pending_due - amount)
        context = {
            'student': student,
            'current_admission': target_adm,
            'all_admissions': all_admissions,
            'payment': payment,
            'amount_paid': amount,
            'remaining_after': remaining_after,
            'success': True,
        }
        return render(request, 'modals/collect_fee_modal.html', context)

    # GET Request
    admission_id = request.GET.get('admission_id')
    initial_amount = request.GET.get('amount')

    target_adm = None
    if admission_id:
        target_adm = student.admissions.filter(id=admission_id).first()
    if not target_adm:
        target_adm = student.admissions.filter(is_active=True).order_by('-created_at').first() or student.admissions.first()

    for adm in all_admissions:
        adm.is_selected = bool(target_adm and adm.id == target_adm.id)

    fp = getattr(target_adm, 'fee_plan', None) if target_adm else None
    tot_f = fp.net_payable if fp else MONEY_ZERO
    paid_f = sum((p.total_amount for p in target_adm.payments.filter(is_reversed=False)), MONEY_ZERO) if target_adm else MONEY_ZERO
    pend_f = max(MONEY_ZERO, tot_f - paid_f)

    other_sessions_pending = sum((adm.adm_pending for adm in all_admissions if target_adm and adm.id != target_adm.id), MONEY_ZERO)
    overall_pending = sum((adm.adm_pending for adm in all_admissions), MONEY_ZERO)

    amount_to_pay = initial_amount
    if not amount_to_pay or amount_to_pay == '0':
        amount_to_pay = pend_f

    context = {
        'student': student,
        'current_admission': target_adm,
        'all_admissions': all_admissions,
        'agreed_fees': tot_f,
        'paid_fees': paid_f,
        'pending_fees': pend_f,
        'other_sessions_pending': other_sessions_pending,
        'overall_pending': overall_pending,
        'amount_to_pay': amount_to_pay,
    }
    return render(request, 'modals/collect_fee_modal.html', context)


def api_student_fee_search_view(request):
    """
    HTMX live student autocomplete search endpoint for Fee Collection screen.
    """
    q = request.GET.get('q', '').strip()
    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    branch_id = request.GET.get('branch_id') or scope_b_id
    session_id = request.GET.get('session_id') or scope_s_id

    admissions = StudentAdmission.objects.filter(is_active=True).select_related('student', 'branch', 'session', 'fee_plan').prefetch_related('payments')

    if branch_id and branch_id != 'ALL':
        admissions = admissions.filter(branch_id=branch_id)
    if session_id and session_id != 'ALL':
        admissions = admissions.filter(session_id=session_id)

    if q:
        for term in q.split():
            admissions = admissions.filter(
                Q(student__full_name__icontains=term) |
                Q(roll_number__icontains=term) |
                Q(student__student_code__icontains=term) |
                Q(student__parent_phone__icontains=term) |
                Q(student__student_phone__icontains=term) |
                Q(standard__icontains=term)
            )

    results = []
    for adm in admissions[:15]:
        tot = adm.fee_plan.net_payable if hasattr(adm, 'fee_plan') else MONEY_ZERO
        paid = sum(p.total_amount for p in adm.payments.filter(is_reversed=False))
        pending = max(MONEY_ZERO, tot - paid)
        results.append({
            'student_id': adm.student.id,
            'admission_id': adm.id,
            'full_name': adm.student.full_name,
            'student_code': adm.student.student_code,
            'roll_number': adm.roll_number,
            'standard': adm.standard,
            'branch_name': adm.branch.name,
            'pending_fees': pending,
        })

    return render(request, 'includes/fee_search_results.html', {'results': results, 'q': q})


def payment_receipt_modal_view(request, payment_id):
    """
    Renders printable dual-copy fee receipt modal (A4 Student/Office Copy & Thermal 80mm).
    Matches React FeeReceiptModal.tsx.
    """
    payment = get_object_or_404(
        Payment.objects.select_related('student', 'branch', 'session', 'admission', 'previous_due'),
        id=payment_id
    )

    allocations = payment.allocations.select_related('installment').all()

    # Remaining balance for this admission or previous due
    remaining_balance = MONEY_ZERO
    if payment.admission and hasattr(payment.admission, 'fee_plan'):
        fp = payment.admission.fee_plan
        tot = fp.net_payable
        paid = sum(p.total_amount for p in payment.admission.payments.filter(is_reversed=False))
        remaining_balance = max(MONEY_ZERO, tot - paid)
    elif payment.previous_due:
        pd = payment.previous_due
        remaining_balance = max(MONEY_ZERO, pd.outstanding_amount - pd.collected_amount)

    amount_in_words = number_to_words_inr(payment.total_amount)

    # Pre-generate WhatsApp message & deep link
    whatsapp_url = None
    target_phone = payment.student.parent_phone or payment.student.student_phone
    if target_phone:
        msg = build_receipt_whatsapp_message(
            institute_name="Sutawane Classes",
            student_name=payment.student.full_name,
            student_code=payment.student.student_code,
            roll_number=payment.admission.roll_number if payment.admission else '',
            standard=payment.admission.standard if payment.admission else 'General',
            receipt_number=payment.receipt_number,
            total_amount=payment.total_amount,
            payment_date=timezone.localtime(payment.payment_date).strftime('%d %B %Y') if payment.payment_date else '',
            payment_mode=payment.payment_mode,
            reference_number=payment.reference_number or '',
            remaining_balance=remaining_balance,
            branch_name=payment.branch.name if payment.branch else '',
            helpline=payment.branch.phone if payment.branch else '',
        )
        whatsapp_url = generate_whatsapp_url(target_phone, msg)

    context = {
        'payment': payment,
        'allocations': allocations,
        'remaining_balance': remaining_balance,
        'amount_in_words': amount_in_words,
        'whatsapp_url': whatsapp_url,
        'institute_settings': get_institute_settings_dict(),
    }
    return render(request, 'modals/fee_receipt_modal.html', context)


def payment_receipt_print_view(request, payment_id):
    """
    Dedicated full-page printable receipt sheet supporting A4 Dual-Copy,
    Student Slip, Office Slip, and 80mm Thermal Receipt.
    Matches React FeeReceiptModal print output.
    """
    payment = get_object_or_404(
        Payment.objects.select_related('student', 'branch', 'session', 'admission', 'previous_due'),
        id=payment_id
    )
    allocations = payment.allocations.select_related('installment').all()

    remaining_balance = MONEY_ZERO
    if payment.admission and hasattr(payment.admission, 'fee_plan'):
        fp = payment.admission.fee_plan
        tot = fp.net_payable
        paid = sum(p.total_amount for p in payment.admission.payments.filter(is_reversed=False))
        remaining_balance = max(MONEY_ZERO, tot - paid)
    elif payment.previous_due:
        pd = payment.previous_due
        remaining_balance = max(MONEY_ZERO, pd.outstanding_amount - pd.collected_amount)

    amount_in_words = number_to_words_inr(payment.total_amount)
    current_mode = request.GET.get('format', 'a4_dual').lower()
    if current_mode not in ['a4_dual', 'student_only', 'office_only', 'thermal']:
        current_mode = 'a4_dual'

    autoprint = request.GET.get('autoprint', '0') == '1'

    whatsapp_url = None
    target_phone = payment.student.parent_phone or payment.student.student_phone
    if target_phone:
        msg = build_receipt_whatsapp_message(
            institute_name="Sutawane Classes",
            student_name=payment.student.full_name,
            student_code=payment.student.student_code,
            roll_number=payment.admission.roll_number if payment.admission else '',
            standard=payment.admission.standard if payment.admission else 'General',
            receipt_number=payment.receipt_number,
            total_amount=payment.total_amount,
            payment_date=timezone.localtime(payment.payment_date).strftime('%d %B %Y') if payment.payment_date else '',
            payment_mode=payment.payment_mode,
            reference_number=payment.reference_number or '',
            remaining_balance=remaining_balance,
            branch_name=payment.branch.name if payment.branch else '',
            helpline=payment.branch.phone if payment.branch else '',
        )
        whatsapp_url = generate_whatsapp_url(target_phone, msg)

    context = {
        'payment': payment,
        'allocations': allocations,
        'remaining_balance': remaining_balance,
        'amount_in_words': amount_in_words,
        'current_mode': current_mode,
        'autoprint': autoprint,
        'whatsapp_url': whatsapp_url,
        'institute_settings': get_institute_settings_dict(),
    }
    return render(request, 'receipt_print.html', context)


def payment_receipt_void_view(request, payment_id):
    """
    Cancels/voids an official fee receipt with audit trail.
    Restores student pending dues.
    """
    payment = get_object_or_404(Payment.objects.select_related('student', 'previous_due'), id=payment_id)
    if payment.is_reversed:
        messages.warning(request, f"Receipt #{payment.receipt_number} has already been reversed.")
        return redirect('fee_collect')

    if request.method == 'POST':
        reversal_reason = request.POST.get('reversal_reason', '').strip()
        if not reversal_reason:
            messages.error(request, "A specific mandatory reason is required to void/reverse a receipt.")
            return redirect('fee_collect')

        with transaction.atomic():
            payment.is_reversed = True
            payment.reversal_reason = reversal_reason
            payment.reversed_at = timezone.now()
            payment.save()

            if payment.previous_due:
                pd = payment.previous_due
                pd.collected_amount = max(MONEY_ZERO, pd.collected_amount - payment.total_amount)
                pd.save()

        messages.success(request, f"Fee Receipt #{payment.receipt_number} has been voided/reversed successfully. Balances restored.")
        return redirect('fee_collect')

    return redirect('fee_collect')


def fees_dues_view(request):
    """
    Student Fee Dues Register & Defaulters Tracker.
    Matches React DuesPage.tsx with 4 KPI cards, universal search, 5-tab quick filters,
    sorting, date presets, WhatsApp reminders, Excel/PDF exports, and due date updating.
    """
    # 1. Handle POST Actions (e.g. Quick Due Date Extension)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_due_date':
            installment_id = request.POST.get('installment_id')
            new_date_str = request.POST.get('due_date', '').strip()
            if installment_id and new_date_str:
                inst = get_object_or_404(Installment, id=installment_id)
                try:
                    inst.due_date = parse_form_date(new_date_str)
                    inst.save()
                    messages.success(request, f"Fee due date for {inst.label} updated to {new_date_str} successfully!")
                except ValueError as e:
                    messages.error(request, f"Failed to update due date: {e}")
            return redirect(request.get_full_path())

    # 2. Extract Query Parameters
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'ALL').upper()
    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    branch_filter = request.GET.get('branch_id')
    if branch_filter is None:
        branch_filter = scope_b_id

    session_filter = request.GET.get('session_id')
    if session_filter is None or session_filter == 'CURRENT':
        session_filter = scope_s_id

    standard_filter = request.GET.get('standard', 'ALL')
    date_preset = request.GET.get('date_preset', 'ALL').upper()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    sort_field = request.GET.get('sort', 'dueDate')
    sort_direction = request.GET.get('direction', 'asc').lower()
    try:
        page_size = int(request.GET.get('page_size', 25))
        if page_size not in (10, 25, 50, 100):
            page_size = 25
    except (TypeError, ValueError):
        page_size = 25

    try:
        page_num = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page_num = 1
    export_type = request.GET.get('export', '').lower()

    # 3. Query Admissions
    adm_query = StudentAdmission.objects.filter(is_active=True).select_related(
        'student', 'branch', 'session', 'fee_plan'
    ).prefetch_related(
        'fee_plan__installments',
        'fee_plan__installments__allocations__payment',
        'student__previous_dues',
        'student__previous_dues__original_session',
    )

    if branch_filter and branch_filter != 'ALL':
        adm_query = adm_query.filter(branch_id=branch_filter)
    if session_filter and session_filter != 'ALL':
        adm_query = adm_query.filter(session_id=session_filter)
    if standard_filter and standard_filter != 'ALL':
        adm_query = adm_query.filter(standard=standard_filter)

    today = timezone.localtime().date()
    raw_dues = []

    for adm in adm_query:
        student = adm.student
        if not hasattr(adm, 'fee_plan'):
            continue
        fp = adm.fee_plan

        # Calculate previous dues
        prev_dues_qs = student.previous_dues.all()
        if adm.session_id and session_filter != 'ALL':
            prev_dues_qs = prev_dues_qs.filter(current_session_id=adm.session_id)
        prev_dues_pending = sum(
            max(MONEY_ZERO, pd.outstanding_amount - pd.collected_amount)
            for pd in prev_dues_qs
        )

        for inst in fp.installments.all().order_by('installment_no'):
            paid = sum(
                a.allocated_amount for a in inst.allocations.filter(payment__is_reversed=False)
            )
            balance = max(MONEY_ZERO, inst.amount_due - paid)

            # STRICT RULE: Cleared / 0 balance students MUST NEVER appear in dues register
            if balance <= 0.0:
                continue

            inst_date = timezone.localtime(inst.due_date).date() if inst.due_date else None
            if paid > 0 and paid < inst.amount_due:
                computed_status = 'PARTIAL'
            elif not inst_date:
                computed_status = 'UPCOMING'
            elif today > inst_date:
                computed_status = 'OVERDUE'
            elif today == inst_date:
                computed_status = 'DUE'
            else:
                computed_status = 'UPCOMING'

            days_overdue = (today - inst_date).days if inst_date and today > inst_date else 0
            overall_pending = balance + prev_dues_pending

            wa_url = None
            if student.parent_phone:
                msg = build_fee_reminder_whatsapp_message(
                    institute_name="Sutawane Classes",
                    student_name=student.full_name,
                    student_code=student.student_code,
                    roll_number=adm.roll_number,
                    standard=adm.standard,
                    current_pending_amount=balance,
                    previous_dues_pending=prev_dues_pending,
                    overall_pending_amount=overall_pending,
                    next_due_date=inst_date.strftime('%d %B %Y') if inst_date else None,
                    branch_name=adm.branch.name if adm.branch else '',
                    session_name=adm.session.name if adm.session else '',
                    helpline=adm.branch.phone if adm.branch else '',
                )
                wa_url = generate_whatsapp_url(student.parent_phone, msg)

            raw_dues.append({
                'id': inst.id,
                'installment_id': inst.id,
                'installment_no': inst.installment_no,
                'label': inst.label,
                'due_date': inst_date,
                'due_date_iso': inst_date.strftime('%Y-%m-%d') if inst_date else '',
                'due_date_formatted': inst_date.strftime('%d %b %Y') if inst_date else '—',
                'amount_due': inst.amount_due,
                'amount_paid': paid,
                'balance_remaining': balance,
                'status': computed_status,
                'days_overdue': days_overdue,
                'admission_id': adm.id,
                'branch_id': adm.branch_id,
                'branch_name': adm.branch.name if adm.branch else '—',
                'session_id': adm.session_id,
                'session_name': adm.session.name if adm.session else '—',
                'student_id': student.id,
                'student_name': student.full_name,
                'student_code': student.student_code,
                'roll_number': adm.roll_number or '—',
                'standard': adm.standard or '—',
                'parent_phone': student.parent_phone or '—',
                'student_phone': student.student_phone or '—',
                'previous_dues_pending': prev_dues_pending,
                'overall_pending_amount': overall_pending,
                'whatsapp_url': wa_url,
            })

    # 4. Global KPI Aggregations (across all raw dues before status/date filtering)
    overdue_list = [d for d in raw_dues if d['status'] == 'OVERDUE']
    due_today_list = [d for d in raw_dues if d['status'] == 'DUE']
    partial_list = [d for d in raw_dues if d['status'] == 'PARTIAL']
    upcoming_list = [d for d in raw_dues if d['status'] == 'UPCOMING']

    kpis = {
        'total_pending_amount': sum(d['balance_remaining'] for d in raw_dues),
        'total_overdue_amount': sum(d['balance_remaining'] for d in overdue_list),
        'overdue_count': len(overdue_list),
        'total_due_today_amount': sum(d['balance_remaining'] for d in due_today_list),
        'due_today_count': len(due_today_list),
        'partial_count': len(partial_list),
        'upcoming_count': len(upcoming_list),
        'total_accounts': len(raw_dues),
    }

    # 5. Filter Pipeline
    filtered_dues = list(raw_dues)

    # Status Filter
    if status_filter != 'ALL':
        filtered_dues = [d for d in filtered_dues if d['status'] == status_filter]

    # Date Range Preset Filter
    if date_preset == 'OVERDUE':
        filtered_dues = [d for d in filtered_dues if d['due_date'] and d['due_date'] < today]
    elif date_preset == 'TODAY':
        filtered_dues = [d for d in filtered_dues if d['due_date'] and d['due_date'] == today]
    elif date_preset == 'THIS_WEEK':
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        filtered_dues = [d for d in filtered_dues if d['due_date'] and week_start <= d['due_date'] <= week_end]
    elif date_preset == 'THIS_MONTH':
        month_start = today.replace(day=1)
        next_m = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_m - timedelta(days=1)
        filtered_dues = [d for d in filtered_dues if d['due_date'] and month_start <= d['due_date'] <= month_end]
    elif date_preset == 'CUSTOM':
        if start_date_str:
            try:
                sd = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                filtered_dues = [d for d in filtered_dues if d['due_date'] and d['due_date'] >= sd]
            except Exception:
                pass
        if end_date_str:
            try:
                ed = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                filtered_dues = [d for d in filtered_dues if d['due_date'] and d['due_date'] <= ed]
            except Exception:
                pass

    # Search Query Filter (Multi-token)
    if search_query:
        tokens = search_query.lower().split()
        def matches_search(item):
            target = " ".join([
                item['student_name'], item['roll_number'], item['student_code'],
                item['standard'], item['parent_phone'], item['branch_name'],
                item['session_name'], item['label']
            ]).lower()
            return all(tok in target for tok in tokens)
        filtered_dues = [d for d in filtered_dues if matches_search(d)]

    # 6. Sorting Pipeline
    def sort_key(d):
        if sort_field == 'studentName':
            return d['student_name'].lower()
        elif sort_field == 'rollNo':
            return d['roll_number'].lower()
        elif sort_field == 'standard':
            return d['standard'].lower()
        elif sort_field == 'branch':
            return d['branch_name'].lower()
        elif sort_field == 'session':
            return d['session_name'].lower()
        elif sort_field == 'dueDate':
            return d['due_date'] or datetime.max.date()
        elif sort_field == 'parentPhone':
            return d['parent_phone']
        elif sort_field == 'amountDue':
            return d['amount_due']
        elif sort_field == 'amountPaid':
            return d['amount_paid']
        elif sort_field == 'balanceRemaining':
            return d['balance_remaining']
        elif sort_field == 'status':
            return d['status']
        return d['due_date'] or datetime.max.date()

    filtered_dues.sort(key=sort_key, reverse=(sort_direction == 'desc'))

    # 7. Check for Export Requests (Excel / PDF)
    if export_type == 'excel':
        meta = {
            'branch_name': Branch.objects.filter(id=branch_filter).first().name if branch_filter != 'ALL' else 'All Branches',
            'session_name': AcademicSession.objects.filter(id=session_filter).first().name if session_filter != 'ALL' else 'All Sessions',
        }
        excel_bytes = export_dues_to_excel(filtered_dues, meta)
        filename = f"Sutawane_Classes_Pending_Dues_{today.strftime('%Y%m%d')}.xlsx"
        response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    elif export_type == 'pdf':
        meta = {
            'institute_name': 'Sutawane Classes',
            'branch_name': Branch.objects.filter(id=branch_filter).first().name if branch_filter != 'ALL' else 'All Branches',
            'session_name': AcademicSession.objects.filter(id=session_filter).first().name if session_filter != 'ALL' else 'All Sessions',
        }
        pdf_bytes = export_dues_to_pdf(filtered_dues, meta)
        filename = f"Sutawane_Classes_Pending_Dues_{today.strftime('%Y%m%d')}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # 8. Pagination
    total_count = len(filtered_dues)
    if page_size >= 10000:
        total_pages = 1
        paginated_dues = filtered_dues
        page_num = 1
    else:
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page_num = max(1, min(page_num, total_pages))
        start_idx = (page_num - 1) * page_size
        end_idx = start_idx + page_size
        paginated_dues = filtered_dues[start_idx:end_idx]

    # Available distinct standards for filter
    available_standards = sorted(list(set(
        c.name for c in Course.objects.filter(is_active=True)
    ) | set(d['standard'] for d in raw_dues if d['standard'] != '—')))

    branches = Branch.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-name')

    has_active_filters = bool(
        search_query or
        status_filter != 'ALL' or
        branch_filter != 'ALL' or
        session_filter != 'ALL' or
        standard_filter != 'ALL' or
        date_preset != 'ALL' or
        start_date_str or
        end_date_str
    )

    context = {
        'dues': paginated_dues,
        'total_filtered_count': total_count,
        'kpis': kpis,
        'available_standards': available_standards,
        'branches': branches,
        'sessions': sessions,
        'has_active_filters': has_active_filters,
        'filters': {
            'q': search_query,
            'status': status_filter,
            'branch_id': branch_filter,
            'session_id': session_filter,
            'standard': standard_filter,
            'date_preset': date_preset,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'sort': sort_field,
            'direction': sort_direction,
            'page_size': page_size,
            'page': page_num,
        },
        'pagination': {
            'page': page_num,
            'total_pages': total_pages,
            'has_prev': page_num > 1,
            'has_next': page_num < total_pages,
            'prev_page': page_num - 1,
            'next_page': page_num + 1,
        }
    }

    # HTMX Partial swap support
    if request.headers.get('HX-Request') and request.GET.get('table_only') == '1':
        return render(request, 'includes/dues_table_partial.html', context)

    return render(request, 'dues.html', context)

def expenses_list_view(request):
    """
    Branch Expense & Overheads Management.
    Matches React ExpensesPage.tsx with 5 KPI summary cards, category pills strip,
    multi-token search, filter pipeline, file attachment upload & viewing,
    Excel/PDF exports, and full CRUD modals with zero page-reloads via HTMX.
    """
    # 1. Handle POST Actions (Create, Update, Delete Expense Voucher, Create Category)
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            description = request.POST.get('description', '').strip()
            amount_str = request.POST.get('amount', '0').strip()
            try:
                amount_val = parse_non_negative_money(amount_str, allow_blank=False)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('expenses_list')

            category_id = request.POST.get('category_id')
            new_category_name = request.POST.get('new_category_name', '').strip()

            # Resolve Category (auto-create new category if typed on-the-fly)
            if new_category_name or category_id == '__NEW__':
                cat_name_to_use = new_category_name or "General"
                cat, _ = ExpenseCategory.objects.get_or_create(
                    name__iexact=cat_name_to_use,
                    defaults={'name': cat_name_to_use, 'is_active': True, 'sort_order': 99}
                )
            elif category_id:
                cat = get_object_or_404(ExpenseCategory, id=category_id)
            else:
                cat = ExpenseCategory.objects.first()

            # Resolve Branch
            # Resolve Branch
            branch_id = request.POST.get('branch_id')
            if branch_id and branch_id != 'ALL':
                branch = get_object_or_404(Branch, id=branch_id)
            else:
                scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
                branch = scope_b or Branch.objects.filter(is_active=True).first()

            payment_mode = request.POST.get('payment_mode', 'UPI')
            vendor = request.POST.get('vendor', '').strip() or None
            reference_number = request.POST.get('reference_number', '').strip() or None

            # Expense Date
            exp_date_str = request.POST.get('expense_date', '').strip()
            if exp_date_str:
                try:
                    exp_dt = timezone.make_aware(datetime.strptime(exp_date_str, '%Y-%m-%d'))
                except Exception:
                    exp_dt = timezone.now()
            else:
                exp_dt = timezone.now()

            expense = Expense.objects.create(
                branch=branch,
                category=cat,
                amount=amount_val,
                expense_date=exp_dt,
                description=description,
                payment_mode=payment_mode,
                vendor=vendor,
                reference_number=reference_number,
            )

            # Handle File Attachment
            if request.FILES.get('attachment'):
                file_obj = request.FILES['attachment']
                import uuid
                ext = os.path.splitext(file_obj.name)[1] or ''
                orig_name = file_obj.name
                filename = f"bill-{uuid.uuid4()}-{int(datetime.now().timestamp())}{ext}"
                attachments_dir = os.path.join(settings.MEDIA_ROOT, 'attachments')
                os.makedirs(attachments_dir, exist_ok=True)
                filepath = os.path.join(attachments_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in file_obj.chunks():
                        dest.write(chunk)
                file_url = f"/media/attachments/{filename}"
                ExpenseAttachment.objects.create(
                    expense=expense,
                    file_name=orig_name,
                    file_path=file_url,
                    file_size=file_obj.size,
                    mime_type=file_obj.content_type or 'application/octet-stream',
                )

            messages.success(request, f"Expense voucher for '₹{amount_val:,.0f}' ({cat.name}) recorded successfully!")
            return redirect('expenses_list')

        elif action == 'update':
            expense_id = request.POST.get('expense_id')
            expense = get_object_or_404(Expense, id=expense_id)

            description = request.POST.get('description', '').strip()
            amount_str = request.POST.get('amount', '0').strip()
            try:
                expense.amount = parse_non_negative_money(amount_str, allow_blank=False)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect('expenses_list')

            category_id = request.POST.get('category_id')
            new_category_name = request.POST.get('new_category_name', '').strip()
            if new_category_name or category_id == '__NEW__':
                cat_name_to_use = new_category_name or "General"
                cat, _ = ExpenseCategory.objects.get_or_create(
                    name__iexact=cat_name_to_use,
                    defaults={'name': cat_name_to_use, 'is_active': True, 'sort_order': 99}
                )
                expense.category = cat
            elif category_id:
                expense.category = get_object_or_404(ExpenseCategory, id=category_id)

            branch_id = request.POST.get('branch_id')
            if branch_id and branch_id != 'ALL':
                expense.branch = get_object_or_404(Branch, id=branch_id)

            expense.description = description
            expense.payment_mode = request.POST.get('payment_mode', 'UPI')
            expense.vendor = request.POST.get('vendor', '').strip() or None
            expense.reference_number = request.POST.get('reference_number', '').strip() or None

            exp_date_str = request.POST.get('expense_date', '').strip()
            if exp_date_str:
                try:
                    expense.expense_date = timezone.make_aware(datetime.strptime(exp_date_str, '%Y-%m-%d'))
                except Exception:
                    pass

            expense.save()

            # Handle new attachment upload if provided
            if request.FILES.get('attachment'):
                file_obj = request.FILES['attachment']
                import uuid
                ext = os.path.splitext(file_obj.name)[1] or ''
                orig_name = file_obj.name
                filename = f"bill-{uuid.uuid4()}-{int(datetime.now().timestamp())}{ext}"
                attachments_dir = os.path.join(settings.MEDIA_ROOT, 'attachments')
                os.makedirs(attachments_dir, exist_ok=True)
                filepath = os.path.join(attachments_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in file_obj.chunks():
                        dest.write(chunk)
                file_url = f"/media/attachments/{filename}"
                ExpenseAttachment.objects.create(
                    expense=expense,
                    file_name=orig_name,
                    file_path=file_url,
                    file_size=file_obj.size,
                    mime_type=file_obj.content_type or 'application/octet-stream',
                )

            messages.success(request, f"Expense voucher updated successfully.")
            return redirect('expenses_list')

        elif action == 'delete':
            expense_id = request.POST.get('expense_id')
            expense = get_object_or_404(Expense, id=expense_id)
            desc = expense.description
            amt = expense.amount

            # Clean up physical files on disk
            for att in expense.attachments.all():
                if att.file_path and att.file_path.startswith('/media/'):
                    disk_rel = att.file_path[len('/media/'):]
                    disk_full = os.path.join(settings.MEDIA_ROOT, disk_rel)
                    try:
                        if os.path.exists(disk_full):
                            os.remove(disk_full)
                    except Exception:
                        pass

            expense.delete()
            messages.success(request, f"Expense voucher '{desc}' (₹{amt:,.0f}) permanently deleted.")
            return redirect('expenses_list')

        elif action == 'create_category':
            cat_name = request.POST.get('category_name', '').strip()
            is_ajax = (
                request.headers.get('x-requested-with') == 'XMLHttpRequest' or
                'application/json' in request.headers.get('Accept', '') or
                request.content_type == 'application/json'
            )
            if not cat_name:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Category name cannot be empty.'}, status=400)
                messages.error(request, 'Category name cannot be empty.')
                return redirect('expenses_list')

            existing = ExpenseCategory.objects.filter(name__iexact=cat_name).first()
            if existing:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': f"Category '{existing.name}' already exists."}, status=400)
                messages.warning(request, f"Category '{existing.name}' already exists.")
                return redirect('expenses_list')

            cat = ExpenseCategory.objects.create(
                name=cat_name,
                is_active=True,
                sort_order=ExpenseCategory.objects.count() + 1
            )
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Category '{cat.name}' created successfully.",
                    'category': {
                        'id': str(cat.id),
                        'name': cat.name,
                        'expense_count': 0,
                        'expense_total': 0.0,
                        'is_active': cat.is_active,
                    }
                })
            messages.success(request, f"Category '{cat.name}' created successfully.")
            return redirect('expenses_list')

        elif action == 'update_category':
            category_id = request.POST.get('category_id')
            cat_name = request.POST.get('category_name', '').strip()
            is_ajax = (
                request.headers.get('x-requested-with') == 'XMLHttpRequest' or
                'application/json' in request.headers.get('Accept', '') or
                request.content_type == 'application/json'
            )

            if not category_id:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Category ID is required.'}, status=400)
                messages.error(request, 'Category ID is required.')
                return redirect('expenses_list')

            if not cat_name:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Category name cannot be empty.'}, status=400)
                messages.error(request, 'Category name cannot be empty.')
                return redirect('expenses_list')

            cat = get_object_or_404(ExpenseCategory, id=category_id)

            existing = ExpenseCategory.objects.filter(name__iexact=cat_name).exclude(id=category_id).first()
            if existing:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': f"Another category named '{existing.name}' already exists."}, status=400)
                messages.error(request, f"Another category named '{existing.name}' already exists.")
                return redirect('expenses_list')

            old_name = cat.name
            cat.name = cat_name
            cat.save()

            exp_count = cat.expenses.count()
            exp_total = sum((e.amount for e in cat.expenses.all()), Decimal('0.00'))

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Category updated to '{cat.name}' successfully. (Updated across {exp_count} voucher(s))",
                    'category': {
                        'id': str(cat.id),
                        'name': cat.name,
                        'expense_count': exp_count,
                        'expense_total': float(exp_total),
                        'is_active': cat.is_active,
                    }
                })
            messages.success(request, f"Category '{old_name}' updated to '{cat.name}' successfully.")
            return redirect('expenses_list')

        elif action == 'delete_category':
            category_id = request.POST.get('category_id')
            is_ajax = (
                request.headers.get('x-requested-with') == 'XMLHttpRequest' or
                'application/json' in request.headers.get('Accept', '') or
                request.content_type == 'application/json'
            )

            if not category_id:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Category ID is required.'}, status=400)
                messages.error(request, 'Category ID is required.')
                return redirect('expenses_list')

            cat = get_object_or_404(ExpenseCategory, id=category_id)
            exp_count = cat.expenses.count()

            # Rule requested by user: If anyone records the particular category, they will NOT be able to delete!
            if exp_count > 0:
                exp_total = sum((e.amount for e in cat.expenses.all()), Decimal('0.00'))
                err_msg = (
                    f"Cannot delete category '{cat.name}': It is linked to {exp_count} recorded expense voucher(s) "
                    f"totaling ₹{exp_total:,.0f}. To preserve audit ledgers, categories with existing expenses cannot be deleted. "
                    f"You can update or rename it instead."
                )
                if is_ajax:
                    return JsonResponse({'success': False, 'error': err_msg, 'cannot_delete': True, 'expense_count': exp_count}, status=400)
                messages.error(request, err_msg)
                return redirect('expenses_list')

            cat_name = cat.name
            cat.delete()

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Category '{cat_name}' permanently deleted.",
                    'deleted_id': category_id,
                })
            messages.success(request, f"Category '{cat_name}' permanently deleted.")
            return redirect('expenses_list')

    # 2. Extract Query Parameters
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category_id', 'ALL')
    payment_mode_filter = request.GET.get('payment_mode', 'ALL')
    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    branch_filter = request.GET.get('branch_id')
    if branch_filter is None:
        branch_filter = scope_b_id

    date_preset = request.GET.get('date_preset', 'ALL').upper()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    sort_field = request.GET.get('sort', 'expenseDate')
    sort_direction = request.GET.get('direction', 'desc').lower()
    page_size = int(request.GET.get('page_size', 25))
    page_num = int(request.GET.get('page', 1))
    export_type = request.GET.get('export', '').lower()

    # 3. Base Queryset
    qs = Expense.objects.select_related('branch', 'category').prefetch_related('attachments').all()

    # In-page Branch filter
    if branch_filter and branch_filter != 'ALL':
        qs = qs.filter(branch_id=branch_filter)

    # Session date range filter for expenses
    if scope_s_id and scope_s_id != 'ALL' and scope_s:
        if scope_s.start_date and scope_s.end_date:
            qs = qs.filter(expense_date__range=[scope_s.start_date, scope_s.end_date])

    # Category filter
    if category_filter and category_filter != 'ALL':
        qs = qs.filter(Q(category_id=category_filter) | Q(category__name__iexact=category_filter))

    # Payment mode filter
    if payment_mode_filter and payment_mode_filter != 'ALL':
        qs = qs.filter(payment_mode=payment_mode_filter)

    # Date Range Preset Filter
    today = timezone.localtime().date()
    if date_preset == 'TODAY':
        qs = qs.filter(expense_date__date=today)
    elif date_preset == 'YESTERDAY':
        yesterday = today - timedelta(days=1)
        qs = qs.filter(expense_date__date=yesterday)
    elif date_preset == 'THIS_WEEK':
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        qs = qs.filter(expense_date__date__range=[week_start, week_end])
    elif date_preset == 'THIS_MONTH':
        month_start = today.replace(day=1)
        next_m = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_m - timedelta(days=1)
        qs = qs.filter(expense_date__date__range=[month_start, month_end])
    elif date_preset == 'LAST_MONTH':
        first_this_m = today.replace(day=1)
        last_m_end = first_this_m - timedelta(days=1)
        last_m_start = last_m_end.replace(day=1)
        qs = qs.filter(expense_date__date__range=[last_m_start, last_m_end])
    elif date_preset == 'THIS_YEAR':
        year_start = today.replace(month=1, day=1)
        year_end = today.replace(month=12, day=31)
        qs = qs.filter(expense_date__date__range=[year_start, year_end])
    elif date_preset == 'CUSTOM':
        if start_date_str:
            qs = qs.filter(expense_date__date__gte=start_date_str)
        if end_date_str:
            qs = qs.filter(expense_date__date__lte=end_date_str)

    # Multi-token Search across description, vendor, ref no, category name, branch name, payment mode
    if search_query:
        tokens = search_query.split()
        for token in tokens:
            qs = qs.filter(
                Q(description__icontains=token) |
                Q(vendor__icontains=token) |
                Q(reference_number__icontains=token) |
                Q(category__name__icontains=token) |
                Q(branch__name__icontains=token) |
                Q(payment_mode__icontains=token)
            )

    # 4. Serialize to list of dictionaries for sorting and metrics
    raw_expenses = []
    for exp in qs:
        atts = list(exp.attachments.all())
        first_att = atts[0] if atts else None
        exp_dt = timezone.localtime(exp.expense_date) if exp.expense_date else None

        raw_expenses.append({
            'id': exp.id,
            'expense_date': exp_dt,
            'expense_date_iso': exp_dt.strftime('%Y-%m-%d') if exp_dt else '',
            'expense_date_formatted': exp_dt.strftime('%d %b %Y') if exp_dt else '—',
            'category_id': exp.category_id,
            'category_name': exp.category.name if exp.category else 'General',
            'description': exp.description,
            'branch_id': exp.branch_id,
            'branch_name': exp.branch.name if exp.branch else '—',
            'vendor': exp.vendor or '',
            'payment_mode': exp.payment_mode,
            'reference_number': exp.reference_number or '',
            'amount': exp.amount,
            'has_attachment': bool(first_att),
            'attachment_file_name': first_att.file_name if first_att else '',
            'attachment_file_path': first_att.file_path if first_att else '',
            'attachment_mime_type': first_att.mime_type if first_att else '',
        })

    # 5. Sorting
    reverse_sort = (sort_direction == 'desc')
    if sort_field == 'expenseDate':
        raw_expenses.sort(key=lambda x: x['expense_date'] or timezone.now(), reverse=reverse_sort)
    elif sort_field == 'category':
        raw_expenses.sort(key=lambda x: x['category_name'].lower(), reverse=reverse_sort)
    elif sort_field == 'description':
        raw_expenses.sort(key=lambda x: x['description'].lower(), reverse=reverse_sort)
    elif sort_field == 'branch':
        raw_expenses.sort(key=lambda x: x['branch_name'].lower(), reverse=reverse_sort)
    elif sort_field == 'vendor':
        raw_expenses.sort(key=lambda x: x['vendor'].lower(), reverse=reverse_sort)
    elif sort_field == 'paymentMode':
        raw_expenses.sort(key=lambda x: x['payment_mode'], reverse=reverse_sort)
    elif sort_field == 'referenceNumber':
        raw_expenses.sort(key=lambda x: x['reference_number'].lower(), reverse=reverse_sort)
    elif sort_field == 'amount':
        raw_expenses.sort(key=lambda x: x['amount'], reverse=reverse_sort)
    else:
        raw_expenses.sort(key=lambda x: x['expense_date'] or timezone.now(), reverse=True)

    # 6. Global KPI Summary Calculations
    total_count = len(raw_expenses)
    total_amount = sum(e['amount'] for e in raw_expenses)
    upi_total = sum(e['amount'] for e in raw_expenses if e['payment_mode'] == 'UPI')
    cash_total = sum(e['amount'] for e in raw_expenses if e['payment_mode'] == 'CASH')
    bank_total = sum(e['amount'] for e in raw_expenses if e['payment_mode'] in ['BANK_TRANSFER', 'CHEQUE'])

    # Category Breakdown
    cat_map = {}
    for e in raw_expenses:
        c_name = e['category_name']
        c_id = e['category_id']
        if c_name not in cat_map:
            cat_map[c_name] = {'id': c_id, 'name': c_name, 'total': MONEY_ZERO, 'count': 0}
        cat_map[c_name]['total'] += e['amount']
        cat_map[c_name]['count'] += 1

    category_breakdown = sorted(cat_map.values(), key=lambda c: c['total'], reverse=True)
    top_category = category_breakdown[0] if category_breakdown else None

    kpis = {
        'total_count': total_count,
        'total_amount': total_amount,
        'top_category': top_category,
        'upi_total': upi_total,
        'cash_bank_total': cash_total + bank_total,
    }

    # 7. Exports (Excel & PDF)
    branch_name_label = 'All Branches'
    if branch_filter and branch_filter != 'ALL':
        b_obj = Branch.objects.filter(id=branch_filter).first()
        if b_obj:
            branch_name_label = b_obj.name

    if export_type == 'excel':
        xlsx_bytes = export_expenses_to_excel(raw_expenses, {'branch_name': branch_name_label})
        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        safe_branch = branch_name_label.replace(' ', '_')
        date_str = today.strftime('%Y-%m-%d')
        response['Content-Disposition'] = f'attachment; filename="Expense_Vouchers_{safe_branch}_{date_str}.xlsx"'
        return response

    elif export_type == 'pdf':
        pdf_bytes = export_expenses_to_pdf(raw_expenses, {
            'institute_name': 'Sutawane Classes',
            'branch_name': branch_name_label,
        })
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        safe_branch = branch_name_label.replace(' ', '_')
        date_str = today.strftime('%Y-%m-%d')
        response['Content-Disposition'] = f'attachment; filename="Expense_Vouchers_{safe_branch}_{date_str}.pdf"'
        return response

    # 8. Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(raw_expenses, page_size)
    page_obj = paginator.get_page(page_num)

    has_active_filters = bool(
        search_query or
        (category_filter and category_filter != 'ALL') or
        (payment_mode_filter and payment_mode_filter != 'ALL') or
        (branch_filter and branch_filter != 'ALL') or
        (date_preset and date_preset != 'ALL') or
        start_date_str or
        end_date_str
    )

    categories_list = ExpenseCategory.objects.annotate(
        expense_count=Count('expenses'),
        expense_total=Sum('expenses__amount')
    ).order_by('sort_order', 'name')
    branches_list = Branch.objects.filter(is_active=True).order_by('name')

    context = {
        'page_obj': page_obj,
        'total_filtered': total_count,
        'kpis': kpis,
        'category_breakdown': category_breakdown,
        'categories': categories_list,
        'branches': branches_list,
        'has_active_filters': has_active_filters,
        'filters': {
            'q': search_query,
            'category_id': category_filter,
            'payment_mode': payment_mode_filter,
            'branch_id': branch_filter,
            'date_preset': date_preset,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'sort': sort_field,
            'direction': sort_direction,
            'page_size': page_size,
        }
    }

    # HTMX Partial swap support
    if request.headers.get('HX-Request'):
        return render(request, 'includes/expenses_table_partial.html', context)

    return render(request, 'expenses.html', context)

def financial_reports_view(request):
    """
    Financial & Administrative Reports Suite matching React ReportsPage.tsx.
    Supports 4 primary tabs:
    1. SESSION_AUDIT: Comprehensive academic session audit with branch & course breakdown
    2. PAYMENT_MODES: Inflow channels reconciliation & share distribution
    3. EXPENSE_CATEGORIES: Center expenditure taxonomy & budget breakdown
    4. STATEMENT_DIRECTORY: Quick links to all 16 financial statements and reports
    """
    branches = Branch.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-start_date')

    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    selected_branch_id = request.GET.get('branch_id')
    if not selected_branch_id:
        selected_branch_id = scope_b_id

    selected_session_id = request.GET.get('session_id')
    if not selected_session_id:
        selected_session_id = scope_s_id

    active_tab = request.GET.get('tab', 'SESSION_AUDIT').upper()
    if active_tab not in ('SESSION_AUDIT', 'PAYMENT_MODES', 'EXPENSE_CATEGORIES', 'STATEMENT_DIRECTORY'):
        active_tab = 'SESSION_AUDIT'

    # Target session resolution
    target_session = None
    if selected_session_id != 'ALL':
        target_session = AcademicSession.objects.filter(id=selected_session_id).first()
    if not target_session:
        target_session = AcademicSession.objects.filter(is_current=True).first()
    if not target_session:
        target_session = sessions.first()

    # 1. SESSION AUDIT DATA
    active_admissions = []
    archived_admissions = []
    total_fees_agreed = MONEY_ZERO
    total_collections = MONEY_ZERO
    total_pending_dues = MONEY_ZERO
    collection_efficiency = 0.0
    total_expenses = MONEY_ZERO
    net_surplus = MONEY_ZERO
    is_surplus = True
    branch_breakdown = []
    standard_breakdown = []
    monthly_trend = []

    if target_session:
        adm_qs = StudentAdmission.objects.filter(session=target_session).select_related('student', 'branch', 'fee_plan')
        if selected_branch_id != 'ALL':
            adm_qs = adm_qs.filter(branch_id=selected_branch_id)
        
        admissions = list(adm_qs)
        active_admissions = [a for a in admissions if a.is_active]
        archived_admissions = [a for a in admissions if not a.is_active]

        total_fees_agreed = sum(
            (a.fee_plan.net_payable if hasattr(a, 'fee_plan') and a.fee_plan and a.fee_plan.net_payable is not None 
             else (a.fee_plan.total_fees if hasattr(a, 'fee_plan') and a.fee_plan else MONEY_ZERO)
             for a in active_admissions),
            MONEY_ZERO
        )

        pay_qs = Payment.objects.filter(
            session=target_session,
            is_reversed=False,
            admission__isnull=False,
            admission__session=target_session,
        ).select_related('branch', 'admission', 'student')
        if selected_branch_id != 'ALL':
            pay_qs = pay_qs.filter(branch_id=selected_branch_id)
        payments = list(pay_qs)
        total_collections = sum((p.total_amount for p in payments), MONEY_ZERO)
        total_pending_dues = max(MONEY_ZERO, total_fees_agreed - total_collections)
        collection_efficiency = round((float(total_collections) / float(total_fees_agreed) * 100), 1) if total_fees_agreed and float(total_fees_agreed) > 0 else 0.0

        exp_qs = Expense.objects.filter(
            expense_date__gte=target_session.start_date,
            expense_date__lte=target_session.end_date
        ).select_related('category', 'branch')
        if selected_branch_id != 'ALL':
            exp_qs = exp_qs.filter(branch_id=selected_branch_id)
        session_expenses = list(exp_qs)
        total_expenses = sum((e.amount for e in session_expenses), MONEY_ZERO)

        net_surplus = total_collections - total_expenses
        is_surplus = net_surplus >= 0

        # Campus & Branch Performance Breakdown
        for b in branches:
            b_adms = [a for a in active_admissions if a.branch_id == b.id]
            b_fees = sum(
                (a.fee_plan.net_payable if hasattr(a, 'fee_plan') and a.fee_plan and a.fee_plan.net_payable is not None
                 else (a.fee_plan.total_fees if hasattr(a, 'fee_plan') and a.fee_plan else MONEY_ZERO)
                 for a in b_adms),
                MONEY_ZERO
            )
            b_pays = [p for p in payments if p.branch_id == b.id]
            b_col = sum((p.total_amount for p in b_pays), MONEY_ZERO)
            b_exp = sum((e.amount for e in session_expenses if e.branch_id == b.id), MONEY_ZERO)
            b_dues = max(MONEY_ZERO, b_fees - b_col)
            b_net = b_col - b_exp
            b_rate = round((float(b_col) / float(b_fees) * 100), 1) if b_fees and float(b_fees) > 0 else 0.0

            branch_breakdown.append({
                'branchId': b.id,
                'branchName': b.name,
                'branchCode': b.code,
                'studentsCount': len(b_adms),
                'totalFees': b_fees,
                'collections': b_col,
                'pendingDues': b_dues,
                'expenses': b_exp,
                'netSurplus': b_net,
                'collectionRate': b_rate,
            })

        # Standard / Course-wise Performance
        std_map = {}
        for a in active_admissions:
            std = a.standard or 'General'
            if std not in std_map:
                std_map[std] = {'studentCount': 0, 'totalFees': MONEY_ZERO, 'collected': MONEY_ZERO}
            std_map[std]['studentCount'] += 1
            f_amt = (a.fee_plan.net_payable if hasattr(a, 'fee_plan') and a.fee_plan and a.fee_plan.net_payable is not None
                     else (a.fee_plan.total_fees if hasattr(a, 'fee_plan') and a.fee_plan else MONEY_ZERO))
            std_map[std]['totalFees'] += f_amt

        for p in payments:
            if p.admission and p.admission.standard:
                std = p.admission.standard
                if std in std_map:
                    std_map[std]['collected'] += p.total_amount

        for std, s_info in std_map.items():
            s_fees = s_info['totalFees']
            s_col = s_info['collected']
            s_dues = max(MONEY_ZERO, s_fees - s_col)
            s_rate = round((float(s_col) / float(s_fees) * 100), 1) if s_fees and float(s_fees) > 0 else 0.0
            standard_breakdown.append({
                'standard': std,
                'studentCount': s_info['studentCount'],
                'totalFees': s_fees,
                'collected': s_col,
                'pendingDues': s_dues,
                'collectionRate': s_rate,
            })
        standard_breakdown.sort(key=lambda s: s['studentCount'], reverse=True)

        # Monthly Inflow vs Outflow Trend
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        m_trend_map = {}
        if target_session.start_date and target_session.end_date:
            cur_dt = target_session.start_date
            end_dt = target_session.end_date
            iters = 0
            while cur_dt <= end_dt and iters < 36:
                iters += 1
                y = cur_dt.year
                m = cur_dt.month
                k = f"{y}-{m:02d}"
                m_trend_map[k] = {
                    'monthKey': k,
                    'monthLabel': f"{month_names[m-1]} {y}",
                    'collections': MONEY_ZERO,
                    'expenses': MONEY_ZERO,
                }
                if m == 12:
                    cur_dt = cur_dt.replace(year=y+1, month=1, day=1)
                else:
                    cur_dt = cur_dt.replace(month=m+1, day=1)

        for p in payments:
            k = f"{p.payment_date.year}-{p.payment_date.month:02d}"
            if k in m_trend_map:
                m_trend_map[k]['collections'] += p.total_amount

        for e in session_expenses:
            k = f"{e.expense_date.year}-{e.expense_date.month:02d}"
            if k in m_trend_map:
                m_trend_map[k]['expenses'] += e.amount

        for item in m_trend_map.values():
            item['net'] = item['collections'] - item['expenses']
            item['net_abs'] = abs(item['net'])

        monthly_trend = list(m_trend_map.values())

    session_audit_data = {
        'session': {
            'id': target_session.id if target_session else None,
            'name': target_session.name if target_session else 'Consolidated',
            'displayName': target_session.display_name if target_session else 'Academic Session',
            'isCurrent': target_session.is_current if target_session else False,
            'startDate': target_session.start_date.isoformat() if target_session else '',
            'endDate': target_session.end_date.isoformat() if target_session else '',
        },
        'summary': {
            'activeAdmissions': len(active_admissions),
            'archivedAdmissions': len(archived_admissions),
            'totalFeesAgreed': total_fees_agreed,
            'totalCollections': total_collections,
            'totalPendingDues': total_pending_dues,
            'collectionEfficiency': collection_efficiency,
            'totalExpenses': total_expenses,
            'netSurplus': net_surplus,
            'isSurplus': is_surplus,
        },
        'branchBreakdown': branch_breakdown,
        'standardBreakdown': standard_breakdown,
        'monthlyTrend': monthly_trend,
    }

    # 2. PAYMENT MODES DATA
    # Payment-mode collection analytics represent current admission fees. Cash
    # movement for previous-session dues remains visible in the receipt history.
    p_modes_qs = Payment.objects.filter(is_reversed=False, admission__isnull=False)
    if selected_branch_id != 'ALL':
        p_modes_qs = p_modes_qs.filter(branch_id=selected_branch_id)
    if selected_session_id != 'ALL':
        p_modes_qs = p_modes_qs.filter(session_id=selected_session_id)

    mode_map = {
        'CASH': {'amount': MONEY_ZERO, 'count': 0},
        'UPI': {'amount': MONEY_ZERO, 'count': 0},
        'BANK_TRANSFER': {'amount': MONEY_ZERO, 'count': 0},
        'CHEQUE': {'amount': MONEY_ZERO, 'count': 0},
        'OTHER': {'amount': MONEY_ZERO, 'count': 0},
    }
    tot_col_modes = MONEY_ZERO
    tot_txns_modes = 0
    for p in p_modes_qs:
        m_key = (p.payment_mode or 'OTHER').upper()
        if m_key not in mode_map:
            mode_map[m_key] = {'amount': MONEY_ZERO, 'count': 0}
        mode_map[m_key]['amount'] += p.total_amount
        mode_map[m_key]['count'] += 1
        tot_col_modes += p.total_amount
        tot_txns_modes += 1

    modes_list = []
    for m_key, m_info in mode_map.items():
        pct = round((float(m_info['amount']) / float(tot_col_modes) * 100), 1) if tot_col_modes and float(tot_col_modes) > 0 else 0.0
        avg = round(float(m_info['amount']) / m_info['count'], 2) if m_info['count'] > 0 else 0.0
        modes_list.append({
            'mode': m_key,
            'label': m_key.replace('_', ' '),
            'amount': m_info['amount'],
            'count': m_info['count'],
            'average': avg,
            'percentage': pct,
        })
    modes_list.sort(key=lambda x: x['amount'], reverse=True)
    payment_modes_data = {
        'totalCollected': tot_col_modes,
        'totalTransactions': tot_txns_modes,
        'modes': modes_list,
    }

    # 3. EXPENSE CATEGORIES DATA
    e_cats_qs = Expense.objects.select_related('category', 'branch')
    if selected_branch_id != 'ALL':
        e_cats_qs = e_cats_qs.filter(branch_id=selected_branch_id)
    if selected_session_id != 'ALL' and target_session:
        e_cats_qs = e_cats_qs.filter(expense_date__gte=target_session.start_date, expense_date__lte=target_session.end_date)

    cat_map = {}
    tot_exp_cats = MONEY_ZERO
    tot_vouchers_cats = 0
    for e in e_cats_qs:
        c_id = e.category_id or 'uncategorized'
        c_name = e.category.name if e.category else 'General Operations'
        if c_id not in cat_map:
            cat_map[c_id] = {'categoryId': c_id, 'categoryName': c_name, 'amount': MONEY_ZERO, 'count': 0}
        cat_map[c_id]['amount'] += e.amount
        cat_map[c_id]['count'] += 1
        tot_exp_cats += e.amount
        tot_vouchers_cats += 1

    categories_list = []
    for c_id, c_info in cat_map.items():
        pct = round((float(c_info['amount']) / float(tot_exp_cats) * 100), 1) if tot_exp_cats and float(tot_exp_cats) > 0 else 0.0
        avg = round(float(c_info['amount']) / c_info['count'], 2) if c_info['count'] > 0 else 0.0
        categories_list.append({
            'categoryId': c_id,
            'categoryName': c_info['categoryName'],
            'amount': c_info['amount'],
            'count': c_info['count'],
            'average': avg,
            'percentage': pct,
        })
    categories_list.sort(key=lambda x: x['amount'], reverse=True)
    expense_categories_data = {
        'totalExpenses': tot_exp_cats,
        'totalVouchers': tot_vouchers_cats,
        'categories': categories_list,
    }

    # EXPORT HANDLING
    export_type = request.GET.get('export')
    branch_name_label = 'All Branches'
    if selected_branch_id != 'ALL':
        b_match = Branch.objects.filter(id=selected_branch_id).first()
        if b_match:
            branch_name_label = b_match.name

    session_name_label = target_session.name if target_session else 'All Sessions'

    if export_type == 'excel':
        if active_tab == 'SESSION_AUDIT':
            content = export_session_audit_excel(session_audit_data, {
                'branch_name': branch_name_label,
                'session_name': session_name_label,
            })
            resp = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp['Content-Disposition'] = f'attachment; filename="Session_Audit_{session_name_label}.xlsx"'
            return resp
        elif active_tab == 'PAYMENT_MODES':
            content = export_payment_modes_excel(payment_modes_data, {
                'branch_name': branch_name_label,
                'session_name': session_name_label,
            })
            resp = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp['Content-Disposition'] = 'attachment; filename="Payment_Modes_Summary.xlsx"'
            return resp
        elif active_tab == 'EXPENSE_CATEGORIES':
            content = export_expense_categories_excel(expense_categories_data, {
                'branch_name': branch_name_label,
            })
            resp = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            resp['Content-Disposition'] = 'attachment; filename="Expense_Categories_Summary.xlsx"'
            return resp

    if export_type == 'pdf':
        if active_tab == 'SESSION_AUDIT':
            content = export_session_audit_pdf(session_audit_data, {
                'branch_name': branch_name_label,
                'session_name': session_name_label,
            })
            resp = HttpResponse(content, content_type='application/pdf')
            resp['Content-Disposition'] = f'attachment; filename="Session_Audit_{session_name_label.replace(" ", "_")}.pdf"'
            return resp
        elif active_tab == 'PAYMENT_MODES':
            content = export_payment_modes_pdf(payment_modes_data, {
                'branch_name': branch_name_label,
                'session_name': session_name_label,
            })
            resp = HttpResponse(content, content_type='application/pdf')
            resp['Content-Disposition'] = 'attachment; filename="Payment_Modes_Summary.pdf"'
            return resp
        elif active_tab == 'EXPENSE_CATEGORIES':
            content = export_expense_categories_pdf(expense_categories_data, {
                'branch_name': branch_name_label,
            })
            resp = HttpResponse(content, content_type='application/pdf')
            resp['Content-Disposition'] = 'attachment; filename="Expense_Categories_Summary.pdf"'
            return resp

    # JSON API Handshake
    if request.GET.get('format') == 'json':
        if active_tab == 'PAYMENT_MODES':
            return JsonResponse({'success': True, **payment_modes_data})
        elif active_tab == 'EXPENSE_CATEGORIES':
            return JsonResponse({'success': True, **expense_categories_data})
        else:
            return JsonResponse({'success': True, **session_audit_data})

    context = {
        'active_tab': active_tab,
        'branches': branches,
        'sessions': sessions,
        'selected_branch_id': selected_branch_id,
        'selected_session_id': selected_session_id,
        'target_session': target_session,
        'session_audit': session_audit_data,
        'payment_modes': payment_modes_data,
        'expense_categories': expense_categories_data,
        'printed_date': datetime.now().strftime('%d %B %Y'),
    }

    return render(request, 'reports.html', context)


def daily_reports_view(request):
    """
    Day Book & Unified Daily Financial Statement matching React DailyReportsPage.tsx.
    Supports DAILY, MONTHLY, and CUSTOM modes, dual collections & expenses ledgers,
    mode-based cash reconciliation, HTMX search, official print modal, and Excel/PDF exports.
    """
    branches = Branch.objects.filter(is_active=True).order_by('name')
    sessions = AcademicSession.objects.filter(isActive=True).order_by('-start_date')

    scope_b_id, scope_s_id, scope_b, scope_s = get_active_scope(request)
    selected_branch_id = request.GET.get('branch_id') or scope_b_id
    selected_session_id = request.GET.get('session_id') or scope_s_id

    modes_list = [m.upper() for m in request.GET.getlist('mode') if m]
    active_mode = 'DAILY'
    for m in modes_list:
        if m in ('MONTHLY', 'CUSTOM'):
            active_mode = m
            break
    else:
        if modes_list:
            active_mode = modes_list[0]
    if active_mode not in ('DAILY', 'MONTHLY', 'CUSTOM'):
        active_mode = 'DAILY'

    today_str = datetime.now().strftime('%Y-%m-%d')
    daily_date = request.GET.get('date') or today_str

    try:
        selected_month = int(request.GET.get('month', datetime.now().month - 1))
    except (ValueError, TypeError):
        selected_month = datetime.now().month - 1

    try:
        selected_year = int(request.GET.get('year', datetime.now().year))
    except (ValueError, TypeError):
        selected_year = datetime.now().year

    custom_start_date = request.GET.get('start_date') or datetime(datetime.now().year, datetime.now().month, 1).strftime('%Y-%m-%d')
    custom_end_date = request.GET.get('end_date') or today_str

    # Date range calculations
    if active_mode == 'DAILY':
        try:
            d_obj = datetime.strptime(daily_date, '%Y-%m-%d').date()
        except ValueError:
            d_obj = datetime.now().date()
            daily_date = today_str
        start_dt = timezone.make_aware(datetime.combine(d_obj, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(d_obj, datetime.max.time()))
        period_label = f"Daily Statement: {d_obj.strftime('%d %B %Y')}"

    elif active_mode == 'MONTHLY':
        m_1based = (selected_month % 12) + 1
        num_days = calendar.monthrange(selected_year, m_1based)[1]
        start_dt = timezone.make_aware(datetime(selected_year, m_1based, 1, 0, 0, 0))
        end_dt = timezone.make_aware(datetime(selected_year, m_1based, num_days, 23, 59, 59))
        period_label = f"Monthly Statement: {calendar.month_name[m_1based]} {selected_year}"

    else:  # CUSTOM
        try:
            s_obj = datetime.strptime(custom_start_date, '%Y-%m-%d').date()
        except ValueError:
            s_obj = datetime(datetime.now().year, datetime.now().month, 1).date()
            custom_start_date = s_obj.strftime('%Y-%m-%d')
        try:
            e_obj = datetime.strptime(custom_end_date, '%Y-%m-%d').date()
        except ValueError:
            e_obj = datetime.now().date()
            custom_end_date = today_str
        start_dt = timezone.make_aware(datetime.combine(s_obj, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(e_obj, datetime.max.time()))
        period_label = f"Custom Range: {s_obj.strftime('%d %b %Y')} to {e_obj.strftime('%d %b %Y')}"

    # Query Payments & Expenses
    pay_qs = Payment.objects.filter(
        is_reversed=False,
        payment_date__gte=start_dt,
        payment_date__lte=end_dt
    ).select_related('student', 'branch', 'session', 'admission').order_by('-payment_date')

    if selected_branch_id != 'ALL':
        pay_qs = pay_qs.filter(branch_id=selected_branch_id)
    if selected_session_id != 'ALL':
        pay_qs = pay_qs.filter(session_id=selected_session_id)

    exp_qs = Expense.objects.filter(
        expense_date__gte=start_dt,
        expense_date__lte=end_dt
    ).select_related('category', 'branch').order_by('-expense_date')

    if selected_branch_id != 'ALL':
        exp_qs = exp_qs.filter(branch_id=selected_branch_id)

    payments = list(pay_qs)
    expenses = list(exp_qs)

    total_collections = sum((p.total_amount for p in payments), MONEY_ZERO)
    collections_count = len(payments)
    total_expenses = sum((e.amount for e in expenses), MONEY_ZERO)
    expenses_count = len(expenses)
    net_movement = total_collections - total_expenses
    is_profit = net_movement >= 0

    # Mode and Category breakdowns
    collections_by_mode = {}
    for p in payments:
        m = p.payment_mode or 'OTHER'
        if m not in collections_by_mode:
            collections_by_mode[m] = {'amount': MONEY_ZERO, 'count': 0}
        collections_by_mode[m]['amount'] += p.total_amount
        collections_by_mode[m]['count'] += 1

    expenses_by_mode = {}
    for e in expenses:
        m = e.payment_mode or 'OTHER'
        if m not in expenses_by_mode:
            expenses_by_mode[m] = {'amount': MONEY_ZERO, 'count': 0}
        expenses_by_mode[m]['amount'] += e.amount
        expenses_by_mode[m]['count'] += 1

    expenses_by_category = {}
    for e in expenses:
        cat = e.category.name if e.category else 'General Expense'
        if cat not in expenses_by_category:
            expenses_by_category[cat] = {'amount': MONEY_ZERO, 'count': 0}
        expenses_by_category[cat]['amount'] += e.amount
        expenses_by_category[cat]['count'] += 1

    # Search Filtering
    q_col = request.GET.get('q_col', '').strip().lower()
    q_exp = request.GET.get('q_exp', '').strip().lower()

    filtered_collections = payments
    if q_col:
        tokens = q_col.split()
        filtered_collections = [
            p for p in filtered_collections
            if all(
                t in f"{p.student.full_name if p.student else ''} {p.receipt_number} {p.admission.roll_number if p.admission else ''} {p.admission.standard if p.admission else ''} {p.payment_mode} {p.reference_number or ''}".lower()
                for t in tokens
            )
        ]

    filtered_expenses = expenses
    if q_exp:
        tokens = q_exp.split()
        filtered_expenses = [
            e for e in filtered_expenses
            if all(
                t in f"{e.description or ''} {e.vendor or ''} {e.category.name if e.category else ''} {e.reference_number or ''} {e.payment_mode}".lower()
                for t in tokens
            )
        ]

    # Statement Payload for Exports & APIs
    statement_data = {
        'period': {
            'startDate': start_dt.isoformat(),
            'endDate': end_dt.isoformat(),
        },
        'summary': {
            'totalCollections': total_collections,
            'collectionsCount': collections_count,
            'totalExpenses': total_expenses,
            'expensesCount': expenses_count,
            'netMovement': net_movement,
            'isProfit': is_profit,
            'collectionsByMode': collections_by_mode,
            'expensesByMode': expenses_by_mode,
            'expensesByCategory': expenses_by_category,
        },
        'collections': [
            {
                'id': p.id,
                'receiptNumber': p.receipt_number,
                'paymentDate': p.payment_date.isoformat(),
                'totalAmount': p.total_amount,
                'paymentMode': p.payment_mode,
                'referenceNumber': p.reference_number or '—',
                'studentName': p.student.full_name if p.student else '—',
                'studentCode': p.student.student_code if p.student else '—',
                'parentPhone': p.student.parent_phone if p.student else '—',
                'rollNumber': p.admission.roll_number if p.admission else '—',
                'standard': p.admission.standard if p.admission else '—',
                'branchName': p.branch.name if p.branch else '—',
                'sessionName': p.session.display_name if p.session else '—',
            }
            for p in filtered_collections
        ],
        'expenses': [
            {
                'id': e.id,
                'referenceNumber': e.reference_number or '—',
                'expenseDate': e.expense_date.isoformat(),
                'amount': e.amount,
                'paymentMode': e.payment_mode,
                'description': e.description or '—',
                'vendor': e.vendor or '—',
                'paidTo': e.vendor or '—',
                'categoryName': e.category.name if e.category else 'General Expense',
                'branchName': e.branch.name if e.branch else '—',
            }
            for e in filtered_expenses
        ],
    }

    # EXPORT HANDLING
    export_type = request.GET.get('export')
    branch_name_label = 'All Branches'
    branch_logo = None
    if selected_branch_id != 'ALL':
        b_match = Branch.objects.filter(id=selected_branch_id).first()
        if b_match:
            branch_name_label = b_match.name
            branch_logo = b_match.logo_url

    session_name_label = 'All Sessions'
    if selected_session_id != 'ALL':
        s_match = AcademicSession.objects.filter(id=selected_session_id).first()
        if s_match:
            session_name_label = s_match.name

    if export_type == 'excel':
        content = export_statement_excel(statement_data, {
            'period_label': period_label,
            'branch_name': branch_name_label,
            'session_name': session_name_label,
        })
        resp = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        clean_name = period_label.replace(':', '').replace(' ', '_').replace('/', '-')
        resp['Content-Disposition'] = f'attachment; filename="Day_Book_{clean_name}.xlsx"'
        return resp

    if export_type == 'pdf':
        content = export_statement_pdf(statement_data, {
            'period_label': period_label,
            'branch_name': branch_name_label,
            'session_name': session_name_label,
            'branch_logo': branch_logo,
            'date_str': period_label,
        })
        resp = HttpResponse(content, content_type='application/pdf')
        clean_name = period_label.replace(':', '').replace(' ', '_').replace('/', '-')
        resp['Content-Disposition'] = f'attachment; filename="Day_Book_{clean_name}.pdf"'
        return resp

    # JSON Handshake
    if request.GET.get('format') == 'json':
        return JsonResponse({'success': True, **statement_data})

    # Table View Filter: ALL, COLLECTIONS, EXPENSES
    table_tab = request.GET.get('table_tab', 'ALL').upper()
    if table_tab not in ('ALL', 'COLLECTIONS', 'EXPENSES'):
        table_tab = 'ALL'

    context = {
        'active_mode': active_mode,
        'daily_date': daily_date,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'custom_start_date': custom_start_date,
        'custom_end_date': custom_end_date,
        'period_label': period_label,
        'table_tab': table_tab,
        'q_col': q_col,
        'q_exp': q_exp,
        'branches': branches,
        'sessions': sessions,
        'selected_branch_id': selected_branch_id,
        'selected_session_id': selected_session_id,
        'summary': statement_data['summary'],
        'collections': filtered_collections,
        'expenses': filtered_expenses,
        'years': list(range(datetime.now().year - 3, datetime.now().year + 4)),
        'month_names': [(i, calendar.month_name[i+1]) for i in range(12)],
        'today_str': today_str,
        'printed_date': datetime.now().strftime('%d %B %Y'),
    }

    # HTMX Partial Rendering for Table Swaps
    if request.headers.get('HX-Request'):
        if request.GET.get('table') == 'collections' or request.headers.get('HX-Target') == 'collectionsTableBody':
            return render(request, 'includes/daily_collections_table_partial.html', context)
        if request.GET.get('table') == 'expenses' or request.headers.get('HX-Target') == 'expensesTableBody':
            return render(request, 'includes/daily_expenses_table_partial.html', context)

    return render(request, 'daily_reports.html', context)


# -----------------------------------------------------------------------------
# Reports API Endpoints (Exact React Backend Parity)
# -----------------------------------------------------------------------------

def api_reports_statement_view(request):
    """API endpoint for /api/reports/statement/ matching React backend."""
    request.GET = request.GET.copy()
    request.GET['format'] = 'json'
    return daily_reports_view(request)


def api_session_audit_view(request):
    """API endpoint for /api/reports/session-audit/ matching React backend."""
    request.GET = request.GET.copy()
    request.GET['tab'] = 'SESSION_AUDIT'
    request.GET['format'] = 'json'
    return financial_reports_view(request)


def api_payment_modes_view(request):
    """API endpoint for /api/reports/payment-modes-summary/ matching React backend."""
    request.GET = request.GET.copy()
    request.GET['tab'] = 'PAYMENT_MODES'
    request.GET['format'] = 'json'
    return financial_reports_view(request)


def api_expense_categories_view(request):
    """API endpoint for /api/reports/expense-categories-summary/ matching React backend."""
    request.GET = request.GET.copy()
    request.GET['tab'] = 'EXPENSE_CATEGORIES'
    request.GET['format'] = 'json'
    return financial_reports_view(request)


def branches_list_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip().upper()
            contact_person = request.POST.get('contact_person', '').strip()
            phone = request.POST.get('phone', '').strip()
            address = request.POST.get('address', '').strip()

            if Branch.objects.filter(code=code).exists():
                messages.error(request, f"A branch with code '{code}' already exists. Please choose a different code.")
                return redirect('branches_list')

            logo_url = None
            if request.FILES.get('logo'):
                logo_file = request.FILES['logo']
                ext = os.path.splitext(logo_file.name)[1] or '.png'
                import uuid
                filename = f"logo-branch-{uuid.uuid4()}-{int(datetime.now().timestamp())}{ext}"
                from django.conf import settings
                photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
                os.makedirs(photos_dir, exist_ok=True)
                filepath = os.path.join(photos_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in logo_file.chunks():
                        dest.write(chunk)
                logo_url = f"/media/photos/{filename}"

            branch = Branch.objects.create(
                name=name,
                code=code,
                contact_person=contact_person or None,
                phone=phone or None,
                address=address or None,
                logo_url=logo_url,
                is_active=True,
            )
            messages.success(request, f"Branch '{branch.name}' created successfully.")
            return redirect('branches_list')

        elif action == 'update':
            branch_id = request.POST.get('branch_id')
            branch = get_object_or_404(Branch, id=branch_id)
            branch.name = request.POST.get('name', '').strip()
            branch.code = request.POST.get('code', '').strip().upper()
            branch.contact_person = request.POST.get('contact_person', '').strip() or None
            branch.phone = request.POST.get('phone', '').strip() or None
            branch.address = request.POST.get('address', '').strip() or None

            if request.FILES.get('logo'):
                logo_file = request.FILES['logo']
                ext = os.path.splitext(logo_file.name)[1] or '.png'
                import uuid
                filename = f"logo-branch-{uuid.uuid4()}-{int(datetime.now().timestamp())}{ext}"
                from django.conf import settings
                photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
                os.makedirs(photos_dir, exist_ok=True)
                filepath = os.path.join(photos_dir, filename)
                with open(filepath, 'wb+') as dest:
                    for chunk in logo_file.chunks():
                        dest.write(chunk)
                branch.logo_url = f"/media/photos/{filename}"

            branch.save()
            messages.success(request, f"Branch '{branch.name}' updated successfully.")
            return redirect('branches_list')

        elif action == 'toggle_status':
            branch_id = request.POST.get('branch_id')
            branch = get_object_or_404(Branch, id=branch_id)
            branch.is_active = not branch.is_active
            branch.save()
            messages.success(request, f"Branch '{branch.name}' status set to {'Active' if branch.is_active else 'Disabled'}.")
            return redirect('branches_list')

    branches = Branch.objects.all().order_by('name')
    branches_data = []
    total_branch_students = 0
    active_branches_count = 0

    for b in branches:
        st_count = StudentAdmission.objects.filter(branch=b, is_active=True).count()
        total_branch_students += st_count
        if b.is_active:
            active_branches_count += 1
        branches_data.append({
            'branch': b,
            'students_count': st_count,
        })

    context = {
        'branches_data': branches_data,
        'active_branches_count': active_branches_count,
        'total_branch_students': total_branch_students,
    }
    return render(request, 'branches.html', context)


def check_academic_session_overlap(start_d, end_d, exclude_session_id=None):
    """
    Checks if [start_d, end_d] overlaps with any existing active AcademicSession.
    Two date intervals [S1, E1] and [S2, E2] overlap if: S1 <= E2 and E1 >= S2.
    Returns (has_overlap, list_of_overlapping_sessions)
    """
    qs = AcademicSession.objects.filter(isActive=True)
    if exclude_session_id:
        qs = qs.exclude(id=exclude_session_id)

    overlapping = []
    for other in qs:
        o_start = timezone.localtime(other.start_date).date() if timezone.is_aware(other.start_date) else other.start_date.date()
        o_end = timezone.localtime(other.end_date).date() if timezone.is_aware(other.end_date) else other.end_date.date()
        if start_d <= o_end and end_d >= o_start:
            overlapping.append({
                'session': other,
                'start_date': o_start,
                'end_date': o_end,
                'name': other.display_name or other.name,
            })
    return bool(overlapping), overlapping


def sessions_list_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name', '').strip()
            display_name = request.POST.get('display_name', '').strip()
            start_date_str = request.POST.get('start_date', '').strip()
            end_date_str = request.POST.get('end_date', '').strip()
            is_current = request.POST.get('is_current') == 'on'

            if not name:
                messages.error(request, "Session code / key is required (e.g. 2026-27).")
                return redirect('sessions_list')

            if AcademicSession.objects.filter(name__iexact=name).exists():
                messages.error(request, f"Academic session code '{name}' already exists. Please choose a unique code.")
                return redirect('sessions_list')

            if not start_date_str or not end_date_str:
                messages.error(request, "Both Start Date and End Date are required.")
                return redirect('sessions_list')

            try:
                start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                messages.error(request, "Invalid date format. Please select valid dates.")
                return redirect('sessions_list')

            if start_d >= end_d:
                messages.error(request, "Invalid date range: Start Date must be strictly before End Date.")
                return redirect('sessions_list')

            has_overlap, overlaps = check_academic_session_overlap(start_d, end_d)
            if has_overlap:
                conflict_details = ", ".join([
                    f"'{o['name']}' ({o['start_date'].strftime('%d %b %Y')} to {o['end_date'].strftime('%d %b %Y')})"
                    for o in overlaps
                ])
                messages.error(
                    request,
                    f"Date overlap error: The selected range ({start_d.strftime('%d %b %Y')} to {end_d.strftime('%d %b %Y')}) "
                    f"overlaps with existing active session(s): {conflict_details}. Academic sessions cannot have overlapping dates."
                )
                return redirect('sessions_list')

            if is_current:
                AcademicSession.objects.filter(is_current=True).update(is_current=False)

            start_dt = timezone.make_aware(datetime.combine(start_d, datetime.min.time()))
            end_dt = timezone.make_aware(datetime.combine(end_d, datetime.max.time().replace(microsecond=0)))

            session = AcademicSession.objects.create(
                name=name,
                display_name=display_name or f"Academic Year {name}",
                start_date=start_dt,
                end_date=end_dt,
                is_current=is_current,
                isActive=True,
            )
            if is_current:
                request.session['selected_session_id'] = str(session.id)
            messages.success(request, f"Academic session '{session.display_name}' created successfully.")
            return redirect('sessions_list')

        elif action == 'update':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AcademicSession, id=session_id)
            name = request.POST.get('name', '').strip()
            display_name = request.POST.get('display_name', '').strip()
            start_date_str = request.POST.get('start_date', '').strip()
            end_date_str = request.POST.get('end_date', '').strip()
            is_current = request.POST.get('is_current') == 'on'

            if not name:
                messages.error(request, "Session code / key is required.")
                return redirect('sessions_list')

            if AcademicSession.objects.filter(name__iexact=name).exclude(id=session.id).exists():
                messages.error(request, f"Academic session code '{name}' is already in use by another session.")
                return redirect('sessions_list')

            if not start_date_str or not end_date_str:
                messages.error(request, "Both Start Date and End Date are required.")
                return redirect('sessions_list')

            try:
                start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                messages.error(request, "Invalid date format. Please select valid dates.")
                return redirect('sessions_list')

            if start_d >= end_d:
                messages.error(request, "Invalid date range: Start Date must be strictly before End Date.")
                return redirect('sessions_list')

            has_overlap, overlaps = check_academic_session_overlap(start_d, end_d, exclude_session_id=session.id)
            if has_overlap:
                conflict_details = ", ".join([
                    f"'{o['name']}' ({o['start_date'].strftime('%d %b %Y')} to {o['end_date'].strftime('%d %b %Y')})"
                    for o in overlaps
                ])
                messages.error(
                    request,
                    f"Date overlap error: The selected range ({start_d.strftime('%d %b %Y')} to {end_d.strftime('%d %b %Y')}) "
                    f"overlaps with existing active session(s): {conflict_details}. Academic sessions cannot have overlapping dates."
                )
                return redirect('sessions_list')

            start_dt = timezone.make_aware(datetime.combine(start_d, datetime.min.time()))
            end_dt = timezone.make_aware(datetime.combine(end_d, datetime.max.time().replace(microsecond=0)))

            session.name = name
            session.display_name = display_name or f"Academic Year {name}"
            session.start_date = start_dt
            session.end_date = end_dt

            if is_current and not session.is_current:
                AcademicSession.objects.filter(is_current=True).update(is_current=False)
                session.is_current = True
                request.session['selected_session_id'] = str(session.id)
            elif not is_current and session.is_current:
                session.is_current = False

            session.save()
            messages.success(request, f"Academic session '{session.display_name}' updated successfully.")
            return redirect('sessions_list')

        elif action == 'set_current':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AcademicSession, id=session_id)
            AcademicSession.objects.filter(is_current=True).update(is_current=False)
            session.is_current = True
            session.save()
            request.session['selected_session_id'] = str(session.id)
            messages.success(request, f"Active academic session switched to '{session.display_name}'.")
            return redirect('sessions_list')

        elif action == 'toggle_status':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AcademicSession, id=session_id)

            if not session.isActive:
                s_start = timezone.localtime(session.start_date).date() if timezone.is_aware(session.start_date) else session.start_date.date()
                s_end = timezone.localtime(session.end_date).date() if timezone.is_aware(session.end_date) else session.end_date.date()
                has_overlap, overlaps = check_academic_session_overlap(s_start, s_end, exclude_session_id=session.id)
                if has_overlap:
                    conflict_details = ", ".join([
                        f"'{o['name']}' ({o['start_date'].strftime('%d %b %Y')} to {o['end_date'].strftime('%d %b %Y')})"
                        for o in overlaps
                    ])
                    messages.error(
                        request,
                        f"Cannot activate session '{session.display_name or session.name}': Its date range "
                        f"({s_start.strftime('%d %b %Y')} to {s_end.strftime('%d %b %Y')}) overlaps with active session(s): {conflict_details}. "
                        f"Please edit the dates before activating."
                    )
                    return redirect('sessions_list')

            session.isActive = not session.isActive
            session.save()
            status_text = "activated" if session.isActive else "deactivated"
            messages.success(request, f"Academic session '{session.display_name or session.name}' {status_text} successfully.")
            return redirect('sessions_list')

        elif action == 'delete':
            session_id = request.POST.get('session_id')
            session = get_object_or_404(AcademicSession, id=session_id)
            if session.is_current:
                messages.error(request, "Cannot delete the currently active operational session. Switch active session first.")
                return redirect('sessions_list')

            st_count = StudentAdmission.objects.filter(session=session).count()
            if st_count > 0:
                messages.error(request, f"Cannot delete session '{session.display_name}': It has {st_count} enrolled students. Sessions with student records cannot be deleted.")
                return redirect('sessions_list')

            disp = session.display_name or session.name
            session.delete()
            messages.success(request, f"Academic session '{disp}' deleted successfully.")
            return redirect('sessions_list')

    sessions = list(AcademicSession.objects.all().order_by('-start_date'))
    sessions_data = []
    current_session = None
    current_session_students = 0

    # Calculate date overlaps among all sessions for conflict flagging
    conflicting_session_ids = set()
    conflict_map = {}
    for i, s1 in enumerate(sessions):
        if not s1.isActive:
            continue
        s1_start = timezone.localtime(s1.start_date).date() if timezone.is_aware(s1.start_date) else s1.start_date.date()
        s1_end = timezone.localtime(s1.end_date).date() if timezone.is_aware(s1.end_date) else s1.end_date.date()
        for j, s2 in enumerate(sessions):
            if i == j or not s2.isActive:
                continue
            s2_start = timezone.localtime(s2.start_date).date() if timezone.is_aware(s2.start_date) else s2.start_date.date()
            s2_end = timezone.localtime(s2.end_date).date() if timezone.is_aware(s2.end_date) else s2.end_date.date()
            if s1_start <= s2_end and s1_end >= s2_start:
                conflicting_session_ids.add(s1.id)
                if s1.id not in conflict_map:
                    conflict_map[s1.id] = []
                conflict_map[s1.id].append(s2.display_name or s2.name)

    for s in sessions:
        st_count = StudentAdmission.objects.filter(session=s, is_active=True).count()
        if s.is_current:
            current_session = s
            current_session_students = st_count
        sessions_data.append({
            'session': s,
            'students_count': st_count,
            'has_overlap_conflict': s.id in conflicting_session_ids,
            'conflicting_with': ", ".join(conflict_map.get(s.id, [])),
        })

    # JSON serialization for client-side instant validation
    sessions_json = json.dumps([
        {
            'id': str(s.id),
            'name': s.name,
            'displayName': s.display_name or s.name,
            'startDate': timezone.localtime(s.start_date).strftime('%Y-%m-%d') if timezone.is_aware(s.start_date) else s.start_date.strftime('%Y-%m-%d'),
            'endDate': timezone.localtime(s.end_date).strftime('%Y-%m-%d') if timezone.is_aware(s.end_date) else s.end_date.strftime('%Y-%m-%d'),
            'startDateFormatted': timezone.localtime(s.start_date).strftime('%d %b %Y') if timezone.is_aware(s.start_date) else s.start_date.strftime('%d %b %Y'),
            'endDateFormatted': timezone.localtime(s.end_date).strftime('%d %b %Y') if timezone.is_aware(s.end_date) else s.end_date.strftime('%d %b %Y'),
            'isActive': s.isActive,
            'isCurrent': s.is_current,
        }
        for s in sessions
    ])

    context = {
        'sessions_data': sessions_data,
        'current_session': current_session,
        'current_session_students': current_session_students,
        'sessions_json': sessions_json,
        'total_conflicts_count': len(conflicting_session_ids),
    }
    return render(request, 'sessions.html', context)

def backup_manage_view(request):
    """
    Backup & Data Restore Management matching React BackupPage.tsx.
    Provides storage telemetry, one-click full backup snapshot (.zip),
    external backup file upload & restore, local snapshot restore,
    direct download, and snapshot deletion with pre-restore safety snapshots.
    """
    paths = get_storage_paths()

    # Handle Downloads via ?download=<filename>
    download_file = request.GET.get('download')
    if download_file:
        safe_name = os.path.basename(download_file)
        file_path = os.path.join(paths['backups_dir'], safe_name)
        if os.path.exists(file_path):
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=safe_name)
        messages.error(request, f"Backup file '{safe_name}' not found on disk.")
        return redirect('backup_manage')

    # Handle Actions
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            try:
                b = create_full_backup_snapshot()
                messages.success(
                    request,
                    f"Full backup '{b['fileName']}' ({format_bytes(b['sizeBytes'])}) created! "
                    f"Included {b['photosCount']} photos & {b['attachmentsCount']} attachments."
                )
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': True, 'message': 'Backup created successfully', 'backup': b})
            except Exception as e:
                messages.error(request, f"Failed to create backup: {str(e)}")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
            return redirect('backup_manage')

        elif action == 'restore_local':
            file_name = request.POST.get('file_name', '').strip()
            if not file_name:
                messages.error(request, "Please select a valid backup snapshot to restore.")
                return redirect('backup_manage')
            safe_name = os.path.basename(file_name)
            file_path = os.path.join(paths['backups_dir'], safe_name)
            try:
                res = execute_restore_from_file(file_path, safe_name)
                messages.success(request, res['message'])
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': True, **res})
            except Exception as e:
                messages.error(request, f"Restore failed: {str(e)}")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
            return redirect('backup_manage')

        elif action == 'upload_restore':
            if not request.FILES.get('backup_file'):
                messages.error(request, "No backup file uploaded. Please select a .zip or .db file.")
                return redirect('backup_manage')
            uploaded_file = request.FILES['backup_file']
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext not in ('.zip', '.db'):
                messages.error(request, "Only .zip (Full Backup) or .db (Database Snapshot) files can be restored.")
                return redirect('backup_manage')

            timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
            permanent_name = f"sutawane-uploaded-{timestamp}{ext}"
            permanent_path = os.path.join(paths['backups_dir'], permanent_name)

            try:
                with open(permanent_path, 'wb') as dest:
                    for chunk in uploaded_file.chunks():
                        dest.write(chunk)

                res = execute_restore_from_file(permanent_path, uploaded_file.name)
                messages.success(request, f"Uploaded backup restored successfully! {res['message']}")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': True, 'uploadedFileName': permanent_name, **res})
            except Exception as e:
                messages.error(request, f"Upload restore failed: {str(e)}")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
            return redirect('backup_manage')

        elif action == 'delete':
            file_name = request.POST.get('file_name', '').strip()
            if not file_name:
                messages.error(request, "Snapshot filename is required for deletion.")
                return redirect('backup_manage')
            try:
                delete_backup(file_name)
                messages.success(request, f"Backup snapshot '{os.path.basename(file_name)}' removed from disk.")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': True, 'message': f"Backup snapshot '{file_name}' removed."})
            except Exception as e:
                messages.error(request, f"Failed to remove backup: {str(e)}")
                if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'success': False, 'error': str(e)}, status=500)
            return redirect('backup_manage')

    # GET Request Handling
    data = list_backups()

    if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
        return JsonResponse({'success': True, **data})

    context = {
        'stats': data['stats'],
        'backups': data['backups'],
    }
    return render(request, 'backup.html', context)


# -----------------------------------------------------------------------------
# Backup REST API Endpoints (100% React Client Parity)
# -----------------------------------------------------------------------------

def api_backup_list_view(request):
    """GET /api/backup/ - Lists all existing backups & storage stats matching React."""
    data = list_backups()
    return JsonResponse({'success': True, **data})


@require_POST
def api_backup_create_view(request):
    """POST /api/backup/create/ - Creates a full backup snapshot (.zip)."""
    if not can_manage_system(request):
        return JsonResponse({'error': 'You do not have permission to create backups.'}, status=403)
    try:
        backup = create_full_backup_snapshot()
        return JsonResponse({
            'success': True,
            'message': 'Full backup archive created successfully including SQLite database and media files.',
            'backup': backup,
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': 'Failed to create complete backup archive', 'details': str(e)}, status=500)


def api_backup_download_view(request, file_name):
    """GET /api/backup/<file_name>/download/ - Streams backup file directly."""
    paths = get_storage_paths()
    safe_name = os.path.basename(file_name)
    file_path = os.path.join(paths['backups_dir'], safe_name)
    if not os.path.exists(file_path):
        return JsonResponse({'error': 'Requested backup file does not exist'}, status=404)
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=safe_name)


@require_POST
def api_backup_restore_local_view(request):
    """POST /api/backup/restore-local/ - Restores data from existing local snapshot."""
    if not can_manage_system(request):
        return JsonResponse({'error': 'You do not have permission to restore backups.'}, status=403)
    try:
        body = {}
        if request.body:
            try:
                body = json.loads(request.body)
            except Exception:
                pass
        file_name = body.get('fileName') or request.POST.get('fileName')
        if not file_name:
            return JsonResponse({'error': 'Backup fileName is required for local restore'}, status=400)

        paths = get_storage_paths()
        safe_name = os.path.basename(str(file_name).strip())
        file_path = os.path.join(paths['backups_dir'], safe_name)
        if not os.path.exists(file_path):
            return JsonResponse({'error': f"Backup snapshot '{safe_name}' not found in storage."}, status=404)

        result = execute_restore_from_file(file_path, safe_name)
        return JsonResponse({'success': True, **result})
    except Exception as e:
        return JsonResponse({'error': 'Failed to restore backup snapshot', 'details': str(e)}, status=500)


@require_POST
def api_backup_upload_restore_view(request):
    """POST /api/backup/upload-restore/ - Uploads and restores an external backup file."""
    if not can_manage_system(request):
        return JsonResponse({'error': 'You do not have permission to restore backups.'}, status=403)
    try:
        uploaded_file = request.FILES.get('backupFile') or request.FILES.get('backup_file')
        if not uploaded_file:
            return JsonResponse({'error': 'No backup file uploaded. Please select a .zip or .db file.'}, status=400)

        paths = get_storage_paths()
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ('.zip', '.db'):
            return JsonResponse({'error': 'Only .zip (Full Backup) or .db (Database Snapshot) files are accepted for restore'}, status=400)

        timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        permanent_name = f"sutawane-uploaded-{timestamp}{ext}"
        permanent_path = os.path.join(paths['backups_dir'], permanent_name)

        with open(permanent_path, 'wb') as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        result = execute_restore_from_file(permanent_path, uploaded_file.name)
        return JsonResponse({'success': True, 'uploadedFileName': permanent_name, **result})
    except Exception as e:
        return JsonResponse({'error': 'Failed to process uploaded backup file', 'details': str(e)}, status=500)


@require_http_methods(["DELETE", "POST"])
def api_backup_delete_view(request, file_name):
    """DELETE /api/backup/<file_name>/ - Deletes a backup snapshot from disk."""
    if not can_manage_system(request):
        return JsonResponse({'error': 'You do not have permission to delete backups.'}, status=403)
    try:
        safe_name = delete_backup(file_name)
        return JsonResponse({'success': True, 'message': f"Backup snapshot '{safe_name}' removed."})
    except FileNotFoundError:
        return JsonResponse({'error': 'Backup file not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': 'Failed to delete backup file', 'details': str(e)}, status=500)


# -----------------------------------------------------------------------------
# Institute Settings & Master Branding Management
# -----------------------------------------------------------------------------

def get_institute_settings_dict():
    """Returns dictionary of all system settings with robust fallbacks."""
    records = SystemSetting.objects.all()
    settings_map = {s.key: s.value for s in records}
    return {
        'institute_name': settings_map.get('institute_name', 'Sutawane Classes'),
        'tagline': settings_map.get('tagline', 'Excellence in Coaching & Board Preparations'),
        'phone': settings_map.get('phone', '+91 98765 43210'),
        'email': settings_map.get('email', 'contact@sutawaneclasses.com'),
        'address': settings_map.get('address', 'Main Head Office, Maharashtra'),
        'website': settings_map.get('website', 'www.sutawaneclasses.com'),
        'receipt_footer': settings_map.get('receipt_footer', 'Fees once paid are non-refundable. Thank you!'),
        'logo_url': settings_map.get('logo_url') or '',
    }


def save_master_logo(file_obj):
    """
    Saves an uploaded master logo image to media/photos/ and updates SystemSetting.
    Removes old logo from disk if it was an uploaded file.
    """
    ext = os.path.splitext(file_obj.name)[1].lower() or '.png'
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.svg'):
        raise ValueError("Only image files (.png, .jpg, .jpeg, .webp, .svg) are allowed for institute logo.")

    from django.conf import settings
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    os.makedirs(photos_dir, exist_ok=True)

    # Clean old logo from disk if it was uploaded
    old_setting = SystemSetting.objects.filter(key='logo_url').first()
    if old_setting and old_setting.value:
        old_val = old_setting.value
        if '/media/photos/' in old_val or '/api/uploads/photos/' in old_val:
            old_name = os.path.basename(old_val)
            old_p = os.path.join(photos_dir, old_name)
            if os.path.exists(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass

    timestamp = int(datetime.now().timestamp() * 1000)
    filename = f"logo-master-{timestamp}{ext}"
    dest_path = os.path.join(photos_dir, filename)

    with open(dest_path, 'wb+') as dest:
        for chunk in file_obj.chunks():
            dest.write(chunk)

    logo_url = f"/media/photos/{filename}"
    SystemSetting.objects.update_or_create(
        key='logo_url',
        defaults={'value': logo_url}
    )
    return logo_url


def remove_master_logo():
    """Removes current master logo from disk and clears SystemSetting."""
    from django.conf import settings
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')

    old_setting = SystemSetting.objects.filter(key='logo_url').first()
    if old_setting and old_setting.value:
        old_val = old_setting.value
        if '/media/photos/' in old_val or '/api/uploads/photos/' in old_val:
            old_name = os.path.basename(old_val)
            old_p = os.path.join(photos_dir, old_name)
            if os.path.exists(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass

    SystemSetting.objects.update_or_create(
        key='logo_url',
        defaults={'value': ''}
    )


def settings_manage_view(request):
    """
    Central Institute Settings & Master Branding View matching React SettingsPage.tsx.
    Manages central coaching branding, logo, receipt templates, and organization profile.
    """
    if request.method == 'POST':
        action = request.POST.get('action', 'save_profile')

        if action == 'upload_logo':
            if not request.FILES.get('logo'):
                messages.error(request, "Please select an image file to upload as master logo.")
                return redirect('settings_manage')
            logo_file = request.FILES['logo']
            if logo_file.size > 5 * 1024 * 1024:
                messages.error(request, "Logo file size must not exceed 5 MB.")
                return redirect('settings_manage')
            try:
                save_master_logo(logo_file)
                messages.success(request, "Master institute logo uploaded successfully!")
            except Exception as e:
                messages.error(request, f"Failed to upload logo: {str(e)}")
            return redirect('settings_manage')

        elif action == 'remove_logo':
            try:
                remove_master_logo()
                messages.success(request, "Master institute logo removed.")
            except Exception as e:
                messages.error(request, f"Failed to remove logo: {str(e)}")
            return redirect('settings_manage')

        else:
            # Save Institute Profile & Receipt Terms
            fields = [
                'institute_name', 'tagline', 'phone', 'email',
                'address', 'website', 'receipt_footer'
            ]
            for f in fields:
                val = request.POST.get(f, '').strip()
                SystemSetting.objects.update_or_create(
                    key=f,
                    defaults={'value': val}
                )

            # Optional logo upload bundled with the form
            if request.FILES.get('logo'):
                logo_file = request.FILES['logo']
                if logo_file.size <= 5 * 1024 * 1024:
                    try:
                        save_master_logo(logo_file)
                    except Exception as e:
                        messages.warning(request, f"Profile saved, but logo upload failed: {str(e)}")

            messages.success(request, "Institute settings saved successfully!")
            return redirect('settings_manage')

    settings_dict = get_institute_settings_dict()

    if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
        return JsonResponse(settings_dict)

    return render(request, 'settings.html', {'settings': settings_dict})


# -----------------------------------------------------------------------------
# Settings REST API Endpoints (100% React Parity)
# -----------------------------------------------------------------------------

def api_settings_view(request):
    """GET /api/settings/ or POST /api/settings/ matching React backend."""
    if request.method == 'GET':
        return JsonResponse(get_institute_settings_dict())

    elif request.method == 'POST':
        if not can_manage_system(request):
            return JsonResponse({'error': 'You do not have permission to modify settings.'}, status=403)
        try:
            body = {}
            if request.body:
                try:
                    body = json.loads(request.body.decode('utf-8'))
                except Exception:
                    pass
            data = body or request.POST
            for key, val in data.items():
                if val is not None:
                    SystemSetting.objects.update_or_create(
                        key=key,
                        defaults={'value': str(val).strip()}
                    )
            return JsonResponse({'success': True, 'message': 'Settings saved successfully'})
        except Exception as e:
            return JsonResponse({'error': 'Failed to save settings', 'details': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def api_settings_logo_view(request):
    """POST /api/settings/logo/ or DELETE /api/settings/logo/ matching React backend."""
    if request.method == 'POST':
        if not can_manage_system(request):
            return JsonResponse({'error': 'You do not have permission to modify the institute logo.'}, status=403)
        logo_file = request.FILES.get('logo')
        if not logo_file:
            return JsonResponse({'error': 'No logo image file was provided'}, status=400)
        if logo_file.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Logo file size must not exceed 5 MB'}, status=400)
        try:
            logo_url = save_master_logo(logo_file)
            return JsonResponse({
                'success': True,
                'logoUrl': logo_url,
                'message': 'Master institute logo updated successfully',
            })
        except Exception as e:
            return JsonResponse({'error': 'Failed to upload master logo', 'details': str(e)}, status=500)

    elif request.method in ('DELETE', 'POST') and (request.method == 'DELETE' or request.POST.get('action') == 'delete'):
        if not can_manage_system(request):
            return JsonResponse({'error': 'You do not have permission to modify the institute logo.'}, status=403)
        try:
            remove_master_logo()
            return JsonResponse({'success': True, 'message': 'Master logo removed'})
        except Exception as e:
            return JsonResponse({'error': 'Failed to delete master logo', 'details': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)
