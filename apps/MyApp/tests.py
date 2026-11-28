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
        self.assertIn('FileBasedCache', data['cache_backend'])
        self.assertEqual(data['base_dir_name'], 'Django')



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
