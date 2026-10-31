import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from django.core.mail import send_mail, EmailMultiAlternatives
from .models import SystemSetting, User, RolePermission

AUTHORIZED_DEVELOPER_EMAIL = 'prameshwar4378@gmail.com'


def hash_password(password: str, existing_salt: str = None) -> tuple[str, str]:
    """
    PBKDF2 SHA512 hash with salt matching Node.js crypto.pbkdf2Sync(password, salt, 10000, 64, 'sha512').
    """
    salt = existing_salt or secrets.token_hex(16)
    hash_hex = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt.encode('utf-8'), 10000, 64).hex()
    return hash_hex, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """
    Constant-time password comparison.
    """
    calculated, _ = hash_password(password, salt)
    return secrets.compare_digest(calculated, stored_hash)


def invalidate_license_cache():
    """Invalidates the in-memory license status cache."""
    from .cache_utils import safe_cache_delete, invalidate_namespace
    safe_cache_delete('software_license_status')
    invalidate_namespace('license')


def get_license_status(force_refresh: bool = False) -> dict:
    """
    Retrieves and parses current software license activation and expiry status.
    Uses RAM cache with automated invalidation to eliminate repeated database queries across middleware checks.
    """
    from .cache_utils import safe_cache_get, safe_cache_set, TTL_LICENSE
    CACHE_KEY = 'software_license_status'
    if not force_refresh:
        cached = safe_cache_get(CACHE_KEY)
        if cached is not None:
            return cached

    keys = ['license_is_active', 'license_expiry_date', 'license_developer_note', 'license_client_name']
    settings_qs = SystemSetting.objects.filter(key__in=keys)
    data = {s.key: s.value for s in settings_qs}

    # Default expiry: 1 year from now if not present
    expiry_date_str = data.get('license_expiry_date')
    if not expiry_date_str:
        one_year_later = datetime.now(timezone.utc) + timedelta(days=365)
        expiry_date_str = one_year_later.isoformat()
        SystemSetting.objects.update_or_create(
            key='license_expiry_date',
            defaults={'value': expiry_date_str}
        )

    is_active = data.get('license_is_active', 'true').lower() != 'false'
    developer_note = data.get('license_developer_note') or 'Support Helpline: +91 7776824564 (Mr. Rameshwar Pawar)'
    client_name = data.get('license_client_name') or 'Sutawane Classes'

    # Parse expiry
    try:
        if 'T' in expiry_date_str:
            expiry_dt = datetime.fromisoformat(expiry_date_str.replace('Z', '+00:00'))
        else:
            expiry_dt = datetime.strptime(expiry_date_str, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
    except Exception:
        expiry_dt = datetime.now(timezone.utc) + timedelta(days=365)

    now = datetime.now(timezone.utc)
    is_expired = now > expiry_dt
    days_remaining = 0 if is_expired else max(0, (expiry_dt - now).days)

    res = {
        'isActive': is_active,
        'expiryDate': expiry_dt.isoformat(),
        'isExpired': is_expired,
        'daysRemaining': days_remaining,
        'developerNote': developer_note,
        'clientName': client_name,
    }
    safe_cache_set(CACHE_KEY, res, TTL_LICENSE)
    return res


import json
import re

# In-memory OTP storage fallback
DEVELOPER_OTP_STORE = {}


def _get_otp_entry(clean_email: str) -> dict | None:
    """
    Retrieves OTP entry from persistent SQLite SystemSetting, fallback to in-memory store.
    Prevents OTP loss on server reload or process restart.
    """
    key = f"dev_otp_{clean_email}"
    try:
        setting = SystemSetting.objects.filter(key=key).first()
        if setting and setting.value:
            data = json.loads(setting.value)
            if 'expires_at' in data and isinstance(data['expires_at'], str):
                data['expires_at'] = datetime.fromisoformat(data['expires_at'])
            return data
    except Exception as e:
        print(f"[DEVELOPER AUTH] DB OTP fetch notice: {e}", flush=True)

    return DEVELOPER_OTP_STORE.get(clean_email)


def _save_otp_entry(clean_email: str, entry: dict):
    """
    Persists OTP entry to both SQLite SystemSetting and in-memory dictionary.
    """
    DEVELOPER_OTP_STORE[clean_email] = entry
    key = f"dev_otp_{clean_email}"
    try:
        payload = {
            'code': str(entry['code']).strip(),
            'expires_at': entry['expires_at'].isoformat() if hasattr(entry['expires_at'], 'isoformat') else str(entry['expires_at']),
            'attempts': int(entry.get('attempts', 0)),
        }
        SystemSetting.objects.update_or_create(
            key=key,
            defaults={'value': json.dumps(payload)}
        )
    except Exception as e:
        print(f"[DEVELOPER AUTH] DB OTP save notice: {e}", flush=True)


def _clear_otp_entry(clean_email: str):
    """
    Clears OTP entry from both persistent database and in-memory store.
    """
    DEVELOPER_OTP_STORE.pop(clean_email, None)
    key = f"dev_otp_{clean_email}"
    try:
        SystemSetting.objects.filter(key=key).delete()
    except Exception as e:
        print(f"[DEVELOPER AUTH] DB OTP clear notice: {e}", flush=True)


def generate_and_send_developer_otp(email: str) -> tuple[bool, str, str]:
    """
    Generates a secure 6-digit OTP code, persists it to DB, and dispatches via Gmail SMTP.
    """
    clean_email = email.strip().lower()
    if clean_email != AUTHORIZED_DEVELOPER_EMAIL.lower():
        return False, "", "Unauthorized developer email address. Only authorized developers can request OTP."

    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    entry = {
        'code': code,
        'expires_at': expires_at,
        'attempts': 0,
    }
    _save_otp_entry(clean_email, entry)

    # Print to console for instant local development access as well
    print(f"\n=======================================================", flush=True)
    print(f"[DEVELOPER AUTH] OTP Generated for {clean_email}: {code}", flush=True)
    print(f"=======================================================\n", flush=True)

    # Deliver the code through configured trusted Gmail SMTP transport
    try:
        subject = f"🔐 Developer Login OTP: {code} (Sutawane Classes)"
        text_message = (
            f"Your One-Time Password (OTP) for Developer Login is: {code}\n\n"
            f"This code expires in 10 minutes and can only be used once.\n\n"
            f"Sutawane Classes Software • Secure Authentication"
        )
        # Note: {code} must be strictly contiguous without newline/whitespace so copy-paste is exact
        html_message = f"""
        <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;">
          <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #1e3a8a; margin: 0; font-size: 22px;">Sutawane Classes Software</h2>
            <p style="color: #64748b; font-size: 13px; margin-top: 4px;">Developer Management Portal Authentication</p>
          </div>

          <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
            <span style="font-size: 13px; color: #166534; display: block; margin-bottom: 8px; font-weight: 600;">Your One-Time Password (OTP):</span>
            <div style="font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #15803d; font-family: 'Courier New', monospace; user-select: all;">{code}</div>
            <span style="font-size: 11px; color: #4ade80; display: block; margin-top: 8px; font-weight: 500;">Valid for 10 minutes &bull; Single Use Only</span>
          </div>

          <p style="font-size: 12px; color: #64748b; line-height: 1.6;">
            This One-Time Password was requested to authenticate your <strong>Developer Session</strong> in the Sutawane Classes Management System.
            If you did not request this OTP, you can safely ignore this email.
          </p>

          <div style="border-top: 1px solid #e2e8f0; margin-top: 24px; padding-top: 12px; font-size: 11px; color: #94a3b8; text-align: center;">
            Sutawane Classes Desktop Management System &bull; Secure Authentication
          </div>
        </div>
        """
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'prameshwar4378@gmail.com'),
            to=[clean_email],
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        print(f"[DEVELOPER AUTH] OTP email successfully delivered to {clean_email}", flush=True)
    except Exception as e:
        print(f"[DEVELOPER AUTH] Email dispatch error: {e}", flush=True)
        return False, "", f"Failed to send email to {clean_email}: {str(e)}"

    return True, code, f"Verification OTP code sent to {clean_email}."


