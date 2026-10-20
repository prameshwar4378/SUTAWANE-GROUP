import os
import django
import sys
import io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apps'))
django.setup()

from django.test import Client
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from datetime import datetime, timedelta
from MyApp.models import (
    Branch, AcademicSession, User, Expense, ExpenseCategory, ExpenseAttachment
)

TEST_TAG = "TEST_STEP12_OVERHEAD"

def cleanup_step12_artifacts():
    # Remove test expenses and test files
    for exp in Expense.objects.filter(description__icontains=TEST_TAG):
        for att in exp.attachments.all():
            if att.file_path and att.file_path.startswith('/media/'):
                disk_rel = att.file_path[len('/media/'):]
                disk_full = os.path.join(settings.MEDIA_ROOT, disk_rel)
                try:
                    if os.path.exists(disk_full):
                        os.remove(disk_full)
                except Exception:
                    pass
        exp.delete()

    # Remove any test category created
    ExpenseCategory.objects.filter(name='Test Step12 Refreshments').delete()

cleanup_step12_artifacts()

client = Client()

print("=" * 70)
print("RUNNING STEP 12 AUTOMATED VERIFICATION SUITE")
print("EXPENSE MANAGEMENT, BILL ATTACHMENTS & FINANCIAL AUDIT")
print("=" * 70)

# 1. Authenticate Class Owner
print("\n--- 1. Authenticating as Class Owner ---")
login_res = client.post('/login/', {'username': 'sutawane', 'password': 'sutawane@123'})
assert login_res.status_code == 302
branch = Branch.objects.filter(is_active=True).first()
today = timezone.localtime().date()
print(f"Owner authenticated! Active Branch: '{branch.name}', Date: {today}")

# 2. Testing Initial GET /expenses/
print("\n--- 2. Testing GET /expenses/ (Page Load & Headers) ---")
res_initial = client.get('/expenses/')
assert res_initial.status_code == 200
html_initial = res_initial.content.decode('utf-8')
assert 'Branch Expense & Overheads Management' in html_initial
assert 'Recorded Vouchers' in html_initial
assert 'Filtered Expenses' in html_initial
assert 'Top Category' in html_initial
assert 'UPI & Online' in html_initial
assert 'Cash & Bank Wire' in html_initial
print("Initial /expenses/ page rendered with all 5 KPI summary card slots!")

# 3. Recording Expense Vouchers via POST action='create'
print("\n--- 3. Recording Expense Vouchers (POST action='create') ---")
cat_rent = ExpenseCategory.objects.filter(name='Rent').first() or ExpenseCategory.objects.create(name='Rent')
cat_elec = ExpenseCategory.objects.filter(name='Electricity').first() or ExpenseCategory.objects.create(name='Electricity')
cat_stat = ExpenseCategory.objects.filter(name='Stationery').first() or ExpenseCategory.objects.create(name='Stationery')

# Expense 1: Rent (Bank Transfer)
res_exp1 = client.post('/expenses/', {
    'action': 'create',
    'description': f'{TEST_TAG} Center Main Hall Rent for Oct 2026',
    'amount': '25000',
    'category_id': cat_rent.id,
    'branch_id': branch.id,
    'payment_mode': 'BANK_TRANSFER',
    'vendor': 'Landlord Shri V. K. Deshmukh',
    'reference_number': 'NEFT-88991122',
    'expense_date': today.strftime('%Y-%m-%d'),
})
assert res_exp1.status_code == 302
exp1 = Expense.objects.filter(description__icontains='Center Main Hall Rent').first()
assert exp1 is not None and exp1.amount == 25000.0 and exp1.payment_mode == 'BANK_TRANSFER'
print("Expense 1 recorded: Rent ₹25,000 via BANK_TRANSFER!")

# Expense 2: Electricity (UPI)
res_exp2 = client.post('/expenses/', {
    'action': 'create',
    'description': f'{TEST_TAG} MSEB Center Electricity Meter #4901',
    'amount': '4850',
    'category_id': cat_elec.id,
    'branch_id': branch.id,
    'payment_mode': 'UPI',
    'vendor': 'MSEB Power Corp',
    'reference_number': 'UPI-774411',
    'expense_date': today.strftime('%Y-%m-%d'),
})
assert res_exp2.status_code == 302
exp2 = Expense.objects.filter(description__icontains='MSEB Center Electricity').first()
assert exp2 is not None and exp2.amount == 4850.0 and exp2.payment_mode == 'UPI'
print("Expense 2 recorded: Electricity ₹4,850 via UPI!")

