from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .auth_utils import AUTHORIZED_DEVELOPER_EMAIL, generate_and_send_developer_otp, verify_developer_otp
from .models import WebsiteGalleryCategory, WebsiteGalleryItem


class PublicGalleryCategoryVisibilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat_campus = WebsiteGalleryCategory.objects.create(
            name='Campus Infrastructure',
            slug='campus-infrastructure',
            sort_order=1,
            is_active=True,
        )
        self.cat_toppers = WebsiteGalleryCategory.objects.create(
            name='Topper Felicitation',
            slug='topper-felicitation',
            sort_order=2,
            is_active=True,
        )
        self.cat_workshops = WebsiteGalleryCategory.objects.create(
            name='Workshops & Seminars 123',
            slug='workshops-seminars-123',
            sort_order=3,
            is_active=True,
        )
        self.cat_indoor = WebsiteGalleryCategory.objects.create(
            name='Indoor',
            slug='indoor',
            sort_order=4,
            is_active=True,
        )

    def test_photo_gallery_hides_categories_without_active_photos(self):
        WebsiteGalleryItem.objects.create(
            title='Sports Ground',
            media_type='IMAGE',
            category=self.cat_campus.name,
            category_ref=self.cat_campus,
            file_url='/media/website/gallery/photos/sports.png',
            is_active=True,
        )
        # Inactive photo in Topper Felicitation should not make category visible
        WebsiteGalleryItem.objects.create(
            title='Hidden Topper Photo',
            media_type='IMAGE',
            category=self.cat_toppers.name,
            category_ref=self.cat_toppers,
            file_url='/media/website/gallery/photos/hidden.png',
            is_active=False,
        )
        # Video in Workshops & Seminars 123 should not make it visible in Photo Gallery
        WebsiteGalleryItem.objects.create(
            title='Seminar Video',
            media_type='VIDEO',
            category=self.cat_workshops.name,
            category_ref=self.cat_workshops,
            file_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            is_active=True,
        )

        resp = self.client.get(reverse('public_photo_gallery'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        self.assertIn('Campus Infrastructure', html)
        self.assertIn('Sports Ground', html)
        self.assertNotIn('Topper Felicitation', html)
        self.assertNotIn('Workshops &amp; Seminars 123', html)
        self.assertNotIn('Workshops & Seminars 123', html)
        self.assertNotIn('Indoor', html)
        self.assertNotIn('0 Photos', html)
        self.assertNotIn('images.unsplash.com', html)

        sections = resp.context['category_sections']
        self.assertEqual([s['slug'] for s in sections], ['campus-infrastructure'])
        self.assertEqual(resp.context['total_photos_count'], 1)

    def test_photo_gallery_empty_state_when_no_photos_exist(self):
        resp = self.client.get(reverse('public_photo_gallery'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        self.assertEqual(resp.context['category_sections'], [])
        self.assertEqual(resp.context['total_photos_count'], 0)
        self.assertIn('Campus Photo Gallery Coming Soon', html)
        self.assertNotIn('Campus Infrastructure', html)
        self.assertNotIn('Topper Felicitation', html)
        self.assertNotIn('images.unsplash.com', html)

    def test_video_gallery_hides_category_filters_without_active_videos(self):
        WebsiteGalleryItem.objects.create(
            title='Campus Tour Video',
            media_type='VIDEO',
            category=self.cat_campus.name,
            category_ref=self.cat_campus,
            file_url='https://www.youtube.com/watch?v=Yqb1Ks886fE',
            is_active=True,
        )
        # Photo in Topper Felicitation should not expose Topper Felicitation in Video Gallery filters
        WebsiteGalleryItem.objects.create(
            title='Topper Photo',
            media_type='IMAGE',
            category=self.cat_toppers.name,
            category_ref=self.cat_toppers,
            file_url='/media/website/gallery/photos/topper.png',
            is_active=True,
        )
        # Inactive video in Indoor should not expose Indoor in Video Gallery filters
        WebsiteGalleryItem.objects.create(
            title='Hidden Indoor Video',
            media_type='VIDEO',
            category=self.cat_indoor.name,
            category_ref=self.cat_indoor,
            file_url='https://www.youtube.com/watch?v=Yqb1Ks886fE',
            is_active=False,
        )

        resp = self.client.get(reverse('public_video_gallery'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        visible_slugs = [c['slug'] for c in resp.context['gallery_categories']]
        self.assertEqual(visible_slugs, ['campus-infrastructure'])
        self.assertIn('data-video-filter="campus-infrastructure"', html)
        self.assertNotIn('data-video-filter="topper-felicitation"', html)
        self.assertNotIn('data-video-filter="workshops-seminars-123"', html)
        self.assertNotIn('data-video-filter="indoor"', html)

    def test_video_gallery_hides_all_category_filters_when_no_videos_exist(self):
        resp = self.client.get(reverse('public_video_gallery'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        self.assertEqual(resp.context['gallery_categories'], [])
        self.assertNotIn('data-video-filter="campus-infrastructure"', html)
        self.assertNotIn('data-video-filter="topper-felicitation"', html)
        self.assertNotIn('data-video-filter="science-labs-classrooms"', html)
        self.assertNotIn('data-video-filter="workshops-seminars"', html)

    def test_legacy_unlinked_items_still_match_category_by_name_or_slug(self):
        WebsiteGalleryItem.objects.create(
            title='Legacy Topper Photo',
            media_type='IMAGE',
            category='TOPPERS',
            category_ref=None,
            file_url='/media/website/gallery/photos/legacy_topper.png',
            is_active=True,
        )
        WebsiteGalleryItem.objects.create(
            title='Orphan Photo',
            media_type='IMAGE',
            category='Old Deleted Category',
            category_ref=None,
            file_url='/media/website/gallery/photos/orphan.png',
            is_active=True,
        )

        resp = self.client.get(reverse('public_photo_gallery'))
        self.assertEqual(resp.status_code, 200)
        sections = resp.context['category_sections']
        self.assertEqual([s['slug'] for s in sections], ['topper-felicitation', 'campus-life-highlights'])



class DeveloperOtpEmailTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='"Sutawane Software Support" <prameshwar4378@gmail.com>',
    )
    def test_generate_and_send_developer_otp_uses_settings_and_dispatches_email(self):
        success, code, msg = generate_and_send_developer_otp(AUTHORIZED_DEVELOPER_EMAIL)
        self.assertTrue(success, msg)
        self.assertEqual(len(code), 6)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, [AUTHORIZED_DEVELOPER_EMAIL.lower()])
        self.assertEqual(sent.from_email, '"Sutawane Software Support" <prameshwar4378@gmail.com>')
        self.assertIn(code, sent.body)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_api_developer_send_otp_endpoint_succeeds(self):
        resp = self.client.post(
            reverse('api_developer_send_otp'),
            data={'email': AUTHORIZED_DEVELOPER_EMAIL},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['success'], payload)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_verify_developer_otp_has_no_attempt_limit_or_remaining_count(self):
        success, code, _ = generate_and_send_developer_otp(AUTHORIZED_DEVELOPER_EMAIL)
        self.assertTrue(success)

        wrong_code = '000000' if code != '000000' else '111111'
        for _ in range(7):
            ok, msg = verify_developer_otp(AUTHORIZED_DEVELOPER_EMAIL, wrong_code)
            self.assertFalse(ok)
            self.assertNotIn('attempt', msg.lower())
            self.assertNotIn('remaining', msg.lower())

        ok, msg = verify_developer_otp(AUTHORIZED_DEVELOPER_EMAIL, code)
        self.assertTrue(ok, msg)


class LoginShowcaseContentTests(TestCase):
    def test_login_page_displays_only_actual_software_features(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        self.assertIn('Fee Collection, Installments', html)
        self.assertIn('Student Admissions', html)
        self.assertIn('WhatsApp Alerts, Reports', html)
        self.assertIn('One-Click Backup &amp; Restore', html)

        self.assertNotIn('biometric attendance', html)
        self.assertNotIn('Automated Daily DPPs', html)
        self.assertNotIn('Parent SMS', html)
        self.assertNotIn('Omkar Patil', html)
        self.assertNotIn('10,000+ Alumni', html)
        self.assertNotIn('attendance syncing', html)



class SettingsSeparationTests(TestCase):
    def test_default_settings_loads_development_sqlite(self):
        from django.conf import settings as active_settings

        self.assertEqual(active_settings.ENVIRONMENT, 'development')
        self.assertEqual(active_settings.DATABASES['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertFalse(active_settings.SECURE_SSL_REDIRECT)
        self.assertEqual(active_settings.BASE_DIR.name, 'Django')

    def test_production_settings_requires_secret_and_db_password_and_configures_postgres(self):
        import json
        import os
        import subprocess
        import sys
        from django.conf import settings as active_settings

        base_dir = str(active_settings.BASE_DIR)

        # 1. Fails fast when DB_PASSWORD is missing
        env_missing = os.environ.copy()
        env_missing.update({
            'DJANGO_ENV': 'production',
            'DJANGO_SETTINGS_MODULE': 'SUTAWANE_EDUCATION.settings.production',
            'DJANGO_SECRET_KEY': 'test-prod-secret-key-xyz-999',
            'DB_PASSWORD': '',
        })
        res_fail = subprocess.run(
            [sys.executable, '-c', 'import SUTAWANE_EDUCATION.settings.production'],
            cwd=base_dir,
            env=env_missing,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_fail.returncode, 0)
        self.assertIn('DB_PASSWORD', res_fail.stderr)

        # 2. Loads PostgreSQL & production hardening when required env vars are provided
        env_prod = os.environ.copy()
        env_prod.update({
            'DJANGO_ENV': 'production',
            'DJANGO_SETTINGS_MODULE': 'SUTAWANE_EDUCATION.settings',
            'DJANGO_DEBUG': 'False',
            'DJANGO_SECRET_KEY': 'test-prod-secret-key-xyz-999',
            'DB_NAME': 'sutawane_db',
            'DB_USER': 'sutawane_user',
            'DB_PASSWORD': 'test-db-password-123',
            'DB_HOST': '127.0.0.1',
            'DB_PORT': '5432',
            'DJANGO_SECURE_SSL': 'True',
            'DJANGO_ALLOWED_HOSTS': 'portal.sutawanegroup.com,173.249.33.152',
            'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://portal.sutawanegroup.com',
        })
        probe_code = (
            'import json, SUTAWANE_EDUCATION.settings as settings; '
            'print(json.dumps({'
            '"env": settings.ENVIRONMENT, '
            '"debug": settings.DEBUG, '
            '"engine": settings.DATABASES["default"]["ENGINE"], '
            '"name": settings.DATABASES["default"]["NAME"], '
            '"user": settings.DATABASES["default"]["USER"], '
            '"health": settings.DATABASES["default"].get("CONN_HEALTH_CHECKS"), '
            '"ssl_redirect": settings.SECURE_SSL_REDIRECT, '
            '"session_secure": settings.SESSION_COOKIE_SECURE, '
            '"csrf_secure": settings.CSRF_COOKIE_SECURE, '
            '"hsts": settings.SECURE_HSTS_SECONDS, '
            '"hosts": settings.ALLOWED_HOSTS, '
            '"origins": settings.CSRF_TRUSTED_ORIGINS, '
            '"cache_backend": settings.CACHES["default"]["BACKEND"], '
            '"base_dir_name": settings.BASE_DIR.name'
            '}))'
        )
        res_ok = subprocess.run(
            [sys.executable, '-c', probe_code],
            cwd=base_dir,
            env=env_prod,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_ok.returncode, 0, res_ok.stderr)
        data = json.loads(res_ok.stdout.strip())
        self.assertEqual(data['env'], 'production')
        self.assertFalse(data['debug'])
        self.assertEqual(data['engine'], 'django.db.backends.postgresql')
        self.assertEqual(data['name'], 'sutawane_db')
        self.assertEqual(data['user'], 'sutawane_user')
        self.assertTrue(data['health'])
        self.assertTrue(data['ssl_redirect'])
        self.assertTrue(data['session_secure'])
        self.assertTrue(data['csrf_secure'])
        self.assertEqual(data['hsts'], 31536000)
        self.assertEqual(data['hosts'], ['portal.sutawanegroup.com', '173.249.33.152'])
        self.assertEqual(data['origins'], ['https://portal.sutawanegroup.com'])
        self.assertIn('DatabaseCache', data['cache_backend'])
        self.assertEqual(data['base_dir_name'], 'Django')

    def test_database_cache_table_is_created_and_usable(self):
        from django.core.cache.backends.db import DatabaseCache

        db_cache = DatabaseCache(
            'sutawane_cache_table',
            {'TIMEOUT': 60, 'KEY_PREFIX': 'test_dbcache'},
        )
        db_cache.set('phase1_probe_key', {'ok': True}, 30)
        self.assertEqual(db_cache.get('phase1_probe_key'), {'ok': True})
        db_cache.delete('phase1_probe_key')


class Phase2SecurityHardeningTests(TestCase):
    def setUp(self):
        from .auth_utils import hash_password
        from .models import Branch, RolePermission, SystemSetting, User

        self.branch = Branch.objects.create(name='Main Branch', code='MAIN', is_active=True)
        owner_hash, owner_salt = hash_password('owner1234')
        self.owner = User.objects.create(
            username='owner_admin',
            name='Class Owner',
            password=owner_hash,
            salt=owner_salt,
            role='CLASS_OWNER',
            is_active=True,
        )
        bm_hash, bm_salt = hash_password('manager1234')
        self.bm = User.objects.create(
            username='bm_user',
            name='Branch Manager',
            password=bm_hash,
            salt=bm_salt,
            role='BRANCH_MANAGER',
            branch=self.branch,
            is_active=True,
        )
        RolePermission.objects.create(
            role='BRANCH_MANAGER',
            can_access_settings=False,
            can_access_backup=False,
        )
        SystemSetting.objects.update_or_create(
            key='whatsapp_meta_access_token',
            defaults={'value': 'SECRET_META_TOKEN_12345'},
        )
        SystemSetting.objects.update_or_create(
            key='whatsapp_meta_webhook_token',
            defaults={'value': 'VERIFY_SECRET_999'},
        )

    def test_anonymous_public_page_does_not_impersonate_owner_or_leak_secrets(self):
        from django.contrib.sessions.models import Session

        before_sessions = Session.objects.count()
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['current_user'])
        self.assertFalse(resp.context['is_class_owner'])
        self.assertFalse(resp.context['is_user_authenticated'])
        self.assertNotIn('whatsapp_meta_access_token', resp.context['institute_settings'])
        self.assertNotIn('SECRET_META_TOKEN_12345', resp.content.decode('utf-8'))
        self.assertEqual(Session.objects.count(), before_sessions)

    def test_whatsapp_admin_routes_require_auth_and_webhook_is_reachable(self):
        self.assertEqual(self.client.get('/api/settings/whatsapp-status/').status_code, 401)
        self.assertEqual(self.client.get('/api/settings/whatsapp-qr/').status_code, 401)
        self.assertEqual(self.client.post('/api/settings/whatsapp-action/', {'action': 'logout'}).status_code, 401)
        self.assertEqual(self.client.get('/api/settings/').status_code, 401)

        # Webhook verification reaches view rather than redirecting to /login/
        bad = self.client.get('/api/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=WRONG&hub.challenge=12345')
        self.assertEqual(bad.status_code, 403)
        good = self.client.get('/api/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=VERIFY_SECRET_999&hub.challenge=12345')
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.content.decode('utf-8'), '12345')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_otp_not_stored_plaintext_and_branch_manager_blocked_from_api_settings(self):
        from .auth_utils import AUTHORIZED_DEVELOPER_EMAIL, generate_and_send_developer_otp
        from .models import SystemSetting

        ok, code, _ = generate_and_send_developer_otp(AUTHORIZED_DEVELOPER_EMAIL)
        self.assertTrue(ok)
        otp_setting = SystemSetting.objects.get(key=f'dev_otp_{AUTHORIZED_DEVELOPER_EMAIL}')
        self.assertNotIn(code, otp_setting.value)

        session = self.client.session
        session['user_id'] = str(self.bm.id)
        session.save()

        self.assertEqual(self.client.get('/api/settings/').status_code, 403)

    def test_owner_cannot_create_developer_or_hijack_license_via_api_settings(self):
        from .models import SystemSetting, User

        session = self.client.session
        session['user_id'] = str(self.owner.id)
        session.save()

        resp = self.client.post('/settings/?tab=roles', {
            'action': 'create_user',
            'name': 'Fake Dev',
            'username': 'fakedev',
            'password': 'password123',
            'role': 'DEVELOPER',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(User.objects.filter(username='fakedev').exists())

        api_resp = self.client.post('/api/settings/', {
            'license_is_active': 'false',
            'whatsapp_credits_balance': '999999',
        }, content_type='application/json')
        self.assertEqual(api_resp.status_code, 200)
        self.assertFalse(SystemSetting.objects.filter(key='license_is_active', value='false').exists())
        self.assertFalse(SystemSetting.objects.filter(key='whatsapp_credits_balance', value='999999').exists())

        # GET /api/settings/ excludes secret Meta tokens
        get_resp = self.client.get('/api/settings/')
        self.assertEqual(get_resp.status_code, 200)
        payload = get_resp.json()
        self.assertNotIn('whatsapp_meta_access_token', payload)
        self.assertTrue(payload.get('whatsapp_meta_access_token_configured'))

    def test_malformed_license_date_fails_closed(self):
        from .auth_utils import get_license_status, invalidate_license_cache
        from .models import SystemSetting

        try:
            SystemSetting.objects.update_or_create(key='license_expiry_date', defaults={'value': 'NOT-A-DATE'})
            invalidate_license_cache()
            status_dict = get_license_status(force_refresh=True)
            self.assertTrue(status_dict['isExpired'])
        finally:
            SystemSetting.objects.filter(key='license_expiry_date').delete()
            invalidate_license_cache()



class BackupServiceBackendTests(TestCase):
    def test_sqlite_list_and_snapshot_backup_with_temp_dir(self):
        import tempfile
        from django.test import override_settings
        from .backup_service import create_full_backup_snapshot, list_backups

        with tempfile.TemporaryDirectory() as tmp_backups:
            with override_settings(BACKUPS_DIR=tmp_backups):
                data = list_backups()
                self.assertEqual(data['stats']['databaseEngineLabel'], 'SQLite 3')
                self.assertEqual(data['stats']['backupsCount'], 0)

                snap = create_full_backup_snapshot(label_prefix='test-unit-snap')
                self.assertTrue(snap['fileName'].endswith('.zip'))
                after = list_backups()
                self.assertEqual(after['stats']['backupsCount'], 1)


class Phase3RBACWebhookXSSTests(TestCase):
    def setUp(self):
        from datetime import datetime, timezone as dt_timezone
        from decimal import Decimal
        from django.core.cache import cache
        from .auth_utils import hash_password
        from .models import (
            AcademicSession,
            Branch,
            FeePlan,
            Installment,
            Payment,
            RolePermission,
            Student,
            StudentAdmission,
            SystemSetting,
            User,
        )

        cache.clear()
        self.branch_a = Branch.objects.create(name='Branch A', code='BRA', is_active=True)
        self.branch_b = Branch.objects.create(name='Branch B', code='BRB', is_active=True)
        self.session = AcademicSession.objects.create(
            name='2026-27',
            start_date=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            end_date=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            is_current=True,
            isActive=True,
        )
        pw_hash, salt = hash_password('Pass@1234')
        self.dev = User.objects.create(
            username='dev3',
            name='Dev User',
            password=pw_hash,
            salt=salt,
            role='DEVELOPER',
            is_active=True,
        )
        self.owner = User.objects.create(
            username='owner3',
            name='Owner User',
            password=pw_hash,
            salt=salt,
            role='CLASS_OWNER',
            is_active=True,
        )
        self.bm_a = User.objects.create(
            username='bm_a',
            name='BM A',
            password=pw_hash,
            salt=salt,
            role='BRANCH_MANAGER',
            branch=self.branch_a,
            is_active=True,
        )
        self.bm_unassigned = User.objects.create(
            username='bm_none',
            name='BM Unassigned',
            password=pw_hash,
            salt=salt,
            role='BRANCH_MANAGER',
            branch=None,
            is_active=True,
        )
        self.perm = RolePermission.objects.create(
            role='BRANCH_MANAGER',
            can_view_students=True,
            can_edit_students=True,
            can_collect_fees=True,
            can_void_receipts=True,
            can_export_reports=False,
            can_access_backup=False,
            can_access_settings=False,
            restricted_to_assigned_branch=True,
        )
        self.student_a = Student.objects.create(
            student_code='ST-A1',
            full_name='Student Alpha',
            parent_phone='9800000001',
        )
        self.adm_a = StudentAdmission.objects.create(
            student=self.student_a,
            branch=self.branch_a,
            session=self.session,
            roll_number='BRA-1',
            standard='11th Science',
            is_active=True,
        )
        self.fp_a = FeePlan.objects.create(
            admission=self.adm_a,
            session=self.session,
            total_fees=Decimal('10000.00'),
            total_discount=Decimal('0.00'),
            net_payable=Decimal('10000.00'),
        )
        self.inst_a = Installment.objects.create(
            fee_plan=self.fp_a,
            installment_no=1,
            label='Term 1',
            due_date=datetime(2026, 6, 1, tzinfo=dt_timezone.utc),
            amount_due=Decimal('10000.00'),
        )
        self.student_b = Student.objects.create(
            student_code='ST-B1',
            full_name='Student Beta',
            parent_phone='9800000002',
        )
        self.adm_b = StudentAdmission.objects.create(
            student=self.student_b,
            branch=self.branch_b,
            session=self.session,
            roll_number='BRB-1',
            standard='12th Science',
            is_active=True,
        )
        self.fp_b = FeePlan.objects.create(
            admission=self.adm_b,
            session=self.session,
            total_fees=Decimal('12000.00'),
            total_discount=Decimal('0.00'),
            net_payable=Decimal('12000.00'),
        )
        self.inst_b = Installment.objects.create(
            fee_plan=self.fp_b,
            installment_no=1,
            label='Term B1',
            due_date=datetime(2026, 6, 1, tzinfo=dt_timezone.utc),
            amount_due=Decimal('12000.00'),
        )
        self.payment_b = Payment.objects.create(
            student=self.student_b,
            branch=self.branch_b,
            session=self.session,
            admission=self.adm_b,
            receipt_number='REC-B-1',
            total_amount=Decimal('2000.00'),
            payment_mode='CASH',
        )
        SystemSetting.objects.update_or_create(key='license_is_active', defaults={'value': 'true'})
        SystemSetting.objects.update_or_create(key='license_expiry_date', defaults={'value': '2030-01-01'})

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _login_session(self, user):
        session = self.client.session
        session['user_id'] = str(user.id)
        session.save()

    def test_open_redirect_blocked_on_switch_branch_and_receipt_void(self):
        self._login_session(self.owner)
        resp = self.client.get(
            f'/switch-branch/{self.branch_a.id}/',
            HTTP_REFERER='https://evil.example/phish?x=1',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(resp['Location'].startswith('https://evil.example'))

        void_resp = self.client.post(
            f'/fees/receipts/{self.payment_b.id}/void/',
            {'reversal_reason': 'Duplicate entry', 'next': 'https://evil.example/steal'},
        )
        self.assertEqual(void_resp.status_code, 302)
        self.assertEqual(void_resp['Location'], '/fees/collect/')

    def test_branch_manager_isolated_from_other_branch_and_installment_idor(self):
        self._login_session(self.bm_a)

        # Cannot load Branch B student on fee collection or modal
        fee_page = self.client.get(f'/fees/collect/?student_id={self.student_b.id}')
        self.assertEqual(fee_page.status_code, 200)
        self.assertIsNone(fee_page.context['selected_student'])
        self.assertEqual(self.client.get(f'/fees/collect-modal/{self.student_b.id}/', HTTP_HX_REQUEST='true').status_code, 403)
        non_htmx_modal = self.client.get(f'/fees/collect-modal/{self.student_b.id}/')
        self.assertEqual(non_htmx_modal.status_code, 302)
        self.assertEqual(self.client.get(f'/fees/receipt-modal/{self.payment_b.id}/').status_code, 403)

        # Cannot modify Branch B installment by submitting inst_b ID under student_a (IDOR fix)
        orig_due = self.inst_b.due_date
        self.client.post(f'/students/{self.student_a.id}/', {
            'action': 'update_due_date',
            'installment_id': str(self.inst_b.id),
            'due_date': '2026-12-25',
        })
        self.inst_b.refresh_from_db()
        self.assertEqual(self.inst_b.due_date, orig_due)

    def test_branch_manager_without_assigned_branch_fails_closed(self):
        from .views import is_user_authorized_for_student, is_user_authorized_for_branch

        self.assertFalse(is_user_authorized_for_student(self.bm_unassigned, self.student_a))
        self.assertFalse(is_user_authorized_for_branch(self.bm_unassigned, self.branch_a.id))
        self.assertFalse(is_user_authorized_for_student(None, self.student_a))

    def test_export_and_backup_apis_enforce_permissions(self):
        self._login_session(self.bm_a)
        self.assertEqual(self.client.get('/students/?export=excel').status_code, 403)
        self.assertEqual(self.client.get(f'/students/{self.student_a.id}/statement/pdf/').status_code, 403)
        self.assertEqual(self.client.get('/expenses/?export=pdf').status_code, 403)
        self.assertEqual(self.client.get('/api/backup/').status_code, 403)

    def test_meta_webhook_signature_and_latest_log_update_without_slice_error(self):
        import hashlib
        import hmac
        import json
        from .models import NotificationLog, SystemSetting

        # Missing webhook token must fail closed on both GET and POST
        self.assertEqual(self.client.get('/api/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=anything').status_code, 403)
        self.assertEqual(self.client.post('/api/whatsapp/webhook/', '{}', content_type='application/json').status_code, 403)

        SystemSetting.objects.update_or_create(key='whatsapp_meta_webhook_token', defaults={'value': 'HOOK_TOK_123'})
        SystemSetting.objects.update_or_create(key='whatsapp_meta_app_secret', defaults={'value': 'APP_SECRET_XYZ'})
        log = NotificationLog.objects.create(
            recipient_mobile='919800000001',
            recipient_name='Parent Alpha',
            message_type='PAYMENT_RECEIPT',
            message_text='Test receipt',
            status='SENT',
        )
        payload_bytes = json.dumps({
            'entry': [{'changes': [{'value': {'statuses': [{
                'status': 'failed',
                'recipient_id': '919800000001',
                'errors': [{'message': 'Undeliverable number'}],
            }]}}]}]
        }).encode('utf-8')

        # Missing or wrong HMAC signature rejected
        bad = self.client.post('/api/whatsapp/webhook/', payload_bytes, content_type='application/json', HTTP_X_HUB_SIGNATURE_256='sha256=deadbeef')
        self.assertEqual(bad.status_code, 403)

        good_sig = 'sha256=' + hmac.new(b'APP_SECRET_XYZ', payload_bytes, hashlib.sha256).hexdigest()
        good = self.client.post('/api/whatsapp/webhook/', payload_bytes, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=good_sig)
        self.assertEqual(good.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.status, 'FAILED')
        self.assertIn('Undeliverable number', log.response_payload)

    def test_upload_rejects_svg_and_sanitizes_notification_html(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import WebsiteNotification

        self._login_session(self.owner)
        svg_file = SimpleUploadedFile('evil.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', content_type='image/svg+xml')
        resp = self.client.post('/api/settings/logo/', {'logo': svg_file})
        self.assertEqual(resp.status_code, 400)

        self.client.post('/website-management/', {
            'action': 'add_notification',
            'title': 'Holiday Notice',
            'content': '<p><strong>Holiday</strong> tomorrow</p><script>alert(1)</script><a href="javascript:alert(2)" onclick="evil()">link</a>',
            'is_active': 'on',
        })
        notice = WebsiteNotification.objects.get(title='Holiday Notice')
        self.assertNotIn('<script', notice.content.lower())
        self.assertNotIn('javascript:', notice.content.lower())
        self.assertNotIn('onclick', notice.content.lower())
        self.assertIn('<strong>Holiday</strong>', notice.content)

    @override_settings(DEBUG=False)
    def test_custom_500_handler_redacts_traceback_for_non_developers(self):
        import sys
        from django.test import RequestFactory
        from .views import custom_500_handler

        rf = RequestFactory()
        req = rf.get('/boom/')
        req.current_user = self.owner
        try:
            raise RuntimeError('Sensitive SQLite internal string secret=123')
        except RuntimeError:
            resp = custom_500_handler(req)
            self.assertEqual(resp.status_code, 500)
            self.assertNotIn(b'Sensitive SQLite internal string', resp.content)
            req.current_user = self.dev
            dev_resp = custom_500_handler(req)
            self.assertEqual(dev_resp.status_code, 500)
            self.assertIn(b'Sensitive SQLite internal string', dev_resp.content)

    def test_post_only_logout_and_toggle_sidebar(self):
        self._login_session(self.owner)
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertEqual(self.client.get('/toggle-sidebar/').status_code, 405)

        toggle = self.client.post('/toggle-sidebar/')
        self.assertEqual(toggle.status_code, 200)
        self.assertTrue(toggle.json()['is_collapsed'])

        out = self.client.post('/logout/')
        self.assertEqual(out.status_code, 302)
        self.assertNotIn('user_id', self.client.session)


class Phase4AtomicityValidationBackupTests(TestCase):
    def setUp(self):
        from datetime import datetime, timezone as dt_timezone
        from decimal import Decimal
        from django.core.cache import cache
        from .auth_utils import hash_password
        from .models import (
            AcademicSession,
            Branch,
            FeePlan,
            Installment,
            Student,
            StudentAdmission,
            SystemSetting,
            User,
        )

        cache.clear()
        self.branch = Branch.objects.create(name='Branch Four', code='BR4', is_active=True)
        self.session = AcademicSession.objects.create(
            name='2026-27',
            start_date=datetime(2026, 4, 1, tzinfo=dt_timezone.utc),
            end_date=datetime(2027, 3, 31, tzinfo=dt_timezone.utc),
            is_current=True,
            isActive=True,
        )
        self.old_session = AcademicSession.objects.create(
            name='2025-26',
            start_date=datetime(2025, 4, 1, tzinfo=dt_timezone.utc),
            end_date=datetime(2026, 3, 31, tzinfo=dt_timezone.utc),
            is_current=False,
            isActive=True,
        )
        pw_hash, salt = hash_password('Pass@1234')
        self.owner = User.objects.create(
            username='owner4',
            name='Owner Four',
            password=pw_hash,
            salt=salt,
            role='CLASS_OWNER',
            is_active=True,
        )
        self.student = Student.objects.create(
            student_code='ST-401',
            full_name='Student Four',
            parent_phone='9800000401',
        )
        self.adm = StudentAdmission.objects.create(
            student=self.student,
            branch=self.branch,
            session=self.session,
            roll_number='BR4-1',
            standard='11th Science',
            is_active=True,
        )
        self.fp = FeePlan.objects.create(
            admission=self.adm,
            session=self.session,
            total_fees=Decimal('10000.00'),
            total_discount=Decimal('0.00'),
            net_payable=Decimal('10000.00'),
        )
        self.inst = Installment.objects.create(
            fee_plan=self.fp,
            installment_no=1,
            label='Term 1',
            due_date=datetime(2026, 6, 1, tzinfo=dt_timezone.utc),
            amount_due=Decimal('10000.00'),
        )
        SystemSetting.objects.update_or_create(key='license_is_active', defaults={'value': 'true'})
        SystemSetting.objects.update_or_create(key='license_expiry_date', defaults={'value': '2030-01-01'})

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _login_session(self, user):
        session = self.client.session
        session['user_id'] = str(user.id)
        session.save()

    def test_parse_non_negative_money_rejects_malformed_and_excessive(self):
        from decimal import Decimal
        from .views import parse_non_negative_money

        for bad_val in ('NaN', 'Infinity', '-1', '10000000000.00', 'abc'):
            with self.assertRaises(ValueError):
                parse_non_negative_money(bad_val, allow_blank=False)

        self.assertEqual(parse_non_negative_money('9999999999.99', allow_blank=False), Decimal('9999999999.99'))
        self.assertEqual(parse_non_negative_money('123.456', allow_blank=False), Decimal('123.46'))

    def test_collect_fee_overpayment_sequential_receipts_and_idempotent_reversal(self):
        from decimal import Decimal
        from .models import Payment, PreviousSessionDue
        from .views import generate_sequential_receipt_number

        r1 = generate_sequential_receipt_number(self.branch, self.session)
        r2 = generate_sequential_receipt_number(self.branch, self.session)
        self.assertNotEqual(r1, r2)
        self.assertTrue(r1.endswith('-BR4-REC1'))
        self.assertTrue(r2.endswith('-BR4-REC2'))

        self._login_session(self.owner)
        # Strict overpayment check: no 0.005 tolerance loophole via modal or collect view
        self.client.post(f'/fees/collect-modal/{self.student.id}/', {
            'admission_id': str(self.adm.id),
            'amount': '10000.005',
            'payment_mode': 'CASH',
        })
        self.client.post('/fees/collect/', {
            'action': 'collect_payment',
            'student_id': str(self.student.id),
            'target_type': 'ADMISSION',
            'admission_id': str(self.adm.id),
            'amount': '10000.01',
            'payment_mode': 'CASH',
        })
        self.assertEqual(Payment.objects.filter(student=self.student).count(), 0)

        # Previous session due collection + double reversal must not double-decrement collected_amount
        prev_due = PreviousSessionDue.objects.create(
            student=self.student,
            original_session=self.old_session,
            current_session=self.session,
            outstanding_amount=Decimal('3000.00'),
            collected_amount=Decimal('1000.00'),
        )
        self.client.post('/fees/collect/', {
            'action': 'collect_payment',
            'student_id': str(self.student.id),
            'target_type': 'PREVIOUS_DUE',
            'previous_due_id': str(prev_due.id),
            'amount': '500.00',
            'payment_mode': 'CASH',
        })
        pay = Payment.objects.get(student=self.student, previous_due=prev_due)
        prev_due.refresh_from_db()
        self.assertEqual(prev_due.collected_amount, Decimal('1500.00'))

        self.client.post('/fees/collect/', {
            'action': 'reverse_payment',
            'payment_id': str(pay.id),
            'refund_mode': 'CASH',
            'reversal_reason': 'First void',
        })
        self.client.post('/fees/collect/', {
            'action': 'reverse_payment',
            'payment_id': str(pay.id),
            'refund_mode': 'CASH',
            'reversal_reason': 'Duplicate void attempt',
        })
        pay.refresh_from_db()
        prev_due.refresh_from_db()
        self.assertTrue(pay.is_reversed)
        self.assertEqual(prev_due.collected_amount, Decimal('1000.00'))

    def test_delete_student_and_session_with_restrict_dependencies(self):
        from decimal import Decimal
        from .models import AcademicSession, Payment, PreviousSessionDue, Student

        prev_due = PreviousSessionDue.objects.create(
            student=self.student,
            original_session=self.old_session,
            current_session=self.session,
            outstanding_amount=Decimal('2000.00'),
            collected_amount=Decimal('500.00'),
        )
        pay = Payment.objects.create(
            student=self.student,
            branch=self.branch,
            session=self.session,
            previous_due=prev_due,
            receipt_number='REC-PREV-DEL-1',
            total_amount=Decimal('500.00'),
            payment_mode='CASH',
            is_reversed=False,
        )

        self._login_session(self.owner)
        # Session delete linked to PreviousSessionDue must fail gracefully instead of 500 RestrictedError
        sess_resp = self.client.post('/sessions/', {
            'action': 'delete',
            'session_id': str(self.old_session.id),
        })
        self.assertEqual(sess_resp.status_code, 302)
        self.assertTrue(AcademicSession.objects.filter(id=self.old_session.id).exists())

        # Active payment blocks permanent delete; once reversed, deleting student deletes payment before RESTRICT PreviousSessionDue
        self.client.post('/students/', {'action': 'delete', 'student_id': str(self.student.id)})
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        pay.is_reversed = True
        pay.save(update_fields=['is_reversed'])

        stud_resp = self.client.post('/students/', {
            'action': 'delete',
            'student_id': str(self.student.id),
        })
        self.assertEqual(stud_resp.status_code, 302)
        self.assertFalse(Student.objects.filter(id=self.student.id).exists())
        self.assertFalse(PreviousSessionDue.objects.filter(id=prev_due.id).exists())

    def test_whatsapp_credit_atomic_decrement(self):
        from .models import SystemSetting
        from .whatsapp import deduct_whatsapp_credit

        SystemSetting.objects.update_or_create(key='whatsapp_credits_enforced', defaults={'value': 'true'})
        SystemSetting.objects.update_or_create(key='whatsapp_credits_balance', defaults={'value': '2'})
        SystemSetting.objects.update_or_create(key='whatsapp_messages_sent_count', defaults={'value': '0'})

        self.assertEqual(deduct_whatsapp_credit(), 1)
        self.assertEqual(deduct_whatsapp_credit(), 0)
        self.assertEqual(deduct_whatsapp_credit(), 0)

        self.assertEqual(SystemSetting.objects.get(key='whatsapp_credits_balance').value, '0')
        self.assertEqual(SystemSetting.objects.get(key='whatsapp_messages_sent_count').value, '3')

    def test_backup_security_validation_and_website_batch_flag(self):
        import os
        import tempfile
        import zipfile
        from .backup_service import (
            _extract_media_from_zip,
            _sanitize_summary_settings,
            _validate_sqlite_staging_file,
            execute_restore_from_file,
        )
        from .models import WebsiteBatchCard, WebsiteGalleryItem

        sanitized = _sanitize_summary_settings({
            'dev_otp_code': '999999',
            'whatsapp_meta_app_secret': 'top-secret',
            'institute_name': 'Sutawane Classes',
        })
        self.assertEqual(sanitized['dev_otp_code'], '***REDACTED***')
        self.assertEqual(sanitized['whatsapp_meta_app_secret'], '***REDACTED***')
        self.assertEqual(sanitized['institute_name'], 'Sutawane Classes')

        with tempfile.TemporaryDirectory() as tmp_dir:
            media_dir = os.path.join(tmp_dir, 'media')
            zip_path = os.path.join(tmp_dir, 'zipslip.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('../../outside.txt', 'pwned')
                zf.writestr('media/photos/safe.jpg', b'JPEGDATA')

            with zipfile.ZipFile(zip_path, 'r') as zf:
                photos, _, _, total = _extract_media_from_zip(zf, media_dir)

            self.assertEqual(photos, 1)
            self.assertEqual(total, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp_dir, 'outside.txt')))
            self.assertTrue(os.path.exists(os.path.join(media_dir, 'photos', 'safe.jpg')))

            bad_db = os.path.join(tmp_dir, 'bad.db')
            with open(bad_db, 'wb') as f:
                f.write(b'not-a-sqlite-header')
            with self.assertRaises(ValueError):
                _validate_sqlite_staging_file(bad_db)

            bad_zip = os.path.join(tmp_dir, 'corrupt.zip')
            with open(bad_zip, 'wb') as f:
                f.write(b'not-a-zip')
            with override_settings(BACKUPS_DIR=tmp_dir, MEDIA_ROOT=media_dir):
                with self.assertRaises(ValueError):
                    execute_restore_from_file(bad_zip, 'corrupt.zip')

        self._login_session(self.owner)
        self.client.post('/website-management/', {
            'action': 'add_batch',
            'title': 'Hidden Batch 2026',
            'category': 'science',
            'stream_tag': '12th',
            'sort_order': 'abc',
        })
        batch = WebsiteBatchCard.objects.get(title='Hidden Batch 2026')
        self.assertFalse(batch.is_active)

        self.client.post('/website-management/', {
            'action': 'add_gallery',
            'title': 'Safe Sort Video',
            'media_type': 'VIDEO',
            'video_url': 'https://youtu.be/dQw4w9WgXcQ',
            'sort_order': 'bad-int',
            'is_active': 'on',
        })
        gal = WebsiteGalleryItem.objects.get(title='Safe Sort Video')
        self.assertEqual(gal.sort_order, 0)


class Phase5ReportsExportsUITests(TestCase):
    def setUp(self):
        from datetime import datetime, timezone as dt_timezone
        from decimal import Decimal
        from zoneinfo import ZoneInfo
        from django.core.cache import cache
        from .auth_utils import hash_password
        from .models import (
            AcademicSession,
            Branch,
            ExpenseCategory,
            FeePlan,
            Student,
            StudentAdmission,
            SystemSetting,
            User,
        )

        cache.clear()
        self.ist = ZoneInfo('Asia/Kolkata')
        self.branch = Branch.objects.create(name='Main / Center: Alpha', code='BR5', is_active=True)
        self.old_session = AcademicSession.objects.create(
            name='2025-26',
            start_date=datetime(2025, 4, 1, 0, 0, tzinfo=self.ist),
            end_date=datetime(2026, 3, 31, 0, 0, tzinfo=self.ist),
            is_current=False,
            isActive=True,
        )
        self.session = AcademicSession.objects.create(
            name='2026-27',
            start_date=datetime(2026, 4, 1, 0, 0, tzinfo=self.ist),
            end_date=datetime(2027, 3, 31, 0, 0, tzinfo=self.ist),
            is_current=True,
            isActive=True,
        )
        pw_hash, salt = hash_password('Pass@1234')
        self.owner = User.objects.create(
            username='owner5',
            name='Owner & Audit <Admin>',
            password=pw_hash,
            salt=salt,
            role='CLASS_OWNER',
            is_active=True,
        )
        self.exp_cat = ExpenseCategory.objects.create(name='Utilities & Bills')
        self.student = Student.objects.create(
            student_code='ST-501',
            full_name='Aarav & Meera <Topper>',
            parent_phone='9800000501',
        )
        self.adm_old = StudentAdmission.objects.create(
            student=self.student,
            branch=self.branch,
            session=self.old_session,
            roll_number='BR5-OLD-1',
            standard='10th Board',
            is_active=True,
        )
        self.fp_old = FeePlan.objects.create(
            admission=self.adm_old,
            session=self.old_session,
            total_fees=Decimal('10000.00'),
            total_discount=Decimal('0.00'),
            net_payable=Decimal('10000.00'),
        )
        self.adm_cur = StudentAdmission.objects.create(
            student=self.student,
            branch=self.branch,
            session=self.session,
            roll_number='BR5-CUR-1',
            standard='11th Sci & Tech',
            is_active=True,
        )
        self.fp_cur = FeePlan.objects.create(
            admission=self.adm_cur,
            session=self.session,
            total_fees=Decimal('20000.00'),
            total_discount=Decimal('0.00'),
            net_payable=Decimal('20000.00'),
        )
        SystemSetting.objects.update_or_create(key='license_is_active', defaults={'value': 'true'})
        SystemSetting.objects.update_or_create(key='license_expiry_date', defaults={'value': '2030-01-01'})

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _login_session(self, user):
        session = self.client.session
        session['user_id'] = str(user.id)
        session.save()

    def test_export_theme_escaping_and_sheet_title_sanitization(self):
        from .export_theme import safe_xml_text, sanitize_excel_sheet_title

        escaped = safe_xml_text('A & B <Class> "10"')
        self.assertIn('&amp;', escaped)
        self.assertIn('&lt;Class&gt;', escaped)
        self.assertNotIn('<Class>', escaped)

        used = set()
        t1 = sanitize_excel_sheet_title('11th/12th: Sci * [Batch]? Exceeding Thirty One Characters', existing=used)
        used.add(t1)
        t2 = sanitize_excel_sheet_title('11th/12th: Sci * [Batch]? Exceeding Thirty One Characters', existing=used)
        self.assertLessEqual(len(t1), 31)
        self.assertLessEqual(len(t2), 31)
        self.assertNotEqual(t1, t2)
        for bad_ch in ('\\', '/', '?', '*', ':', '[', ']'):
            self.assertNotIn(bad_ch, t1)

    def test_reports_export_standard_breakdown_large_pdf_modes_and_statement(self):
        import io
        from openpyxl import load_workbook
        from .reports_export import (
            export_payment_modes_excel,
            export_session_audit_excel,
            export_session_audit_pdf,
            export_statement_excel,
            export_statement_pdf,
        )

        std_rows = [
            {
                'standard': f'Batch {i} & Honors <Special>',
                'studentCount': i + 5,
                'totalFees': 50000.0,
                'collected': 30000.0,
                'pendingDues': 20000.0,
                'collectionRate': 60.0,
            }
            for i in range(1, 18)
        ]
        audit_payload = {
            'session': {'name': '2026-27 <Main & City>'},
            'summary': {
                'totalStudents': 100,
                'totalFeesAgreed': 850000.0,
                'totalCollections': 510000.0,
                'totalPendingDues': 340000.0,
                'totalExpenses': 40000.0,
                'netSurplus': 470000.0,
                'isSurplus': True,
                'collectionEfficiency': 60.0,
            },
            'branchBreakdown': [{
                'branchName': 'Main / Campus',
                'branchCode': 'BR5',
                'studentsCount': 100,
                'totalFees': 850000.0,
                'collections': 510000.0,
                'pendingDues': 340000.0,
                'expenses': 40000.0,
                'netSurplus': 470000.0,
                'collectionRate': 60.0,
            }],
            'standardBreakdown': std_rows,
            'monthlyTrend': [{'monthLabel': f'Month {i}', 'collections': 10000.0, 'expenses': 2000.0} for i in range(1, 16)],
        }
        wb = load_workbook(io.BytesIO(export_session_audit_excel(audit_payload, {'branch_name': 'All & Main'})))
        ws2_vals = [cell for row in wb.worksheets[1].iter_rows(values_only=True) for cell in row if cell is not None]
        self.assertIn('Batch 1 & Honors <Special>', ws2_vals)

        pdf_audit = export_session_audit_pdf(audit_payload, {'branch_name': 'All & Main'})
        self.assertTrue(pdf_audit.startswith(b'%PDF-'))

        # Payment modes: zero collections safety + Cheque prevents inflated Cash Share
        zero_wb = load_workbook(io.BytesIO(export_payment_modes_excel({'modes': []})))
        self.assertIn('0.0%', str(zero_wb.worksheets[1]['B7'].value))

        modes_wb = load_workbook(io.BytesIO(export_payment_modes_excel({
            'modes': [
                {'mode': 'CASH', 'label': 'Cash Counter', 'amount': 2000.0, 'count': 2, 'percentage': 20.0},
                {'mode': 'BANK_TRANSFER', 'label': 'NEFT & Bank Transfer', 'amount': 5000.0, 'count': 1, 'percentage': 50.0},
                {'mode': 'CHEQUE', 'label': 'Cheque', 'amount': 3000.0, 'count': 1, 'percentage': 30.0},
            ]
        })))
        ins_sheet = modes_wb.worksheets[1]
        self.assertEqual(ins_sheet['B7'].value, '50.0%')
        self.assertEqual(ins_sheet['B8'].value, '20.0%')

        stmt_payload = {
            'summary': {
                'totalCollections': 10000.0,
                'collectionsCount': 2,
                'totalRefunds': 1500.0,
                'refundsCount': 1,
                'totalExpenses': 2500.0,
                'expensesCount': 1,
                'netMovement': 6000.0,
                'isProfit': True,
                'collectionsByMode': {'CASH': {'amount': 10000.0, 'count': 2}},
                'expensesByMode': {'CASH': {'amount': 2500.0, 'count': 1}},
                'expensesByCategory': {'Utilities & Bills': {'amount': 2500.0, 'count': 1}},
            },
            'collections': [],
            'expenses': [],
            'refunds': [],
        }
        stmt_wb = load_workbook(io.BytesIO(export_statement_excel(stmt_payload, {'period_label': 'Today'})))
        ws_summary = stmt_wb.worksheets[0]
        exp_rows = [r for r in range(5, 10) if ws_summary.cell(row=r, column=1).value == 'Total Center Expenditures']
        self.assertEqual(len(exp_rows), 1)
        self.assertTrue(str(ws_summary.cell(row=exp_rows[0], column=2).font.color.rgb).endswith('DC2626'))

        stmt_pdf = export_statement_pdf(stmt_payload, {'period_label': 'Today'})
        self.assertTrue(stmt_pdf.startswith(b'%PDF-'))

    def test_voided_receipts_excluded_from_ledger_and_user_report_exports(self):
        import io
        from datetime import datetime
        from decimal import Decimal
        from openpyxl import load_workbook
        from .models import Payment
        from .student_ledger_export import export_student_ledger_excel, export_student_ledger_pdf
        from .student_ledger_service import build_student_ledger_payload

        p_ok = Payment.objects.create(
            student=self.student,
            branch=self.branch,
            admission=self.adm_cur,
            session=self.session,
            receipt_number='BR5-OK-1',
            total_amount=Decimal('5000.00'),
            payment_mode='CASH',
            received_by=self.owner,
            created_by=self.owner,
            is_reversed=False,
        )
        Payment.objects.create(
            student=self.student,
            branch=self.branch,
            admission=self.adm_cur,
            session=self.session,
            receipt_number='BR5-VOID-1',
            total_amount=Decimal('4000.00'),
            payment_mode='UPI',
            received_by=self.owner,
            created_by=self.owner,
            is_reversed=True,
            reversal_reason='Wrong & entry <test>',
        )

        ledger = build_student_ledger_payload(str(self.student.id))
        wb_ledger = load_workbook(io.BytesIO(export_student_ledger_excel(ledger)))
        ws3 = wb_ledger.worksheets[2]
        voided_cells = [str(ws3.cell(row=r, column=2).value) for r in range(5, ws3.max_row + 1)]
        self.assertIn('BR5-VOID-1 (VOIDED)', voided_cells)
        total_row = ws3.max_row
        self.assertAlmostEqual(float(ws3.cell(row=total_row, column=10).value), 5000.0)
        self.assertAlmostEqual(float(ws3.cell(row=total_row, column=11).value), 5000.0)
        self.assertTrue(export_student_ledger_pdf(ledger).startswith(b'%PDF-'))

        self._login_session(self.owner)
        today_local = datetime.now(self.ist).date().strftime('%Y-%m-%d')
        resp_xl = self.client.get(
            f'/reports/user/?preset=custom&start_date={today_local}&end_date={today_local}&export=excel'
        )
        self.assertEqual(resp_xl.status_code, 200)
        wb_user = load_workbook(io.BytesIO(resp_xl.content))
        ws_col = wb_user.worksheets[1]
        self.assertAlmostEqual(float(ws_col.cell(row=ws_col.max_row, column=11).value), 5000.0)
        self.assertIn('Voided', str(ws_col.cell(row=ws_col.max_row, column=1).value))

        resp_pdf = self.client.get(
            f'/reports/user/?preset=custom&start_date={today_local}&end_date={today_local}&export=pdf'
        )
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertTrue(resp_pdf.content.startswith(b'%PDF-'))

        p_ok.delete()

    def test_all_sessions_audit_end_of_day_expenses_daily_bounds_and_full_student_export(self):
        import io
        from datetime import datetime
        from decimal import Decimal
        from openpyxl import load_workbook
        from .models import Expense, PreviousSessionDue, Student, StudentAdmission, FeePlan

        PreviousSessionDue.objects.create(
            student=self.student,
            original_session=self.old_session,
            current_session=self.session,
            outstanding_amount=Decimal('10000.00'),
            collected_amount=Decimal('0.00'),
        )
        # Expense recorded at 15:30 IST on the session end_date (when end_date is stored at midnight)
        Expense.objects.create(
            branch=self.branch,
            category=self.exp_cat,
            amount=Decimal('1250.00'),
            expense_date=datetime(2027, 3, 31, 15, 30, tzinfo=self.ist),
            description='Closing day stationery',
            payment_mode='CASH',
            created_by=self.owner,
        )

        self._login_session(self.owner)

        # 1. ALL sessions must NOT double-count PreviousSessionDue on top of FeePlans (10k + 20k = 30k, not 40k)
        res_all = self.client.get('/api/reports/session-audit/?session_id=ALL')
        self.assertEqual(res_all.status_code, 200)
        audit_all = res_all.json()
        self.assertAlmostEqual(float(audit_all['summary']['totalFeesAgreed']), 30000.0)
        self.assertAlmostEqual(float(audit_all['summary']['totalPendingDues']), 30000.0)

        # 2. Specific session includes afternoon expense on session.end_date
        res_cur = self.client.get(f'/api/reports/session-audit/?session_id={self.session.id}')
        self.assertEqual(res_cur.status_code, 200)
        audit_cur = res_cur.json()
        self.assertAlmostEqual(float(audit_cur['summary']['totalExpenses']), 1250.0)

        # 3. Dashboard ALL sessions branch_comparison matches non-double-counted dues
        dash_res = self.client.get('/app/?session_id=ALL')
        self.assertEqual(dash_res.status_code, 200)

        # 4. Daily reports invalid out-of-range year/month does not raise 500
        bad_daily = self.client.get('/reports/daily/?mode=MONTHLY&month=999&year=99999')
        self.assertEqual(bad_daily.status_code, 200)

        # 5. User report scoped to old_session excludes 2027 expense
        usr_res = self.client.get(
            f'/reports/user/?preset=custom&start_date=2025-04-01&end_date=2027-04-05&session_id={self.old_session.id}'
        )
        self.assertEqual(usr_res.status_code, 200)
        self.assertNotContains(usr_res, 'Closing day stationery')

        # 6. Students directory export returns ALL filtered rows beyond page_size=25
        for idx in range(2, 29):
            st = Student.objects.create(
                student_code=f'ST-5{idx:02d}',
                full_name=f'Export Student {idx:02d}',
                parent_phone=f'9800001{idx:03d}',
            )
            adm = StudentAdmission.objects.create(
                student=st,
                branch=self.branch,
                session=self.session,
                roll_number=f'BR5-{idx}',
                standard='11th Sci & Tech',
                is_active=True,
            )
            FeePlan.objects.create(
                admission=adm,
                session=self.session,
                total_fees=Decimal('5000.00'),
                total_discount=Decimal('0.00'),
                net_payable=Decimal('5000.00'),
            )

        exp_students = self.client.get(f'/students/?session_id={self.session.id}&page_size=25&export=excel')
        self.assertEqual(exp_students.status_code, 200)
        wb_st = load_workbook(io.BytesIO(exp_students.content))
        ws_st = wb_st.worksheets[0]
        # Rows 5..(5 + 28 - 1) = 28 students (row 4 is header, final row is Grand Total)
        exported_codes = {
            ws_st.cell(row=r, column=2).value
            for r in range(5, ws_st.max_row)
            if ws_st.cell(row=r, column=2).value
        }
        self.assertGreaterEqual(len(exported_codes), 28)
