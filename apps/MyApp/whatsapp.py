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