# Expense 3: Stationery (Cash)
res_exp3 = client.post('/expenses/', {
    'action': 'create',
    'description': f'{TEST_TAG} A4 Printing Paper Reams & Whiteboard Markers',
    'amount': '1500',
    'category_id': cat_stat.id,
    'branch_id': branch.id,
    'payment_mode': 'CASH',
    'vendor': 'Navneet Stationery Mart',
    'reference_number': 'BILL-849',
    'expense_date': today.strftime('%Y-%m-%d'),
})
assert res_exp3.status_code == 302
exp3 = Expense.objects.filter(description__icontains='A4 Printing Paper').first()
assert exp3 is not None and exp3.amount == 1500.0 and exp3.payment_mode == 'CASH'
print("Expense 3 recorded: Stationery ₹1,500 via CASH!")

# Expense 4: Auto-create New Category on-the-fly
res_exp4 = client.post('/expenses/', {
    'action': 'create',
    'description': f'{TEST_TAG} Faculty & Staff Tea Refreshments',
    'amount': '650',
    'category_id': '__NEW__',
    'new_category_name': 'Test Step12 Refreshments',
    'branch_id': branch.id,
    'payment_mode': 'UPI',
    'vendor': 'Sharma Canteen',
    'reference_number': 'UPI-TEA-101',
    'expense_date': today.strftime('%Y-%m-%d'),
})
assert res_exp4.status_code == 302
new_cat = ExpenseCategory.objects.filter(name='Test Step12 Refreshments').first()
assert new_cat is not None
exp4 = Expense.objects.filter(description__icontains='Faculty & Staff Tea').first()
assert exp4 is not None and exp4.category == new_cat
print("Expense 4 recorded: New category 'Test Step12 Refreshments' created dynamically on-the-fly!")

# 4. Expense with File Attachment Upload
print("\n--- 4. Testing File Attachment Upload & Persistence ---")
fake_image_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
uploaded_file = SimpleUploadedFile("sample_receipt_voucher.png", fake_image_content, content_type="image/png")

res_exp5 = client.post('/expenses/', {
    'action': 'create',
    'description': f'{TEST_TAG} Newspaper & Social Media Admission Banner Ads',
    'amount': '12000',
    'category_id': ExpenseCategory.objects.filter(name='Marketing').first().id if ExpenseCategory.objects.filter(name='Marketing').exists() else cat_rent.id,
    'branch_id': branch.id,
    'payment_mode': 'UPI',
    'vendor': 'Navbharat Publicity Agency',
    'reference_number': 'ADV-OCT-9901',
    'expense_date': today.strftime('%Y-%m-%d'),
    'attachment': uploaded_file,
})
assert res_exp5.status_code == 302
exp5 = Expense.objects.filter(description__icontains='Admission Banner Ads').first()
assert exp5 is not None and exp5.amount == 12000.0
assert exp5.attachments.count() == 1
att = exp5.attachments.first()
assert att.file_name == 'sample_receipt_voucher.png'
assert 'attachments/' in att.file_path
# Verify file exists on physical disk
disk_rel = att.file_path[len('/media/'):]
disk_full = os.path.join(settings.MEDIA_ROOT, disk_rel)
assert os.path.exists(disk_full), f"Attached file does not exist at {disk_full}"
print(f"File attachment persisted to disk at '{disk_rel}' ({os.path.getsize(disk_full)} bytes)!")

# 5. Testing GET /expenses/ Live KPI Aggregations & Category Breakdown
print("\n--- 5. Testing GET /expenses/ Live KPI Cards & Category Pills ---")
res_ledger = client.get('/expenses/')
assert res_ledger.status_code == 200
html_ledger = res_ledger.content.decode('utf-8')

# Verify 5 KPIs
# Total count >= 5
assert 'Center Main Hall Rent' in html_ledger
assert 'MSEB Center Electricity' in html_ledger
assert 'A4 Printing Paper' in html_ledger
assert 'Faculty' in html_ledger and 'Staff Tea' in html_ledger
assert 'Admission Banner Ads' in html_ledger
assert 'Bill Scan' in html_ledger

# Verify Category Breakdown pill
assert 'Test Step12 Refreshments' in html_ledger
print("All 5 recorded expense vouchers, Bill Scan button, and category pills verified!")

# 6. Testing Category & Payment Mode Filters
print("\n--- 6. Testing Filters (?category_id=, ?payment_mode=, ?date_preset=, ?q=) ---")
# Category filter (Rent)
res_filter_cat = client.get(f'/expenses/?category_id={cat_rent.id}')
assert res_filter_cat.status_code == 200
html_cat = res_filter_cat.content.decode('utf-8')
assert 'Center Main Hall Rent' in html_cat
assert 'MSEB Center Electricity' not in html_cat
print("Category filter (?category_id=Rent) verified: strictly isolates Rent expenses!")

