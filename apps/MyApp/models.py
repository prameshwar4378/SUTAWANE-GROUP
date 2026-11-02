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


class NotificationLog(models.Model):
    """
    Audit log of all SMS / WhatsApp messages dispatched to parents and students.
    """
    MESSAGE_TYPE_CHOICES = [
        ('PAYMENT_RECEIPT', 'Payment Receipt'),
        ('FEE_REMINDER', 'Fee Reminder'),
        ('ADMISSION_NOTICE', 'Admission Confirmation'),
        ('SYSTEM_TEST', 'Gateway Test Ping'),
        ('CUSTOM', 'Custom Message'),
    ]

    STATUS_CHOICES = [
        ('SENT', 'Sent Successfully'),
        ('FAILED', 'Failed'),
        ('SIMULATED', 'Simulated / Logged'),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    recipient_mobile = models.CharField(max_length=50)
    recipient_name = models.CharField(max_length=150, default='Parent')
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPE_CHOICES, default='CUSTOM')
    message_text = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='SENT')
    response_payload = models.TextField(null=True, blank=True)
    entity_id = models.CharField(max_length=100, null=True, blank=True)
    provider = models.CharField(max_length=50, default='LOCAL_WHATSAPP')
    sent_by = models.CharField(max_length=150, default='System')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'NotificationLog'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at:%d-%b %H:%M}] {self.recipient_mobile} ({self.status})"


# -------------------------------------------------------------
# Authentication & User Accounts (DEVELOPER, CLASS_OWNER, BRANCH_MANAGER)
# -------------------------------------------------------------

