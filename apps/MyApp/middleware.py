from django.shortcuts import render, redirect
from django.urls import reverse
from .models import User
from .auth_utils import get_license_status

EXEMPT_PREFIXES = (
    '/login/',
    '/logout/',
    '/static/',
    '/media/',
    '/api/developer/',
    '/api/settings/whatsapp-',
)

PUBLIC_PATHS = {
    '/',
    '/batches/',
    '/gallery/photos/',
    '/gallery/videos/',
    '/about/',
    '/contact/',
    '/api/public/inquiry/',
}


class SoftwareLicenseAndAuthMiddleware:
    """
    Middleware ensuring:
    1. Authentication: Non-public routes require a valid logged-in session.
    2. License Guard: If software license is inactive or expired, blocks non-developer access
       and renders the SoftwareLockScreen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # The marketing landing page is intentionally public. The WebApp
        # entry point at /app/ remains protected by the checks below.
        if path in PUBLIC_PATHS:
            return self.get_response(request)

        # 1. Exempt static, media, login and logout routes
        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        # 2. Check Authentication
        user_id = request.session.get('user_id')
        current_user = None
        if user_id:
            current_user = User.objects.filter(id=user_id, is_active=True).first()

        # If not logged in, redirect to login
        if not current_user:
            return redirect(f"/login/?next={request.path}")

        # Attach current_user to request
        request.current_user = current_user

        # 3. Check License Guard
        # Developers are exempt from license expiration block so they can renew/manage license
        if not current_user.is_developer:
            license_info = get_license_status()
            if not license_info['isActive'] or license_info['isExpired']:
                context = {
                    'license': license_info,
                    'current_user': current_user,
                }
                return render(request, 'errors/403_locked.html', context, status=403)

        return self.get_response(request)
