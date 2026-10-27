import random
import time
import uuid
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from MyApp.models import (
    Branch,
    AcademicSession,
    Student,
    StudentAdmission,
    Payment,
    Expense,
    ExpenseCategory,
    NotificationLog,
)

FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh', 'Ayaan', 'Krishna', 'Ishaan',
    'Shaurya', 'Atharva', 'Advik', 'Pranav', 'Advaith', 'Aaryan', 'Dhruv', 'Kabir', 'Ritvik', 'Darsh',
    'Saanvi', 'Aanya', 'Aadhya', 'Aaradhya', 'Ananya', 'Pari', 'Anika', 'Navya', 'Angel', 'Diya',
    'Myra', 'Sara', 'Ira', 'Avani', 'Riya', 'Prisha', 'Aditi', 'Kiara', 'Kavya', 'Siya',
    'Rohan', 'Sneha', 'Tanvi', 'Om', 'Sagar', 'Akshay', 'Pooja', 'Pooja', 'Neha', 'Pratik'
]

LAST_NAMES = [
    'Sharma', 'Verma', 'Patil', 'Deshmukh', 'Jadhav', 'Pawar', 'Kulkarni', 'Shinde', 'Chavan', 'More',
    'Gaikwad', 'Bhosale', 'Kadam', 'Sawant', 'Mane', 'Kamble', 'Kale', 'Gore', 'Sutawane', 'Tambe',
    'Rathod', 'Giri', 'Thakur', 'Bangar', 'Suryavanshi', 'Chaudhari', 'Patel', 'Shah', 'Mehta', 'Gupta'
]

STANDARDS = [
    '8th Foundation', '9th Foundation', '10th Board State', '10th Board CBSE',
    '11th - CET', '11th - NEET', '11th - JEE Main',
    '12th - CET', '12th - NEET', '12th - JEE Advanced',
    'Repeaters Batch - NEET', 'Crash Course'
]

PAYMENT_MODES = ['UPI', 'CASH', 'BANK_TRANSFER', 'CHEQUE']


