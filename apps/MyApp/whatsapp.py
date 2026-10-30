"""
WhatsApp Automation Engine for Sutawane Classes Management Software.
Standardizes international phone formatting (E.164 / India 91 prefix) and generates
professional WhatsApp message deep links for:
1. Fee Payment Receipts
2. Intelligent Fee Reminders (4 granular settlement cases)
3. New Admission Confirmations
4. General Parent Notices
"""

import urllib.parse
from datetime import datetime


def format_whatsapp_number(raw_phone: str) -> str:
    """
    Standardize phone numbers to international WhatsApp format.
    Defaults to India (+91) if 10 or 11 digits provided.
    Examples:
      '9876543210' -> '919876543210'
      '09876543210' -> '919876543210'
      '+91 98765 43210' -> '919876543210'
      '919876543210' -> '919876543210'
    """
    if not raw_phone:
        return ''
    digits = ''.join(c for c in str(raw_phone) if c.isdigit())

    # 10 digits e.g. 9876543210 -> 919876543210
    if len(digits) == 10:
        return f"91{digits}"

    # 11 digits starting with 0 e.g. 09876543210 -> 919876543210
    if len(digits) == 11 and digits.startswith('0'):
        return f"91{digits[1:]}"

    # 12 digits starting with 91 e.g. 919876543210
    if len(digits) == 12 and digits.startswith('91'):
        return digits

    return digits


def generate_whatsapp_url(phone: str, message: str) -> str:
    """
    Generates a universal https://api.whatsapp.com/send?phone=...&text=... deep link.
    """
    formatted_phone = format_whatsapp_number(phone)
    encoded_message = urllib.parse.quote(message)
    return f"https://api.whatsapp.com/send?phone={formatted_phone}&text={encoded_message}"


def format_currency_inr(amount: float) -> str:
    """Formats amount with Indian grouping e.g. 15,000"""
    try:
        val = int(round(float(amount)))
        # Standard Indian number formatting
        s = str(val)
        if len(s) <= 3:
            return s
        last_three = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        return ','.join(groups) + ',' + last_three
    except Exception:
        return str(amount)


def build_receipt_whatsapp_message(
    institute_name: str = 'Sutawane Classes',
    student_name: str = '',
    student_code: str = '',
    roll_number: str = '',
    standard: str = 'General',
    receipt_number: str = '',
    total_amount: float = 0.0,
    payment_date: str = '',
    payment_mode: str = 'UPI',
    reference_number: str = '',
    remaining_balance: float = 0.0,
    branch_name: str = '',
    helpline: str = ''
) -> str:
    """
    Template for Fee Payment Receipt WhatsApp Message.
    Matches React buildReceiptWhatsAppMessage exactly.
    """
    institute = (institute_name or 'Sutawane Classes').upper()
    branch_text = f"📍 *Branch:* {branch_name}\n" if branch_name else ""
    helpline_text = f"📞 *Helpline / Accounts:* {helpline}" if helpline else ""
    ref_text = f"\n• 🏦 Txn / Ref No: *{reference_number}*" if reference_number else ""

    if remaining_balance is not None:
        if remaining_balance <= 0:
            balance_text = "\n• 📊 Remaining Dues: *Nil (Fully Settled) ✅*"
        else:
            balance_text = f"\n• 📊 Remaining Dues: *₹{format_currency_inr(remaining_balance)}*"
    else:
        balance_text = ""

    lines = [
        f"🏛️ *{institute}*",
        branch_text.strip(),
        "────────────────────────",
        "🧾 *OFFICIAL FEE PAYMENT RECEIPT*\n",
        "Dear Parent, Greetings! 🙏",
        "We acknowledge with thanks the receipt of fee payment for:\n",
        f"🎓 *Student Name:* *{student_name}*",
    ]

    if student_code:
        lines.append(f"🆔 *Student ID:* *{student_code}*")
    if roll_number:
        lines.append(f"📋 *Roll Number:* *{roll_number}*")
    lines.append(f"📚 *Class / Course:* *{standard or 'General'}*\n")

    lines.append("💵 *PAYMENT SUMMARY:*")
    lines.append(f"• 🧾 Receipt No: *{receipt_number}*")
    lines.append(f"• 💳 Amount Paid: *₹{format_currency_inr(total_amount)}*")
    lines.append(f"• 📅 Payment Date: *{payment_date}*")
    lines.append(f"• 💰 Payment Mode: *{payment_mode}*{ref_text}")
    if balance_text:
        lines.append(balance_text.strip())

    lines.append("\n────────────────────────\n")
    lines.append("🙏 Thank you for your payment! Please retain this computer-generated confirmation for your records.\n")
    lines.append("Warm Regards,")
    lines.append(f"*{institute} Management*")
    if helpline_text:
        lines.append(helpline_text)

    # Clean empty lines
    return "\n".join(l for l in lines if l is not None and (l != "" or lines.index(l) in [3, 5, 8, 14, 16]))