def verify_developer_otp(email: str, entered_code: str) -> tuple[bool, str]:
    """
    Validates entered developer OTP against persistent DB storage.
    Handles extra whitespace, hyphens, and copies from emails.
    """
    clean_email = email.strip().lower()
    # Strip any non-digit character (e.g. spaces, hyphens, tabs, newlines)
    clean_code = re.sub(r'[^0-9]', '', str(entered_code or '')).strip()

    if not clean_code:
        return False, "Please enter the 6-digit verification code."

    if len(clean_code) != 6:
        return False, f"OTP code must be exactly 6 digits (received {len(clean_code)} digits)."

    entry = _get_otp_entry(clean_email)
    if not entry:
        return False, "No active OTP request found for this email. Please click 'Send Verification OTP' to request a new code."

    now = datetime.now(timezone.utc)
    if now > entry['expires_at']:
        _clear_otp_entry(clean_email)
        return False, "The OTP code has expired. Please request a new verification code."

    attempts = entry.get('attempts', 0)
    if attempts >= 5:
        _clear_otp_entry(clean_email)
        return False, "Too many failed attempts. OTP invalidated. Please request a new code."

    if secrets.compare_digest(str(entry['code']).strip(), clean_code):
        _clear_otp_entry(clean_email)
        print(f"[DEVELOPER AUTH] OTP verified successfully for {clean_email}", flush=True)
        return True, "Authentication successful."

    entry['attempts'] = attempts + 1
    _save_otp_entry(clean_email, entry)
    remaining = 5 - entry['attempts']
    return False, f"Invalid OTP code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."


