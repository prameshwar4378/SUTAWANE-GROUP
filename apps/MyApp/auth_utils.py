import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from .models import SystemSetting, User

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
    from django.core.cache import cache
    cache.delete('software_license_status')


def get_license_status(force_refresh: bool = False) -> dict:
    """
    Retrieves and parses current software license activation and expiry status.
    Uses RAM cache (60s) to eliminate repeated database queries across middleware checks.
    """
    from django.core.cache import cache
    CACHE_KEY = 'software_license_status'
    if not force_refresh:
        cached = cache.get(CACHE_KEY)
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
    cache.set(CACHE_KEY, res, 60)
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
