import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator


def generate_uuid():
    return str(uuid.uuid4())


# -------------------------------------------------------------
# System Settings & Diagnostics
# -------------------------------------------------------------

class SystemSetting(models.Model):
    key = models.CharField(primary_key=True, max_length=150)
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'SystemSetting'

    def __str__(self):
        return f"{self.key}: {self.value}"


class HealthLog(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    status = models.CharField(max_length=50)
    details = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'HealthLog'

    def __str__(self):
        return f"[{self.created_at}] Status: {self.status}"


# -------------------------------------------------------------
# Authentication & User Accounts (CLASS_OWNER & DEVELOPER)
# -------------------------------------------------------------

class User(models.Model):
    ROLE_CHOICES = (
        ('CLASS_OWNER', 'Class Owner (Admin)'),
        ('DEVELOPER', 'Software Developer'),
    )

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    username = models.CharField(unique=True, max_length=150)
    password = models.CharField(max_length=255)  # Salted PBKDF2 hash
    salt = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='CLASS_OWNER')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'User'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.name} ({self.username}) [{self.role}]"

    @property
    def is_developer(self):
        return self.role == 'DEVELOPER'

    @property
    def is_class_owner(self):
        return self.role == 'CLASS_OWNER'


# -------------------------------------------------------------
# Core Entities: Branches & Academic Sessions
# -------------------------------------------------------------

class Branch(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(unique=True, max_length=150)
    code = models.CharField(unique=True, max_length=50)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    contact_person = models.CharField(max_length=150, null=True, blank=True, db_column='contactPerson')
    logo_url = models.CharField(max_length=500, null=True, blank=True, db_column='logoUrl')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Branch'
        indexes = [
            models.Index(fields=['is_active', 'name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class AcademicSession(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(unique=True, max_length=50)  # e.g. "2026-27"
    display_name = models.CharField(max_length=150, db_column='displayName')  # e.g. "Academic Year 2026–27"
    start_date = models.DateTimeField(db_column='startDate')
    end_date = models.DateTimeField(db_column='endDate')
    is_current = models.BooleanField(default=False, db_column='isCurrent')
    isActive = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'AcademicSession'
        indexes = [
            models.Index(fields=['isActive', 'start_date']),
            models.Index(fields=['is_current']),
        ]

    def __str__(self):
        return self.display_name or self.name


# -------------------------------------------------------------
# Dynamic Courses & Classes Management
# -------------------------------------------------------------

class Course(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(unique=True, max_length=150)
    code = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    default_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), null=True, blank=True, db_column='defaultFee', validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True, db_column='isActive')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Course'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_active', 'sort_order']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(default_fee__gte=0), name='course_default_fee_non_negative'),
        ]

    def __str__(self):
        return self.name


# -------------------------------------------------------------
# Student Profiles & Session-Scoped Admissions
# -------------------------------------------------------------

class Student(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    student_code = models.CharField(unique=True, max_length=50, db_column='studentCode')  # SC-2026-0001
    full_name = models.CharField(max_length=200, db_column='fullName')
    parent_phone = models.CharField(max_length=50, db_column='parentPhone')
    student_phone = models.CharField(max_length=50, null=True, blank=True, db_column='studentPhone')
    address = models.TextField(null=True, blank=True)
    photo_url = models.CharField(max_length=500, null=True, blank=True, db_column='photoUrl')
    date_of_birth = models.DateTimeField(null=True, blank=True, db_column='dateOfBirth')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Student'
        indexes = [
            models.Index(fields=['full_name']),
            models.Index(fields=['parent_phone']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.student_code})"


class StudentAdmission(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    student = models.ForeignKey(Student, on_delete=models.RESTRICT, related_name='admissions', db_column='studentId')
    branch = models.ForeignKey(Branch, on_delete=models.RESTRICT, related_name='admissions', db_column='branchId')
    session = models.ForeignKey(AcademicSession, on_delete=models.RESTRICT, related_name='admissions', db_column='sessionId')
    roll_number = models.CharField(max_length=50, db_column='rollNumber')
    standard = models.CharField(max_length=150)
    admission_date = models.DateTimeField(default=timezone.now, db_column='admissionDate')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'StudentAdmission'
        unique_together = (
            ('student', 'session'),
            ('branch', 'session', 'roll_number'),
        )
        indexes = [
            models.Index(fields=['branch']),
            models.Index(fields=['session']),
            models.Index(fields=['standard']),
            models.Index(fields=['is_active']),
            models.Index(fields=['roll_number']),
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['branch', 'session', 'is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.standard} (Roll: {self.roll_number})"


# -------------------------------------------------------------
# Installment Fee Architecture & Payment Accounting
# -------------------------------------------------------------

class FeePlan(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    admission = models.OneToOneField(StudentAdmission, on_delete=models.CASCADE, related_name='fee_plan', db_column='admissionId')
    session = models.ForeignKey(AcademicSession, on_delete=models.RESTRICT, related_name='fee_plans', db_column='sessionId')
    total_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), db_column='totalFees', validators=[MinValueValidator(0)])
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), db_column='totalDiscount', validators=[MinValueValidator(0)])
    net_payable = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), db_column='netPayable', validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'FeePlan'
        indexes = [
            models.Index(fields=['session']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total_fees__gte=0), name='fee_plan_total_fees_non_negative'),
            models.CheckConstraint(condition=models.Q(total_discount__gte=0), name='fee_plan_total_discount_non_negative'),
            models.CheckConstraint(condition=models.Q(net_payable__gte=0), name='fee_plan_net_payable_non_negative'),
        ]

    def __str__(self):
        return f"FeePlan: {self.admission} - Net: ₹{self.net_payable}"