# -------------------------------------------------------------
# Role-Based Access Control (RBAC) & Permission Evaluator
# -------------------------------------------------------------

DEFAULT_BRANCH_MANAGER_PERMISSIONS = {
    'can_view_students': True,
    'can_add_students': True,
    'can_edit_students': True,
    'can_delete_students': False,
    'can_promote_students': False,
    'can_collect_fees': True,
    'can_void_receipts': False,
    'can_view_dues': True,
    'can_send_fee_reminders': True,
    'can_view_expenses': True,
    'can_add_expenses': True,
    'can_delete_expenses': False,
    'can_view_reports': True,
    'can_view_daily_reports': True,
    'can_export_reports': True,
    'can_manage_courses': False,
    'can_manage_sessions': False,
    'restricted_to_assigned_branch': True,
    'can_access_backup': False,
    'can_access_settings': False,
}

ALL_PERMISSIONS_GRANTED = {
    'can_view_students': True,
    'can_add_students': True,
    'can_edit_students': True,
    'can_delete_students': True,
    'can_promote_students': True,
    'can_collect_fees': True,
    'can_void_receipts': True,
    'can_view_dues': True,
    'can_send_fee_reminders': True,
    'can_view_expenses': True,
    'can_add_expenses': True,
    'can_delete_expenses': True,
    'can_view_reports': True,
    'can_view_daily_reports': True,
    'can_export_reports': True,
    'can_manage_courses': True,
    'can_manage_sessions': True,
    'restricted_to_assigned_branch': False,
    'can_access_backup': True,
    'can_access_settings': True,
    'can_manage_roles': True,
}


def invalidate_permissions_cache(user_id=None):
    """Invalidates the in-memory permissions cache."""
    from .cache_utils import safe_cache_delete, invalidate_namespace
    if user_id:
        safe_cache_delete(f"user_perms_{user_id}")
    safe_cache_delete("default_bm_permissions")
    invalidate_namespace('permissions')
    if not user_id:
        try:
            for uid in User.objects.filter(role='BRANCH_MANAGER').values_list('id', flat=True):
                safe_cache_delete(f"user_perms_{uid}")
        except Exception:
            pass


