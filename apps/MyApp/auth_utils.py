import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from django.core.mail import send_mail
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


def get_license_status() -> dict:
    """
    Retrieves and parses current software license activation and expiry status.
    """
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

    return {
        'isActive': is_active,
        'expiryDate': expiry_dt.isoformat(),
        'isExpired': is_expired,
        'daysRemaining': days_remaining,
        'developerNote': developer_note,
        'clientName': client_name,
    }


# In-memory OTP storage for Developer Login
# Format: { email: { 'code': '123456', 'expires_at': datetime, 'attempts': 0 } }
DEVELOPER_OTP_STORE = {}


def generate_and_send_developer_otp(email: str) -> tuple[bool, str, str]:
    """
    Generates a secure 6-digit OTP code and dispatches it.
    """
    clean_email = email.strip().lower()
    if clean_email != AUTHORIZED_DEVELOPER_EMAIL.lower():
        return False, "", "Unauthorized developer email address. Only authorized developers can request OTP."

    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    DEVELOPER_OTP_STORE[clean_email] = {
        'code': code,
        'expires_at': expires_at,
        'attempts': 0,
    }

    # Deliver the code only through the configured trusted mail transport.
    try:
        send_mail(
            subject='[Sutawane Classes] Developer Portal Authentication OTP',
            message=f'Your single-use 6-digit Developer Portal authentication code is: {code}\n\nThis code expires in 10 minutes.',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@ultoxy.com'),
            recipient_list=[clean_email],
            fail_silently=True,
        )
    except Exception as e:
        print(f"[DEVELOPER AUTH] Email dispatch warning: {e}")

    return True, code, f"Verification OTP code sent to {clean_email}."


def verify_developer_otp(email: str, entered_code: str) -> tuple[bool, str]:
    """
    Validates entered developer OTP.
    """
    clean_email = email.strip().lower()
    entry = DEVELOPER_OTP_STORE.get(clean_email)
    if not entry:
        return False, "No active OTP request found for this email. Please request a new OTP."

    if datetime.now(timezone.utc) > entry['expires_at']:
        DEVELOPER_OTP_STORE.pop(clean_email, None)
        return False, "The OTP code has expired. Please request a new verification code."

    if entry['attempts'] >= 5:
        DEVELOPER_OTP_STORE.pop(clean_email, None)
        return False, "Too many failed attempts. OTP invalidated. Please request a new code."

    if secrets.compare_digest(entry['code'], entered_code.strip()):
        DEVELOPER_OTP_STORE.pop(clean_email, None)
        return True, "Authentication successful."

    entry['attempts'] += 1
    return False, f"Invalid OTP code. {5 - entry['attempts']} attempts remaining."