class FeeDiscount(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    fee_plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name='discounts', db_column='feePlanId')
    reason = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    approved_date = models.DateTimeField(default=timezone.now, db_column='approvedDate')
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'FeeDiscount'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name='fee_discount_amount_non_negative'),
        ]

    def __str__(self):
        return f"Discount ₹{self.amount} ({self.reason})"


class Installment(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    fee_plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name='installments', db_column='feePlanId')
    installment_no = models.IntegerField(db_column='installmentNo')
    label = models.CharField(max_length=100)
    due_date = models.DateTimeField(db_column='dueDate')
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, db_column='amountDue', validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Installment'
        indexes = [
            models.Index(fields=['due_date']),
            models.Index(fields=['fee_plan', 'installment_no']),
            models.Index(fields=['fee_plan', 'due_date']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_due__gte=0), name='installment_amount_non_negative'),
        ]

    def __str__(self):
        return f"{self.label}: ₹{self.amount_due} due {self.due_date.strftime('%Y-%m-%d')}"

    @property
    def paid_amount(self):
        return sum(alloc.allocated_amount for alloc in self.allocations.filter(payment__is_reversed=False))

    @property
    def pending_amount(self):
        return max(Decimal('0.00'), self.amount_due - self.paid_amount)

    @property
    def status(self):
        due = self.amount_due or Decimal('0.00')
        paid = self.paid_amount or Decimal('0.00')
        bal = max(Decimal('0.00'), due - paid)
        if bal <= 0:
            return 'PAID'
        if paid > 0 and paid < due:
            return 'PARTIAL'
        if not self.due_date:
            return 'UPCOMING'
        today = timezone.localdate()
        due_d = timezone.localtime(self.due_date).date() if timezone.is_aware(self.due_date) else self.due_date.date()
        if today > due_d:
            return 'OVERDUE'
        if today == due_d:
            return 'DUE'
        return 'UPCOMING'


class PreviousSessionDue(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    student = models.ForeignKey(Student, on_delete=models.RESTRICT, related_name='previous_dues', db_column='studentId')
    original_session = models.ForeignKey(AcademicSession, on_delete=models.RESTRICT, related_name='original_dues', db_column='originalSessionId')
    current_session = models.ForeignKey(AcademicSession, on_delete=models.RESTRICT, related_name='current_dues', db_column='currentSessionId')
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, db_column='outstandingAmount', validators=[MinValueValidator(0)])
    collected_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), db_column='collectedAmount', validators=[MinValueValidator(0)])
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'PreviousSessionDue'
        indexes = [
            models.Index(fields=['student']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(outstanding_amount__gte=0), name='previous_due_outstanding_non_negative'),
            models.CheckConstraint(condition=models.Q(collected_amount__gte=0), name='previous_due_collected_non_negative'),
        ]

    def __str__(self):
        return f"Previous Due: {self.student.full_name} - Outstanding: ₹{self.outstanding_amount}"