def get_default_branch_manager_permissions() -> RolePermission:
    """Gets or creates the default RolePermission record for BRANCH_MANAGER."""
    perm, created = RolePermission.objects.get_or_create(
        role='BRANCH_MANAGER',
        user__isnull=True,
        defaults=DEFAULT_BRANCH_MANAGER_PERMISSIONS,
    )
    return perm


def get_user_permissions(user) -> dict:
    """
    Returns a dictionary of all permissions for the specified user.
    - DEVELOPER: 100% unrestricted access.
    - CLASS_OWNER: Full administrative access.
    - BRANCH_MANAGER: Scoped by RolePermission matrix configured by Class Owner.
    """
    if not user:
        return {k: False for k in ALL_PERMISSIONS_GRANTED}

    # Developers and Class Owners have full unrestricted permissions
    if user.is_developer or user.is_class_owner:
        return ALL_PERMISSIONS_GRANTED.copy()

    # Branch Manager
    from .cache_utils import safe_cache_get, safe_cache_set, build_cache_key
    cache_key = build_cache_key('permissions', f"user_perms_{user.id}")
    cached = safe_cache_get(cache_key)
    if cached is not None:
        return cached

    # Check for per-user custom permission override
    perm_obj = getattr(user, 'custom_permissions', None)
    if not perm_obj:
        try:
            perm_obj = RolePermission.objects.filter(user=user).first()
        except Exception:
            perm_obj = None

    # Fall back to role-wide default for BRANCH_MANAGER
    if not perm_obj:
        try:
            perm_obj = RolePermission.objects.filter(role='BRANCH_MANAGER', user__isnull=True).first()
            if not perm_obj:
                perm_obj = get_default_branch_manager_permissions()
        except Exception:
            perm_obj = None

    if perm_obj:
        res = {
            'can_view_students': bool(perm_obj.can_view_students),
            'can_add_students': bool(perm_obj.can_add_students),
            'can_edit_students': bool(perm_obj.can_edit_students),
            'can_delete_students': bool(perm_obj.can_delete_students),
            'can_promote_students': bool(perm_obj.can_promote_students),
            'can_collect_fees': bool(perm_obj.can_collect_fees),
            'can_void_receipts': bool(perm_obj.can_void_receipts),
            'can_view_dues': bool(perm_obj.can_view_dues),
            'can_send_fee_reminders': bool(perm_obj.can_send_fee_reminders),
            'can_view_expenses': bool(perm_obj.can_view_expenses),
            'can_add_expenses': bool(perm_obj.can_add_expenses),
            'can_delete_expenses': bool(perm_obj.can_delete_expenses),
            'can_view_reports': bool(perm_obj.can_view_reports),
            'can_view_daily_reports': bool(perm_obj.can_view_daily_reports),
            'can_export_reports': bool(perm_obj.can_export_reports),
            'can_manage_courses': bool(perm_obj.can_manage_courses),
            'can_manage_sessions': bool(perm_obj.can_manage_sessions),
            'restricted_to_assigned_branch': bool(perm_obj.restricted_to_assigned_branch),
            'can_access_backup': bool(perm_obj.can_access_backup),
            'can_access_settings': bool(perm_obj.can_access_settings),
            'can_manage_roles': False,  # Branch manager cannot manage roles
        }
    else:
        res = DEFAULT_BRANCH_MANAGER_PERMISSIONS.copy()

    safe_cache_set(cache_key, res, 300)
    return res


def has_permission(user, permission_name: str) -> bool:
    """
    Checks if a user is granted a specific permission.
    """
    if not user:
        return False
    if user.is_developer:
        # Developer is never restricted to an assigned branch
        if permission_name == 'restricted_to_assigned_branch':
            return False
        return True
    if user.is_class_owner:
        # Developer portal is strictly developer only
        if permission_name == 'developer_portal':
            return False
        # Class Owner oversees all branches and is never restricted to a single branch
        if permission_name == 'restricted_to_assigned_branch':
            return False
        return True

    perms = get_user_permissions(user)
    return bool(perms.get(permission_name, False))