def build_fee_reminder_whatsapp_message(
    institute_name: str = 'Sutawane Classes',
    student_name: str = '',
    student_code: str = '',
    roll_number: str = '',
    standard: str = '',
    current_pending_amount: float = 0.0,
    previous_dues_pending: float = 0.0,
    overall_pending_amount: float = None,
    next_due_date: str = None,
    branch_name: str = '',
    session_name: str = '',
    helpline: str = ''
) -> str:
    """
    Intelligent Fee Reminder WhatsApp Message Template with 4 distinct cases:
    1. Zero Dues (Appreciation note)
    2. Both Current Session & Prior Year Dues Pending
    3. Current Session Pending Only (Prior Dues Cleared)
    4. Prior Year Carried Dues Pending Only (Current Session Settled)
    """
    institute = (institute_name or 'Sutawane Classes').upper()
    branch_text = f"📍 *Branch:* {branch_name}\n" if branch_name else ""
    helpline_text = f"📞 *Helpline / Accounts:* {helpline}" if helpline else ""

    curr = float(current_pending_amount or 0.0)
    prior = float(previous_dues_pending or 0.0)
    total = float(overall_pending_amount) if overall_pending_amount is not None else (curr + prior)

    # CASE 1: 100% CLEARED
    if total <= 0 and curr <= 0 and prior <= 0:
        return (
            f"🏛️ *{institute}*\n"
            f"{branch_text}"
            f"────────────────────────\n"
            f"🎉 *FEE CLEARED — APPRECIATION NOTE*\n\n"
            f"Dear Parent, Greetings! 🙏\n\n"
            f"We are pleased to inform you that all academic fee commitments for *{student_name}* are **100% CLEARED (NIL)** across all academic sessions! ✅\n\n"
            f"📋 *Student Profile:*\n"
            f"• 🎓 *Student:* *{student_name}*\n"
            + (f"• 🆔 *Student ID:* *{student_code}*\n" if student_code else "")
            + (f"• 🏷️ *Roll No:* *{roll_number}*\n" if roll_number else "")
            + (f"• 📚 *Class / Course:* *{standard}*\n" if standard else "")
            + (f"• 📅 *Session:* *{session_name}*\n" if session_name else "")
            + f"\n🌟 *Current Fee Status:*\n"
            f"• 📚 Current Session Fee: *Paid in Full ✅*\n"
            f"• ⏳ Prior Year Dues: *Nil (Cleared) ✅*\n"
            f"• 🧾 *Total Outstanding: ₹0 (Nil)*\n\n"
            f"Thank you sincerely for your timely payments and valued partnership in your child's education!\n\n"
            f"Warm Regards,\n"
            f"*{institute} Management*\n"
            f"{helpline_text}"
        )

    # CASE 2: BOTH CURRENT AND PRIOR DUES PENDING
    if curr > 0 and prior > 0:
        due_str = f"📅 *Upcoming Due Date: {next_due_date}*\n" if next_due_date else ""
        return (
            f"🏛️ *{institute}*\n"
            f"{branch_text}"
            f"────────────────────────\n"
            f"📢 *OFFICIAL FEE PAYMENT REMINDER*\n\n"
            f"Dear Parent, Greetings! 🙏\n"
            f"This is a gentle reminder regarding the outstanding academic fee for:\n\n"
            f"🎓 *Student Name:* *{student_name}*\n"
            + (f"🆔 *Student ID:* *{student_code}*\n" if student_code else "")
            + (f"📋 *Roll Number:* *{roll_number}*\n" if roll_number else "")
            + (f"📚 *Class / Course:* *{standard}*\n" if standard else "")
            + (f"📅 *Academic Session:* *{session_name}*\n" if session_name else "")
            + f"\n💰 *FEE BALANCE BREAKDOWN:*\n"
            f"• 📚 Current Session Pending: *₹{format_currency_inr(curr)}*\n"
            f"• ⏳ Prior Session Outstanding Dues: *₹{format_currency_inr(prior)}*\n"
            f"────────────────────────\n"
            f"🧾 *TOTAL NET OUTSTANDING: ₹{format_currency_inr(total)}*\n"
            f"{due_str}"
            f"────────────────────────\n\n"
            f"💳 *Payment Methods:*\n"
            f"1. Center Office (Cash / Cheque / Card)\n"
            f"2. Online UPI Payment (Contact center office for official QR code)\n\n"
            f"Kindly arrange to clear the outstanding balance at your earliest convenience. If payment has already been remitted, please disregard this automated notification.\n\n"
            f"Warm Regards,\n"
            f"*{institute} Accounts*\n"
            f"{helpline_text}"
        )

    # CASE 3: CURRENT SESSION PENDING ONLY
    if curr > 0 and prior <= 0:
        due_str = f"📅 *Due Date: {next_due_date}*\n" if next_due_date else ""
        return (
            f"🏛️ *{institute}*\n"
            f"{branch_text}"
            f"────────────────────────\n"
            f"📢 *OFFICIAL FEE PAYMENT REMINDER*\n\n"
            f"Dear Parent, Greetings! 🙏\n"
            f"This is a gentle reminder regarding the installment fee for:\n\n"
            f"🎓 *Student Name:* *{student_name}*\n"
            + (f"🆔 *Student ID:* *{student_code}*\n" if student_code else "")
            + (f"📋 *Roll Number:* *{roll_number}*\n" if roll_number else "")
            + (f"📚 *Class / Course:* *{standard}*\n" if standard else "")
            + (f"📅 *Academic Session:* *{session_name}*\n" if session_name else "")
            + f"\n💰 *FEE BALANCE SUMMARY:*\n"
            f"• 📚 Current Session Pending: *₹{format_currency_inr(curr)}*\n"
            f"• ⏳ Prior Session Dues: *Nil (Fully Cleared) ✅*\n"
            f"────────────────────────\n"
            f"🧾 *NET DUE AMOUNT: ₹{format_currency_inr(curr)}*\n"
            f"{due_str}"
            f"────────────────────────\n\n"
            f"💳 *Payment Options:*\n"
            f"1. Center Office (Cash / Cheque / Card)\n"
            f"2. Online UPI Transfer (Contact center office for official QR code)\n\n"
            f"Kindly clear the due installment at your earliest convenience. Thank you for your continued cooperation!\n\n"
            f"Warm Regards,\n"
            f"*{institute} Accounts*\n"
            f"{helpline_text}"
        )

    # CASE 4: PRIOR YEAR DUES PENDING ONLY
    return (
        f"🏛️ *{institute}*\n"
        f"{branch_text}"
        f"────────────────────────\n"
        f"📢 *OFFICIAL FEE PAYMENT REMINDER*\n\n"
        f"Dear Parent, Greetings! 🙏\n"
        f"This is a reminder regarding the carried-forward academic dues for:\n\n"
        f"🎓 *Student Name:* *{student_name}*\n"
        + (f"🆔 *Student ID:* *{student_code}*\n" if student_code else "")
        + (f"📋 *Roll Number:* *{roll_number}*\n" if roll_number else "")
        + (f"📚 *Class / Course:* *{standard}*\n" if standard else "")
        + f"\n💰 *FEE BALANCE BREAKDOWN:*\n"
        f"• 📚 Current Session: *Paid in Full (Nil) ✅*\n"
        f"• ⏳ Prior Session Carried Dues: *₹{format_currency_inr(prior)}*\n"
        f"────────────────────────\n"
        f"🧾 *TOTAL OUTSTANDING TO CLEAR: ₹{format_currency_inr(prior)}*\n"
        f"────────────────────────\n\n"
        f"Kindly arrange to settle the carried-forward balance at the center office or via UPI at your earliest convenience.\n\n"
        f"Warm Regards,\n"
        f"*{institute} Accounts*\n"
        f"{helpline_text}"
    )