class Payment(models.Model):
    PAYMENT_MODE_CHOICES = (
        ('CASH', 'Cash'),
        ('UPI', 'UPI / QR Code'),
        ('BANK_TRANSFER', 'Bank Transfer / NEFT / IMPS'),
        ('CHEQUE', 'Cheque / DD'),
        ('OTHER', 'Other'),
    )

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    student = models.ForeignKey(Student, on_delete=models.RESTRICT, related_name='payments', db_column='studentId')
    branch = models.ForeignKey(Branch, on_delete=models.RESTRICT, related_name='payments', db_column='branchId')
    admission = models.ForeignKey(StudentAdmission, on_delete=models.RESTRICT, null=True, blank=True, related_name='payments', db_column='admissionId')
    session = models.ForeignKey(AcademicSession, on_delete=models.RESTRICT, null=True, blank=True, related_name='payments', db_column='sessionId')
    previous_due = models.ForeignKey(PreviousSessionDue, on_delete=models.RESTRICT, null=True, blank=True, related_name='payments', db_column='previousDueId')
    receipt_number = models.CharField(unique=True, max_length=100, db_column='receiptNumber')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, db_column='totalAmount', validators=[MinValueValidator(0)])
    payment_date = models.DateTimeField(default=timezone.now, db_column='paymentDate')
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, db_column='paymentMode')
    reference_number = models.CharField(max_length=100, null=True, blank=True, db_column='referenceNumber')
    notes = models.TextField(null=True, blank=True)
    is_reversed = models.BooleanField(default=False, db_column='isReversed')
    reversal_reason = models.TextField(null=True, blank=True, db_column='reversalReason')
    reversed_at = models.DateTimeField(null=True, blank=True, db_column='reversedAt')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Payment'
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['branch']),
            models.Index(fields=['admission']),
            models.Index(fields=['session']),
            models.Index(fields=['previous_due']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['is_reversed']),
            models.Index(fields=['is_reversed', 'payment_date']),
            models.Index(fields=['session', 'is_reversed', 'payment_date']),
            models.Index(fields=['branch', 'is_reversed', 'payment_date']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='payment_total_non_negative'),
        ]

    def __str__(self):
        return f"Receipt #{self.receipt_number} - ₹{self.total_amount} ({self.student.full_name})"


class PaymentAllocation(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='allocations', db_column='paymentId')
    installment = models.ForeignKey(Installment, on_delete=models.RESTRICT, related_name='allocations', db_column='installmentId')
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, db_column='allocatedAmount', validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'PaymentAllocation'
        indexes = [
            models.Index(fields=['payment']),
            models.Index(fields=['installment']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(allocated_amount__gte=0), name='payment_allocation_non_negative'),
        ]

    def __str__(self):
        return f"Alloc: ₹{self.allocated_amount} to {self.installment.label}"


class ReceiptCounter(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='receipt_counters', db_column='branchId')
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='receipt_counters', db_column='sessionId')
    prefix = models.CharField(max_length=100)  # e.g. "2026-27-VAI-REC"
    last_number = models.IntegerField(default=0, db_column='lastNumber')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'ReceiptCounter'
        unique_together = ('branch', 'session')

    def __str__(self):
        return f"{self.prefix}{self.last_number}"


# -------------------------------------------------------------
# Expense Architecture & Category Taxonomy
# -------------------------------------------------------------

class ExpenseCategory(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(unique=True, max_length=150)
    is_active = models.BooleanField(default=True, db_column='isActive')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')

    class Meta:
        db_table = 'ExpenseCategory'
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
        ]

    def __str__(self):
        return self.name


class Expense(models.Model):
    PAYMENT_MODE_CHOICES = (
        ('CASH', 'Cash'),
        ('UPI', 'UPI / QR Code'),
        ('BANK_TRANSFER', 'Bank Transfer / NEFT / IMPS'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    )

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.RESTRICT, related_name='expenses', db_column='branchId')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.RESTRICT, related_name='expenses', db_column='categoryId')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    expense_date = models.DateTimeField(default=timezone.now, db_column='expenseDate')
    description = models.TextField()
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, db_column='paymentMode')
    vendor = models.CharField(max_length=200, null=True, blank=True)
    reference_number = models.CharField(max_length=100, null=True, blank=True, db_column='referenceNumber')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'Expense'
        indexes = [
            models.Index(fields=['branch']),
            models.Index(fields=['category']),
            models.Index(fields=['expense_date']),
            models.Index(fields=['branch', 'expense_date']),
            models.Index(fields=['category', 'expense_date']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name='expense_amount_non_negative'),
        ]

    def __str__(self):
        return f"Expense: ₹{self.amount} - {self.category.name} ({self.description[:30]})"


class ExpenseAttachment(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='attachments', db_column='expenseId')
    file_name = models.CharField(max_length=255, db_column='fileName')
    file_path = models.CharField(max_length=500, db_column='filePath')
    file_size = models.IntegerField(db_column='fileSize')
    mime_type = models.CharField(max_length=100, db_column='mimeType')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'ExpenseAttachment'

    def __str__(self):
        return self.file_name