class Command(BaseCommand):
    help = 'High-Speed Stress Testing Data Generator (Generates 1 Lakh dummy records for performance benchmarking)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--model',
            type=str,
            default='notifications',
            choices=['notifications', 'students', 'expenses', 'payments'],
            help='Model to populate: notifications, students, expenses, or payments (default: notifications)'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=100000,
            help='Number of dummy records to create (default: 100000 = 1 Lakh)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear dummy stress-test records previously created'
        )

    def handle(self, *args, **options):
        model_name = options['model']
        count = options['count']
        clear_only = options['clear']

        if clear_only:
            self.clear_data(model_name)
            return

        self.stdout.write(self.style.NOTICE(f"\n[START] Starting High-Performance Stress Data Generation"))
        self.stdout.write(f"Target Model: {model_name.upper()}")
        self.stdout.write(f"Record Count: {count:,} records\n")

        start_time = time.time()

        if model_name == 'notifications':
            self.generate_notifications(count)
        elif model_name == 'students':
            self.generate_students(count)
        elif model_name == 'expenses':
            self.generate_expenses(count)
        elif model_name == 'payments':
            self.generate_payments(count)

        elapsed = time.time() - start_time
        rate = count / max(0.001, elapsed)
        self.stdout.write(self.style.SUCCESS(
            f"\n[SUCCESS] Generated {count:,} records in {elapsed:.2f} seconds ({rate:,.0f} records/sec)!\n"
        ))

    def clear_data(self, model_name):
        self.stdout.write(self.style.WARNING(f"Cleaning up dummy stress-test records for {model_name}..."))
        if model_name == 'notifications':
            deleted, _ = NotificationLog.objects.filter(sent_by='STRESS_TEST_SUITE').delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted:,} stress-test notification logs."))
        elif model_name == 'students':
            stress_students = Student.objects.filter(student_code__startswith='STRESS-')
            adm_deleted, _ = StudentAdmission.objects.filter(student__in=stress_students).delete()
            deleted, _ = stress_students.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted:,} students and {adm_deleted:,} admissions."))
        elif model_name == 'expenses':
            deleted, _ = Expense.objects.filter(vendor__startswith='STRESS_VENDOR_').delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted:,} stress-test expenses."))
        elif model_name == 'payments':
            deleted, _ = Payment.objects.filter(receipt_number__startswith='STRESS-REC-').delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted:,} stress-test payments."))

    def generate_notifications(self, total_count):
        batch_size = 5000
        types = ['PAYMENT_RECEIPT', 'FEE_REMINDER', 'ADMISSION_NOTICE', 'SYSTEM_TEST', 'CUSTOM']
        statuses = ['SENT', 'SENT', 'SENT', 'FAILED', 'SIMULATED']
        now = timezone.now()

        created_so_far = 0
        while created_so_far < total_count:
            current_batch = min(batch_size, total_count - created_so_far)
            records = []
            for _ in range(current_batch):
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                phone = f"91{random.randint(7000000000, 9999999999)}"
                mtype = random.choice(types)
                stat = random.choice(statuses)
                random_days = random.randint(0, 180)
                random_time = now - timedelta(days=random_days, minutes=random.randint(0, 1440))

                records.append(NotificationLog(
                    id=str(uuid.uuid4()),
                    recipient_mobile=phone,
                    recipient_name=f"{fn} {ln}",
                    message_type=mtype,
                    message_text=f"Dear Parent, this is an automated official alert from Sutawane Classes for student {fn} {ln}.",
                    status=stat,
                    response_payload='{"status": "delivered", "messageId": "msg_' + str(uuid.uuid4())[:8] + '"}',
                    provider='LOCAL_WHATSAPP',
                    sent_by='STRESS_TEST_SUITE',
                    created_at=random_time
                ))

            with transaction.atomic():
                NotificationLog.objects.bulk_create(records, batch_size=current_batch)

            created_so_far += current_batch
            pct = (created_so_far / total_count) * 100
            self.stdout.write(f"  [Progress] {created_so_far:,} / {total_count:,} NotificationLogs created ({pct:.1f}%)...")

    def generate_students(self, total_count):
        branch = Branch.objects.filter(is_active=True).first() or Branch.objects.first()
        session = AcademicSession.objects.filter(is_current=True).first() or AcademicSession.objects.first()

        if not branch or not session:
            self.stderr.write(self.style.ERROR("Error: Academic session or Branch missing. Please seed basic setup first."))
            return

        batch_size = 2500
        now = timezone.now()
        created_so_far = 0

        # We need a starting index to guarantee uniqueness of student_code and roll_number
        base_num = int(time.time()) % 1000000

        while created_so_far < total_count:
            current_batch = min(batch_size, total_count - created_so_far)
            students = []
            student_meta = []

            for i in range(current_batch):
                idx = created_so_far + i + 1
                uid = str(uuid.uuid4())
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                code = f"STRESS-SC-{base_num:06d}-{idx:06d}"
                roll = f"STR-{(base_num % 1000):03d}-{idx:06d}"
                std = random.choice(STANDARDS)

                s = Student(
                    id=uid,
                    student_code=code,
                    full_name=f"{fn} {ln}",
                    parent_phone=f"91{random.randint(7000000000, 9999999999)}",
                    student_phone=f"91{random.randint(7000000000, 9999999999)}",
                    address=f"Plot No. {random.randint(1, 999)}, Kopargaon Road, Maharashtra",
                    created_at=now - timedelta(days=random.randint(1, 365))
                )
                students.append(s)
                student_meta.append((uid, roll, std))

            with transaction.atomic():
                Student.objects.bulk_create(students, batch_size=current_batch)

                admissions = [
                    StudentAdmission(
                        id=str(uuid.uuid4()),
                        student_id=uid,
                        branch=branch,
                        session=session,
                        roll_number=roll,
                        standard=std,
                        admission_date=now,
                        is_active=True,
                        created_at=now
                    )
                    for uid, roll, std in student_meta
                ]
                StudentAdmission.objects.bulk_create(admissions, batch_size=current_batch)

            created_so_far += current_batch
            pct = (created_so_far / total_count) * 100
            self.stdout.write(f"  [Progress] {created_so_far:,} / {total_count:,} Students & Admissions created ({pct:.1f}%)...")

    def generate_expenses(self, total_count):
        branch = Branch.objects.filter(is_active=True).first() or Branch.objects.first()
        category = ExpenseCategory.objects.filter(is_active=True).first() or ExpenseCategory.objects.first()

        if not branch or not category:
            self.stderr.write(self.style.ERROR("Error: Branch or ExpenseCategory missing."))
            return

        batch_size = 5000
        now = timezone.now()
        created_so_far = 0

        while created_so_far < total_count:
            current_batch = min(batch_size, total_count - created_so_far)
            records = []
            for i in range(current_batch):
                idx = created_so_far + i + 1
                amt = Decimal(random.randint(200, 45000))
                mode = random.choice(PAYMENT_MODES)
                d = now - timedelta(days=random.randint(0, 365))

                records.append(Expense(
                    id=str(uuid.uuid4()),
                    branch=branch,
                    category=category,
                    amount=amt,
                    expense_date=d,
                    description=f"Automated benchmark expense transaction #{idx:,} for operational supply audit",
                    payment_mode=mode,
                    vendor=f"STRESS_VENDOR_{random.randint(1, 500)}",
                    reference_number=f"EXP-REF-{random.randint(100000, 999999)}",
                    created_at=d
                ))

            with transaction.atomic():
                Expense.objects.bulk_create(records, batch_size=current_batch)

            created_so_far += current_batch
            pct = (created_so_far / total_count) * 100
            self.stdout.write(f"  [Progress] {created_so_far:,} / {total_count:,} Expenses created ({pct:.1f}%)...")

    def generate_payments(self, total_count):
        student = Student.objects.first()
        branch = Branch.objects.first()
        session = AcademicSession.objects.first()

        if not student or not branch or not session:
            self.stderr.write(self.style.ERROR("Error: Prerequisite student/branch/session records missing."))
            return

        batch_size = 5000
        now = timezone.now()
        created_so_far = 0
        base_time = int(time.time()) % 1000000

        while created_so_far < total_count:
            current_batch = min(batch_size, total_count - created_so_far)
            records = []
            for i in range(current_batch):
                idx = created_so_far + i + 1
                amt = Decimal(random.randint(1000, 25000))
                mode = random.choice(PAYMENT_MODES)
                d = now - timedelta(days=random.randint(0, 365))

                records.append(Payment(
                    id=str(uuid.uuid4()),
                    student=student,
                    branch=branch,
                    session=session,
                    receipt_number=f"STRESS-REC-{base_time:06d}-{idx:06d}",
                    total_amount=amt,
                    payment_date=d,
                    payment_mode=mode,
                    reference_number=f"UPI-{random.randint(100000000000, 999999999999)}",
                    notes="Benchmark payment transaction",
                    is_reversed=False,
                    created_at=d
                ))

            with transaction.atomic():
                Payment.objects.bulk_create(records, batch_size=current_batch)

            created_so_far += current_batch
            pct = (created_so_far / total_count) * 100
            self.stdout.write(f"  [Progress] {created_so_far:,} / {total_count:,} Payments created ({pct:.1f}%)...")