def build_admission_whatsapp_message(
    institute_name: str = 'Sutawane Classes',
    student_name: str = '',
    student_code: str = '',
    roll_number: str = '',
    standard: str = '',
    session_name: str = '',
    branch_name: str = '',
    total_fees: float = 0.0,
    helpline: str = ''
) -> str:
    """
    Template for New Admission Confirmation WhatsApp Message.
    """
    institute = (institute_name or 'Sutawane Classes').upper()
    branch_text = f"📍 *Branch:* {branch_name}\n" if branch_name else ""
    helpline_text = f"📞 *Helpline / Office:* {helpline}" if helpline else ""

    return (
        f"🏛️ *{institute}*\n"
        f"{branch_text}"
        f"────────────────────────\n"
        f"🎉 *CONGRATULATIONS & WELCOME!* 🌟\n\n"
        f"Dear Parent, Greetings! 🙏\n"
        f"We are delighted to confirm that the admission for *{student_name}* has been officially registered!\n\n"
        f"📋 *ADMISSION DETAILS:*\n"
        f"• 🎓 *Student Name:* *{student_name}*\n"
        + (f"• 🆔 *Student ID:* *{student_code}*\n" if student_code else "")
        + (f"• 🏷️ *Roll Number:* *{roll_number}*\n" if roll_number else "")
        + (f"• 📚 *Class / Course:* *{standard}*\n" if standard else "")
        + (f"• 📅 *Academic Session:* *{session_name}*\n" if session_name else "")
        + (f"• 🏢 *Center / Branch:* *{branch_name}*\n" if branch_name else "")
        + f"• 💰 *Annual Session Fee:* *₹{format_currency_inr(total_fees)}*\n"
        f"────────────────────────\n\n"
        f"We extend a warm welcome to {student_name} and look forward to an academic year of dedication and excellence! 🏆\n\n"
        f"Warm Regards,\n"
        f"*{institute} Administration*\n"
        f"{helpline_text}"
    )