class User(models.Model):
    ROLE_CHOICES = (
        ('DEVELOPER', 'Software Developer'),
        ('CLASS_OWNER', 'Class Owner (Admin)'),
        ('BRANCH_MANAGER', 'Branch Manager'),
    )

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    username = models.CharField(unique=True, max_length=150)
    password = models.CharField(max_length=255)  # Salted PBKDF2 hash
    salt = models.CharField(max_length=255)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='CLASS_OWNER')
    branch = models.ForeignKey('Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='managers', db_column='branchId', help_text='Assigned operational branch for Branch Manager')
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
        branch_str = f" @ {self.branch.name}" if self.branch else ""
        return f"{self.name} ({self.username}) [{self.role}{branch_str}]"

    @property
    def is_developer(self):
        return self.role == 'DEVELOPER'

    @property
    def is_class_owner(self):
        return self.role == 'CLASS_OWNER'

    @property
    def is_branch_manager(self):
        return self.role == 'BRANCH_MANAGER'


class RolePermission(models.Model):
    """
    Role & User specific permissions configuration.
    Can store default permissions for BRANCH_MANAGER, or per-user overrides.
    """
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    role = models.CharField(max_length=50, choices=User.ROLE_CHOICES, default='BRANCH_MANAGER', db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_permissions')

    # Students Directory & Admissions
    can_view_students = models.BooleanField(default=True)
    can_add_students = models.BooleanField(default=True)
    can_edit_students = models.BooleanField(default=True)
    can_delete_students = models.BooleanField(default=False)
    can_promote_students = models.BooleanField(default=False)

    # Fees, Receipts & Dues
    can_collect_fees = models.BooleanField(default=True)
    can_void_receipts = models.BooleanField(default=False)
    can_view_dues = models.BooleanField(default=True)
    can_send_fee_reminders = models.BooleanField(default=True)

    # Expenses Management
    can_view_expenses = models.BooleanField(default=True)
    can_add_expenses = models.BooleanField(default=True)
    can_delete_expenses = models.BooleanField(default=False)

    # Reports & Analytics
    can_view_reports = models.BooleanField(default=True)
    can_view_daily_reports = models.BooleanField(default=True)
    can_export_reports = models.BooleanField(default=True)

    # Classes, Courses & Sessions
    can_manage_courses = models.BooleanField(default=False)
    can_manage_sessions = models.BooleanField(default=False)

    # Security & Data Isolation
    restricted_to_assigned_branch = models.BooleanField(default=True)
    can_access_backup = models.BooleanField(default=False)
    can_access_settings = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'RolePermission'

    def __str__(self):
        target = f"User: {self.user.username}" if self.user else f"Default for {self.role}"
        return f"Permissions ({target})"


# -------------------------------------------------------------
# Core Entities: Branches & Academic Sessions
# -------------------------------------------------------------

class Branch(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(unique=True, max_length=150)
    class_name = models.CharField(max_length=200, null=True, blank=True, db_column='className')
    code = models.CharField(unique=True, max_length=50)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.CharField(max_length=150, null=True, blank=True)
    tagline = models.CharField(max_length=255, null=True, blank=True)
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

    def get_display_name(self):
        return self.class_name or self.name


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
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_fee_plans', db_column='createdById', help_text='User who configured the agreed fee plan')
    updated_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_fee_plans', db_column='updatedById', help_text='User who last modified the fee plan')
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

    def save(self, *args, **kwargs):
        from .middleware import get_current_authenticated_user
        current_u = get_current_authenticated_user()
        is_new = not self.pk or not FeePlan.objects.filter(pk=self.pk).exists()
        if is_new:
            if not self.created_by and current_u:
                self.created_by = current_u
        else:
            if current_u:
                self.updated_by = current_u
        super().save(*args, **kwargs)


class FeeDiscount(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    fee_plan = models.ForeignKey(FeePlan, on_delete=models.CASCADE, related_name='discounts', db_column='feePlanId')
    reason = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    approved_date = models.DateTimeField(default=timezone.now, db_column='approvedDate')
    notes = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_discounts', db_column='createdById', help_text='User who granted/authorized this discount')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'FeeDiscount'
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name='fee_discount_amount_non_negative'),
        ]

    def __str__(self):
        return f"Discount ₹{self.amount} ({self.reason})"

    def save(self, *args, **kwargs):
        from .middleware import get_current_authenticated_user
        current_u = get_current_authenticated_user()
        if not self.pk or not FeeDiscount.objects.filter(pk=self.pk).exists():
            if not self.created_by and current_u:
                self.created_by = current_u
        super().save(*args, **kwargs)


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

    @property
    def pending_amount(self):
        return max(Decimal('0.00'), (self.outstanding_amount or Decimal('0.00')) - (self.collected_amount or Decimal('0.00')))

    @property
    def is_cleared(self):
        return self.pending_amount <= Decimal('0.00')

    @property
    def status(self):
        if self.is_cleared:
            return 'PAID'
        if (self.collected_amount or Decimal('0.00')) > Decimal('0.00'):
            return 'PARTIAL'
        return 'PENDING'

    @property
    def clearance_pct(self):
        if not self.outstanding_amount or self.outstanding_amount <= Decimal('0.00'):
            return 100.0
        return round(float((self.collected_amount or Decimal('0.00')) / self.outstanding_amount * 100), 1)


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
    received_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_payments', db_column='receivedById', help_text='Staff/User who collected/received this fee payment')
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payments', db_column='createdById', help_text='User who initiated the payment record')
    updated_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_payments', db_column='updatedById', help_text='User who last updated this payment')
    reversed_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='reversed_payments', db_column='reversedById', help_text='User who voided/reversed this payment')
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
            models.Index(fields=['received_by']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='payment_total_non_negative'),
        ]

    def __str__(self):
        return f"Receipt #{self.receipt_number} - ₹{self.total_amount} ({self.student.full_name})"

    @property
    def received_by_display(self):
        if self.received_by:
            return self.received_by.name
        if self.created_by:
            return self.created_by.name
        return "Staff"

    @property
    def received_by_role_display(self):
        if self.received_by:
            return self.received_by.get_role_display()
        if self.created_by:
            return self.created_by.get_role_display()
        return "Staff"

    @property
    def reversed_by_display(self):
        if self.reversed_by:
            return self.reversed_by.name
        return "Administrator"

    def save(self, *args, **kwargs):
        from .middleware import get_current_authenticated_user
        current_u = get_current_authenticated_user()
        is_new = not self.pk or not Payment.objects.filter(pk=self.pk).exists()

        if is_new:
            if not self.received_by and current_u:
                self.received_by = current_u
            if not self.created_by and current_u:
                self.created_by = current_u
        else:
            if current_u:
                self.updated_by = current_u
            if self.is_reversed and not self.reversed_by and current_u:
                self.reversed_by = current_u

        super().save(*args, **kwargs)


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
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_expenses', db_column='createdById', help_text='User who recorded this expense')
    updated_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_expenses', db_column='updatedById', help_text='User who last updated this expense')
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
            models.Index(fields=['created_by']),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name='expense_amount_non_negative'),
        ]

    def __str__(self):
        return f"Expense: ₹{self.amount} - {self.category.name} ({self.description[:30]})"

    @property
    def created_by_display(self):
        if self.created_by:
            return self.created_by.name or self.created_by.username or "Staff"
        return "Staff"

    @property
    def created_by_role_display(self):
        if self.created_by:
            return self.created_by.get_role_display()
        return "Staff"

    @property
    def updated_by_display(self):
        if self.updated_by:
            return self.updated_by.name or self.updated_by.username or "Staff"
        return None

    def save(self, *args, **kwargs):
        from .middleware import get_current_authenticated_user
        current_u = get_current_authenticated_user()
        is_new = not self.pk or not Expense.objects.filter(pk=self.pk).exists()
        if is_new:
            if not self.created_by and current_u:
                self.created_by = current_u
        else:
            if current_u:
                self.updated_by = current_u
        super().save(*args, **kwargs)


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