# Payment mode filter (UPI)
res_filter_upi = client.get('/expenses/?payment_mode=UPI')
assert res_filter_upi.status_code == 200
html_upi = res_filter_upi.content.decode('utf-8')
assert 'MSEB Center Electricity' in html_upi
assert 'Admission Banner Ads' in html_upi
assert 'Center Main Hall Rent' not in html_upi
print("Payment Mode filter (?payment_mode=UPI) verified: strictly isolates UPI payments!")

# Date preset filter (TODAY)
res_filter_today = client.get('/expenses/?date_preset=TODAY')
assert res_filter_today.status_code == 200
assert 'MSEB Center Electricity' in res_filter_today.content.decode('utf-8')
print("Date preset (?date_preset=TODAY) verified!")

# Multi-token live search
res_search = client.get('/expenses/?q=MSEB+Meter')
assert res_search.status_code == 200
html_search = res_search.content.decode('utf-8')
assert 'MSEB Center Electricity' in html_search
assert 'Center Main Hall Rent' not in html_search
print("Multi-token search (?q=MSEB+Meter) verified!")

# 7. Testing HTMX Partial Rendering (HTTP_HX_REQUEST)
print("\n--- 7. Testing HTMX Partial Table Swap ---")
res_htmx = client.get('/expenses/?q=Stationery', HTTP_HX_REQUEST='true')
assert res_htmx.status_code == 200
html_htmx = res_htmx.content.decode('utf-8')
assert '<table' in html_htmx
assert 'A4 Printing Paper' in html_htmx
assert '<!DOCTYPE html>' not in html_htmx
print("HTMX partial swap verified: returns standalone table partial without full page shell!")

# 8. Testing Expense Update (POST action='update')
print("\n--- 8. Testing Expense Update (POST action='update') ---")
res_update = client.post('/expenses/', {
    'action': 'update',
    'expense_id': exp3.id,
    'description': f'{TEST_TAG} Exam Papers, Register Diaries & Stationery Updated',
    'amount': '1850',
    'category_id': cat_stat.id,
    'branch_id': branch.id,
    'payment_mode': 'CASH',
    'vendor': 'Navneet Stationery Mart & Printers',
    'reference_number': 'BILL-849-REV',
    'expense_date': today.strftime('%Y-%m-%d'),
})
assert res_update.status_code == 302
exp3.refresh_from_db()
assert exp3.amount == 1850.0
assert 'Exam Papers, Register Diaries' in exp3.description
assert exp3.reference_number == 'BILL-849-REV'
print(f"Expense voucher #{exp3.id[:8]} updated to ₹1,850 and new description saved!")

# 9. Testing Excel Export (?export=excel)
print("\n--- 9. Testing Excel (.xlsx) Export ---")
res_excel = client.get('/expenses/?export=excel')
assert res_excel.status_code == 200
assert res_excel['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
assert '.xlsx' in res_excel['Content-Disposition']
assert len(res_excel.content) > 1000
print(f"Excel export verified: generated valid workbook ({len(res_excel.content)} bytes)!")

# 10. Testing Landscape A4 PDF Export (?export=pdf)
print("\n--- 10. Testing Landscape A4 PDF (.pdf) Export ---")
res_pdf = client.get('/expenses/?export=pdf')
assert res_pdf.status_code == 200
assert res_pdf['Content-Type'] == 'application/pdf'
assert '.pdf' in res_pdf['Content-Disposition']
assert res_pdf.content.startswith(b'%PDF')
assert len(res_pdf.content) > 1000
print(f"PDF export verified: generated valid Landscape A4 PDF ({len(res_pdf.content)} bytes)!")

# 11. Testing Expense Voucher Deletion with Disk Cleanup (POST action='delete')
print("\n--- 11. Testing Deletion & Attachment Disk Cleanup ---")
exp5_id = exp5.id
assert os.path.exists(disk_full)
res_del = client.post('/expenses/', {
    'action': 'delete',
    'expense_id': exp5_id,
})
assert res_del.status_code == 302
assert not Expense.objects.filter(id=exp5_id).exists()
assert not os.path.exists(disk_full), f"File {disk_full} should have been deleted from disk!"
print("Expense voucher deleted and linked file scan on disk cleaned up cleanly!")

# 12. Cleanup remaining test records
print("\n--- 12. Cleanup Test Artifacts ---")
cleanup_step12_artifacts()
print("Cleaned up test expenses cleanly.")

print("\n" + "=" * 70)
print("ALL STEP 12 TESTS PASSED (100% SUCCESS)")
print("=" * 70)