def build_general_notice_whatsapp_message(
    institute_name: str = 'Sutawane Classes',
    student_name: str = '',
    roll_number: str = '',
    standard: str = '',
    branch_name: str = '',
    helpline: str = ''
) -> str:
    """
    Template for General Parent Notice / Greetings.
    """
    institute = (institute_name or 'Sutawane Classes').upper()
    branch_text = f"📍 *Branch:* {branch_name}\n" if branch_name else ""
    helpline_text = f"📞 *Helpline:* {helpline}" if helpline else ""

    return (
        f"🏛️ *{institute}*\n"
        f"{branch_text}"
        f"────────────────────────\n"
        f"Dear Parent, Greetings from *{institute}*! 🙏\n\n"
        f"Regarding student: *{student_name}* "
        + (f"(Roll No: *{roll_number}*, " if roll_number else "(")
        + f"Course: *{standard or 'General'}*).\n\n"
        f"Please let us know if you require any academic updates, fee receipts, or attendance support.\n\n"
        f"Warm Regards,\n"
        f"*{institute} Office*\n"
        f"{helpline_text}"
    )


# -----------------------------------------------------------------------------
# Central Notification Dispatch Engine (Local Bridge + Logging)
# -----------------------------------------------------------------------------

import json
import urllib.request
import urllib.error


def deduct_whatsapp_credit() -> int:
    """
    Atomically decrements whatsapp_credits_balance by 1 and increments whatsapp_messages_sent_count by 1.
    Returns the remaining balance after deduction.
    """
    from .models import SystemSetting
    from .context_processors import invalidate_global_context_cache
    from django.db import transaction

    try:
        with transaction.atomic():
            setting, _ = SystemSetting.objects.get_or_create(
                key='whatsapp_credits_balance',
                defaults={'value': '500'}
            )
            try:
                curr_bal = int(setting.value or 0)
            except (ValueError, TypeError):
                curr_bal = 0
            new_bal = max(0, curr_bal - 1)
            setting.value = str(new_bal)
            setting.save(update_fields=['value'])

            sent_setting, _ = SystemSetting.objects.get_or_create(
                key='whatsapp_messages_sent_count',
                defaults={'value': '0'}
            )
            try:
                curr_sent = int(sent_setting.value or 0)
            except (ValueError, TypeError):
                curr_sent = 0
            sent_setting.value = str(curr_sent + 1)
            sent_setting.save(update_fields=['value'])

        invalidate_global_context_cache()
        return new_bal
    except Exception as exc:
        return None