# =============================================================
# Website Inquiries & Lead Follow-Up Management
# =============================================================

class WebsiteInquiry(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'New Lead'),
        ('CONTACTED', 'Contacted / Spoke to Parent'),
        ('FOLLOW_UP', 'Follow-up Scheduled'),
        ('DEMO_SCHEDULED', '3-Day Demo Scheduled'),
        ('CONVERTED', 'Converted (Reference Only)'),
        ('CLOSED', 'Closed / Not Interested'),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    inquiry_number = models.CharField(max_length=30, unique=True, db_column='inquiryNumber')
    student_name = models.CharField(max_length=200, db_column='studentName')
    parent_name = models.CharField(max_length=200, null=True, blank=True, db_column='parentName')
    phone = models.CharField(max_length=50)
    email = models.CharField(max_length=150, null=True, blank=True)
    standard_course = models.CharField(max_length=150, db_column='standardCourse')
    preferred_branch = models.CharField(max_length=150, null=True, blank=True, db_column='preferredBranch')
    message = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='NEW', db_index=True)
    next_followup_date = models.DateField(null=True, blank=True, db_column='nextFollowupDate')
    assigned_staff_name = models.CharField(max_length=150, null=True, blank=True, db_column='assignedStaffName')
    is_converted = models.BooleanField(default=False, db_column='isConverted')
    converted_note = models.CharField(max_length=255, null=True, blank=True, db_column='convertedNote')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsiteInquiry'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.inquiry_number} - {self.student_name}"