def dispatch_whatsapp_message(
    recipient: str,
    message: str,
    message_type: str = 'CUSTOM',
    recipient_name: str = 'Parent',
    entity_id: str = '',
    sent_by: str = 'System',
    force_provider: str = None
) -> dict:
    """
    Central dispatcher for sending WhatsApp messages via the configured provider
    (Local WhatsApp Bridge on http://localhost:3000/send, or Simulator).
    Enforces prepaid message quota balance and deducts 1 credit per successfully sent message.
    Records audit entry in NotificationLog.
    Never crashes or interrupts main business transaction.
    """
    from .models import NotificationLog, SystemSetting
    from .context_processors import get_cached_settings_dict

    settings_map = get_cached_settings_dict()
    is_enabled = settings_map.get('whatsapp_enabled', 'true') != 'false'
    provider = force_provider or settings_map.get('whatsapp_provider', 'LOCAL_WHATSAPP')
    endpoint = (settings_map.get('whatsapp_endpoint') or 'http://localhost:3000/send').strip()

    norm_phone = format_whatsapp_number(recipient)

    if not is_enabled and message_type != 'SYSTEM_TEST':
        return {'success': False, 'status': 'DISABLED', 'error': 'WhatsApp notifications are disabled in settings. Enable "Service Active" to dispatch notifications.'}

    # Quota Balance Verification (Fresh from DB to prevent cache lag)
    quota_enforced = settings_map.get('whatsapp_credits_enforced', 'true') != 'false'
    bal_setting = SystemSetting.objects.filter(key='whatsapp_credits_balance').first()
    try:
        current_balance = int(bal_setting.value if bal_setting and bal_setting.value is not None else settings_map.get('whatsapp_credits_balance', 500))
    except (ValueError, TypeError):
        current_balance = 500

    if quota_enforced and current_balance <= 0:
        rate_display = settings_map.get('whatsapp_rate_per_message', '0.40')
        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone or recipient or 'UNKNOWN',
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='FAILED',
            response_payload=f'Dispatch blocked: WhatsApp Message Quota Exhausted (0 balance). Rate: ₹{rate_display}/msg. Please contact software administrator to recharge credits.',
            entity_id=entity_id,
            provider=provider,
            sent_by=sent_by
        )
        return {
            'success': False,
            'status': 'QUOTA_EXHAUSTED',
            'error': 'WhatsApp message quota exhausted (0 credits remaining). Please contact software provider to recharge credits.',
            'log_id': log.id
        }

    if not norm_phone or len(norm_phone) < 10:
        log = NotificationLog.objects.create(
            recipient_mobile=recipient or 'UNKNOWN',
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='FAILED',
            response_payload='Invalid mobile number format (must be 10-digit Indian mobile).',
            entity_id=entity_id,
            provider=provider,
            sent_by=sent_by
        )
        return {'success': False, 'status': 'FAILED', 'error': 'Invalid phone number', 'log_id': log.id}

    if provider == 'SIMULATOR':
        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone,
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='SIMULATED',
            response_payload='Successfully simulated in test/development mode without gateway charges.',
            entity_id=entity_id,
            provider=provider,
            sent_by=sent_by
        )
    # META_OFFICIAL: Official WhatsApp Cloud API (Graph API)
    if provider == 'META_OFFICIAL':
        meta_phone_id = (settings_map.get('whatsapp_meta_phone_id') or '').strip()
        meta_token = (settings_map.get('whatsapp_meta_access_token') or '').strip()
        meta_version = (settings_map.get('whatsapp_meta_api_version') or 'v21.0').strip() or 'v21.0'

        if not meta_phone_id or not meta_token:
            err_msg = 'Official WhatsApp Cloud API requires Phone Number ID and Permanent Access Token in Settings.'
            log = NotificationLog.objects.create(
                recipient_mobile=norm_phone,
                recipient_name=recipient_name or 'Parent',
                message_type=message_type,
                message_text=message,
                status='FAILED',
                response_payload=err_msg,
                entity_id=entity_id,
                provider=provider,
                sent_by=sent_by
            )
            return {'success': False, 'status': 'FAILED', 'error': err_msg, 'log_id': log.id}

        meta_url = f"https://graph.facebook.com/{meta_version}/{meta_phone_id}/messages"
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": norm_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                meta_url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {meta_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                resp_body = response.read().decode('utf-8')
                resp_data = json.loads(resp_body) if resp_body else {}

            remaining_after = None
            if quota_enforced:
                remaining_after = deduct_whatsapp_credit()

            log = NotificationLog.objects.create(
                recipient_mobile=norm_phone,
                recipient_name=recipient_name or 'Parent',
                message_type=message_type,
                message_text=message,
                status='SENT',
                response_payload=resp_body,
                entity_id=entity_id,
                provider=provider,
                sent_by=sent_by
            )
            return {
                'success': True,
                'status': 'SENT',
                'log_id': log.id,
                'response': resp_data,
                'remaining_credits': remaining_after
            }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8') if e.fp else str(e)
            try:
                err_json = json.loads(err_body)
                err_detail = err_json.get('error', {}).get('message', err_body)
            except Exception:
                err_detail = err_body
            log = NotificationLog.objects.create(
                recipient_mobile=norm_phone,
                recipient_name=recipient_name or 'Parent',
                message_type=message_type,
                message_text=message,
                status='FAILED',
                response_payload=f"Meta Graph API HTTP {e.code}: {err_detail}",
                entity_id=entity_id,
                provider=provider,
                sent_by=sent_by
            )
            return {'success': False, 'status': 'FAILED', 'error': f"Meta API Error: {err_detail}", 'log_id': log.id}
        except Exception as ex:
            log = NotificationLog.objects.create(
                recipient_mobile=norm_phone,
                recipient_name=recipient_name or 'Parent',
                message_type=message_type,
                message_text=message,
                status='FAILED',
                response_payload=f"Meta API Connection Error: {str(ex)}",
                entity_id=entity_id,
                provider=provider,
                sent_by=sent_by
            )
            return {'success': False, 'status': 'FAILED', 'error': str(ex), 'log_id': log.id}

    # LOCAL_WHATSAPP Gateway (Node bridge at http://localhost:3000/send)
    try:
        payload = json.dumps({
            "to": norm_phone,
            "message": message
        }).encode('utf-8')

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=12) as response:
            resp_body = response.read().decode('utf-8')
            resp_data = json.loads(resp_body) if resp_body else {}

        # Successfully delivered: Deduct 1 message credit if quota enforced
        remaining_after = None
        if quota_enforced:
            remaining_after = deduct_whatsapp_credit()

        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone,
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='SENT',
            response_payload=resp_body,
            entity_id=entity_id,
            provider='LOCAL_WHATSAPP',
            sent_by=sent_by
        )
        return {
            'success': True,
            'status': 'SENT',
            'log_id': log.id,
            'response': resp_data,
            'remaining_credits': remaining_after
        }

    except urllib.error.HTTPError as err:
        try:
            body = err.read().decode('utf-8')
            data = json.loads(body)
            err_msg = data.get('error') or f"Gateway Error (HTTP {err.code})"
        except Exception:
            err_msg = f"Gateway Error (HTTP {err.code}: {err.reason})"

        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone,
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='FAILED',
            response_payload=f"HTTPError {err.code}: {err_msg}",
            entity_id=entity_id,
            provider='LOCAL_WHATSAPP',
            sent_by=sent_by
        )
        return {'success': False, 'status': 'FAILED', 'error': err_msg, 'log_id': log.id}

    except urllib.error.URLError as err:
        err_msg = str(err)
        if "refused" in err_msg.lower() or "10061" in err_msg:
            err_msg = "Local WhatsApp Bridge is not running on port 3000. Please start 'start_whatsapp_bridge.bat'."
        
        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone,
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='FAILED',
            response_payload=f"URLError: {err_msg}",
            entity_id=entity_id,
            provider='LOCAL_WHATSAPP',
            sent_by=sent_by
        )
        return {'success': False, 'status': 'FAILED', 'error': err_msg, 'log_id': log.id}

    except Exception as exc:
        log = NotificationLog.objects.create(
            recipient_mobile=norm_phone,
            recipient_name=recipient_name or 'Parent',
            message_type=message_type,
            message_text=message,
            status='FAILED',
            response_payload=f"Exception: {str(exc)}",
            entity_id=entity_id,
            provider='LOCAL_WHATSAPP',
            sent_by=sent_by
        )
        return {'success': False, 'status': 'FAILED', 'error': str(exc), 'log_id': log.id}