class InquiryFollowUp(models.Model):
    CONTACT_METHODS = [
        ('PHONE_CALL', 'Phone Call'),
        ('WHATSAPP', 'WhatsApp Message'),
        ('CAMPUS_VISIT', 'In-Person Campus Visit'),
        ('SMS', 'SMS Alert'),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    inquiry = models.ForeignKey(WebsiteInquiry, on_delete=models.CASCADE, related_name='followups', db_column='inquiryId')
    contact_method = models.CharField(max_length=30, choices=CONTACT_METHODS, default='PHONE_CALL', db_column='contactMethod')
    notes = models.TextField()
    status_after = models.CharField(max_length=30, db_column='statusAfter')
    next_followup_date = models.DateField(null=True, blank=True, db_column='nextFollowupDate')
    recorded_by_name = models.CharField(max_length=150, default='Website System', db_column='recordedByName')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'InquiryFollowUp'
        ordering = ['-created_at']

    def __str__(self):
        return f"FollowUp on {self.inquiry.student_name} ({self.created_at.strftime('%d-%m-%Y')})"

    @property
    def recorded_by_display(self):
        return self.recorded_by_name or "Staff"


# =============================================================
# Selective Dynamic Website Management Models
# =============================================================

class WebsiteBanner(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    page = models.CharField(max_length=50, default='ALL')
    badge_text = models.CharField(max_length=120, default='🔥 ADMISSIONS OPEN 2026–27', db_column='badgeText')
    main_text = models.CharField(max_length=255, default='New Batches Starting Soon · Limited 30 Seats / Batch', db_column='mainText')
    action_url = models.CharField(max_length=255, default='#demoModal', db_column='actionUrl')
    cta_text = models.CharField(max_length=80, default='Book Free Demo', db_column='ctaText')
    detail_text = models.TextField(blank=True, default='', db_column='detailText')
    secondary_url = models.CharField(max_length=255, blank=True, default='/batches/', db_column='secondaryUrl')
    secondary_text = models.CharField(max_length=80, blank=True, default='Explore Batches', db_column='secondaryText')
    is_expandable = models.BooleanField(default=True, db_column='isExpandable')
    is_active = models.BooleanField(default=True, db_column='isActive')
    highlights = models.JSONField(default=list, blank=True, db_column='highlights')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    DEFAULT_HIGHLIGHTS = [
        {"icon": "📅", "title": "Academic Session", "value": "Batches 2026–27 Open", "color": "indigo"},
        {"icon": "🏆", "title": "Scholarship Test", "value": "Up to 100% Fee Waiver", "color": "amber"},
        {"icon": "👥", "title": "Batch Capacity", "value": "Strictly 30 Seats/Batch", "color": "purple"},
        {"icon": "📞", "title": "Counseling Helpline", "value": "+91 98814 65883", "color": "rose"}
    ]

    def get_highlights(self):
        if isinstance(self.highlights, list) and len(self.highlights) > 0:
            return self.highlights
        return self.DEFAULT_HIGHLIGHTS

    def get_highlight_cards_for_admin(self):
        items = [dict(c) for c in self.get_highlights()]
        while len(items) < 4:
            items.append({"icon": "📌", "title": "", "value": "", "color": "indigo"})
        return items[:4]

    @property
    def highlight_1(self):
        return self.get_highlight_cards_for_admin()[0]

    @property
    def highlight_2(self):
        return self.get_highlight_cards_for_admin()[1]

    @property
    def highlight_3(self):
        return self.get_highlight_cards_for_admin()[2]

    @property
    def highlight_4(self):
        return self.get_highlight_cards_for_admin()[3]

    class Meta:
        db_table = 'WebsiteBanner'

    def __str__(self):
        return f"{self.badge_text} - {self.main_text[:40]}"


class WebsiteNotification(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Rich HTML content with styling, lists, bold, italics, colors")
    is_active = models.BooleanField(default=True, db_column='isActive')
    is_pinned = models.BooleanField(default=False, db_column='isPinned')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsiteNotification'
        ordering = ['-is_pinned', 'sort_order', '-created_at']

    def __str__(self):
        return self.title


class WebsiteNotificationDocument(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    notification = models.ForeignKey(WebsiteNotification, on_delete=models.CASCADE, related_name='documents', db_column='notificationId')
    file = models.FileField(upload_to='website_notifications/docs/')
    file_name = models.CharField(max_length=255, db_column='fileName')
    file_size = models.CharField(max_length=50, blank=True, null=True, db_column='fileSize')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'WebsiteNotificationDocument'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.file_name} ({self.notification.title})"


class WebsiteTopper(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    student_name = models.CharField(max_length=150, db_column='studentName')
    exam_stream = models.CharField(max_length=150, db_column='examStream')
    score_text = models.CharField(max_length=100, db_column='scoreText')
    score_icon = models.CharField(max_length=20, default='⚡', db_column='scoreIcon')
    achievement_badge = models.CharField(max_length=200, db_column='achievementBadge')
    quote = models.TextField(blank=True, null=True)
    photo_url = models.CharField(max_length=500, blank=True, null=True, db_column='photoUrl')
    avatar_initials = models.CharField(max_length=10, default='ST', db_column='avatarInitials')
    avatar_color = models.CharField(max_length=30, default='avatar-blue', db_column='avatarColor')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsiteTopper'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f"{self.student_name} ({self.score_text})"


class WebsiteBatchCard(models.Model):
    CATEGORY_CHOICES = [
        ('science', '11th & 12th Science'),
        ('entrance', 'MHT-CET / NEET Target'),
        ('foundation', '8th–10th State Board'),
        ('commerce', 'Commerce Stream'),
    ]

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='science')
    stream_tag = models.CharField(max_length=120, db_column='streamTag')
    seats_badge = models.CharField(max_length=100, default='Seats Available', db_column='seatsBadge')
    target_text = models.CharField(max_length=200, db_column='targetText')
    features = models.TextField(help_text="Newline-separated list of bullet points")
    timing_text = models.CharField(max_length=200, db_column='timingText')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    is_active = models.BooleanField(default=True, db_column='isActive')
    is_featured = models.BooleanField(default=False, db_column='isFeatured')
    featured_tag = models.CharField(max_length=120, blank=True, default='', db_column='featuredTag')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsiteBatchCard'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title

    def get_features_list(self):
        return [f.strip() for f in self.features.split('\n') if f.strip()]


class WebsiteGalleryCategory(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'WebsiteGalleryCategory'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            import re
            base = re.sub(r'[^a-zA-Z0-9]+', '-', self.name.lower()).strip('-')
            self.slug = base or f"cat-{self.id[:8]}"
        super().save(*args, **kwargs)


class WebsiteGalleryItem(models.Model):
    TYPE_CHOICES = [('IMAGE', 'Photo'), ('VIDEO', 'Video')]

    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    title = models.CharField(max_length=200)
    media_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='IMAGE', db_column='mediaType')
    category = models.CharField(max_length=100, default='Campus Infrastructure')
    category_ref = models.ForeignKey(WebsiteGalleryCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='gallery_items', db_column='categoryId')
    file_url = models.CharField(max_length=500, db_column='fileUrl')
    thumbnail_url = models.CharField(max_length=500, blank=True, null=True, db_column='thumbnailUrl')
    caption = models.TextField(blank=True, null=True)
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')

    class Meta:
        db_table = 'WebsiteGalleryItem'
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f"[{self.category}] {self.title}"

    @property
    def category_display(self):
        cat_map = {
            'CAMPUS': 'Campus Infrastructure',
            'TOPPERS': 'Topper Felicitation',
            'LABS': 'Science Labs & Classrooms',
            'EVENTS': 'Workshops & Seminars',
        }
        if self.category_ref:
            return self.category_ref.name
        return cat_map.get(self.category, self.category)

    @property
    def category_slug(self):
        import re
        if self.category_ref and self.category_ref.slug:
            return self.category_ref.slug
        cat_map = {
            'CAMPUS': 'campus-infrastructure',
            'TOPPERS': 'topper-felicitation',
            'LABS': 'science-labs-classrooms',
            'EVENTS': 'workshops-seminars',
        }
        if self.category in cat_map:
            return cat_map[self.category]
        disp = self.category_display or 'general'
        return re.sub(r'[^a-zA-Z0-9]+', '-', disp.lower()).strip('-') or 'general'

    @property
    def youtube_id(self):
        if self.media_type == 'VIDEO' and self.file_url:
            import re
            m = re.search(r'(?:youtube\.com\/(?:watch\?.*v=|embed\/|shorts\/|v\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', self.file_url)
            if m:
                return m.group(1)
        return None

    @property
    def effective_watch_url(self):
        yid = self.youtube_id
        if yid:
            return f"https://www.youtube.com/watch?v={yid}"
        return self.file_url

    @property
    def effective_thumbnail_url(self):
        if self.thumbnail_url:
            return self.thumbnail_url
        yid = self.youtube_id
        if yid:
            return f"https://img.youtube.com/vi/{yid}/hqdefault.jpg"
        return self.file_url or '/static/images/default-course.png'

    @property
    def effective_embed_url(self):
        yid = self.youtube_id
        if yid:
            return f"https://www.youtube.com/embed/{yid}?autoplay=1&rel=0&enablejsapi=1"
        return self.file_url

    def save(self, *args, **kwargs):
        # Auto-normalize YouTube video file_url to official YouTube watch URL
        if self.media_type == 'VIDEO' and self.file_url:
            import re
            m = re.search(r'(?:youtube\.com\/(?:watch\?.*v=|embed\/|shorts\/|v\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', self.file_url)
            if m:
                vid_id = m.group(1)
                self.file_url = f"https://www.youtube.com/watch?v={vid_id}"
                if not self.thumbnail_url or 'youtube.com' in self.thumbnail_url or 'ytimg.com' in self.thumbnail_url:
                    self.thumbnail_url = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
        super().save(*args, **kwargs)


class WebsitePageMeta(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    page_key = models.CharField(max_length=50, unique=True, db_column='pageKey')
    page_name = models.CharField(max_length=100, db_column='pageName')
    meta_title = models.CharField(max_length=255, db_column='metaTitle')
    meta_desc = models.TextField(db_column='metaDesc')
    meta_keywords = models.TextField(db_column='metaKeywords')
    og_title = models.CharField(max_length=255, blank=True, null=True, db_column='ogTitle')
    og_desc = models.TextField(blank=True, null=True, db_column='ogDesc')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsitePageMeta'

    def __str__(self):
        return self.page_name


class WebsiteCampus(models.Model):
    """
    Dedicated, completely independent Website Campus model.
    Contains marketing campus directory, maps, and timings for the public website.
    100% separate from internal software Branch table.
    """
    id = models.CharField(primary_key=True, max_length=36, default=generate_uuid, editable=False)
    campus_key = models.CharField(max_length=50, unique=True, db_column='campusKey')
    name = models.CharField(max_length=150)
    badge = models.CharField(max_length=150, default='Branch Campus')
    icon = models.CharField(max_length=20, default='🏛️')
    person_name = models.CharField(max_length=150, default='Prof. Sutawane Sir', db_column='personName')
    person_role = models.CharField(max_length=150, default='Academic Director & Faculty Lead', db_column='personRole')
    address = models.CharField(max_length=255)
    district = models.CharField(max_length=150)
    phone = models.CharField(max_length=50, default='+91 98814 65883')
    phone_raw = models.CharField(max_length=50, default='9881465883', db_column='phoneRaw')
    hours = models.CharField(max_length=150, default='Monday to Saturday: 7:30 AM – 8:00 PM')
    hours_sub = models.CharField(max_length=150, default='Sunday: 8:00 AM – 1:00 PM', db_column='hoursSub')
    map_heading = models.CharField(max_length=200, default='Find Our Campus', db_column='mapHeading')
    map_subdesc = models.TextField(blank=True, null=True, db_column='mapSubdesc')
    map_embed_url = models.TextField(blank=True, null=True, db_column='mapEmbedUrl')
    map_direct_url = models.TextField(blank=True, null=True, db_column='mapDirectUrl')
    sort_order = models.IntegerField(default=0, db_column='sortOrder')
    is_active = models.BooleanField(default=True, db_column='isActive')
    created_at = models.DateTimeField(default=timezone.now, db_column='createdAt')
    updated_at = models.DateTimeField(auto_now=True, db_column='updatedAt')

    class Meta:
        db_table = 'WebsiteCampus'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    @property
    def mentor_initials(self):
        raw = (self.person_name or '').strip()
        if not raw:
            return 'SC'
        parts = [p for p in raw.replace('.', ' ').split() if p]
        if not parts:
            return 'SC'
        if parts[0].lower() in ('prof', 'dr', 'mr', 'mrs', 'ms', 'shri') and len(parts) >= 2:
            first = parts[1][0]
            second = parts[2][0] if len(parts) > 2 else (parts[1][1] if len(parts[1]) > 1 else '')
            return (first + second).upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def phone_clean(self):
        digits = ''.join(c for c in (self.phone or '') if c.isdigit())
        if digits.startswith('91') and len(digits) > 10:
            return f"+{digits}"
        elif len(digits) == 10:
            return f"+91{digits}"
        return self.phone or '+919881465883'

    @property
    def phone_whatsapp(self):
        digits = ''.join(c for c in (self.phone or '') if c.isdigit())
        if len(digits) >= 10:
            if digits.startswith('91') and len(digits) == 12:
                return digits
            return f"91{digits[-10:]}"
        return '919881465883'

    def save(self, *args, **kwargs):
        if self.phone:
            clean_digits = ''.join(ch for ch in self.phone if ch.isdigit())
            if clean_digits:
                self.phone_raw = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits
        if not self.map_heading and self.name:
            self.map_heading = f"Find Our {self.name}"
        if not self.map_subdesc and self.address:
            self.map_subdesc = f"Located on {self.address}{f', {self.district}' if self.district else ''}. Peaceful, secure, and accessible learning environment."
        super().save(*args, **kwargs)
        try:
            from .context_processors import invalidate_global_context_cache
            invalidate_global_context_cache()
        except Exception:
            pass



