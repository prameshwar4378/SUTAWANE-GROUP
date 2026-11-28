import contextvars
import hashlib
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from .models import User
from .auth_utils import get_license_status

_current_user_var = contextvars.ContextVar('current_authenticated_user', default=None)


def compute_session_user_fingerprint(user) -> str:
    """Compute a short credential/role fingerprint to auto-invalidate stale sessions."""
    raw = f"{user.password}:{user.role}:{bool(user.is_active)}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def get_current_authenticated_user():
    """
    Returns the currently authenticated User instance for the current request context, or None.
    Used by confidential models (.save hooks) to automatically record audit stamps.
    """
    return _current_user_var.get(None)


def set_current_authenticated_user(user):
    """Binds the authenticated User to the current request ContextVar."""
    return _current_user_var.set(user)


def clear_current_authenticated_user():
    """Cleans up the ContextVar reference at request termination."""
    _current_user_var.set(None)


EXEMPT_PREFIXES = (
    '/login/',
    '/logout/',
    '/static/',
    '/media/',
    '/api/developer/',
)

PUBLIC_PATHS = {
    '/',
    '/batches/',
    '/gallery/photos/',
    '/gallery/videos/',
    '/about/',
    '/contact/',
    '/api/public/inquiry/',
    '/api/whatsapp/webhook/',
}


def _is_public_or_exempt(path: str) -> bool:
    norm_path = path if (path == '/' or path.endswith('/')) else f"{path}/"
    if path in PUBLIC_PATHS or norm_path in PUBLIC_PATHS:
        return True
    for prefix in EXEMPT_PREFIXES:
        if path.startswith(prefix) or norm_path == prefix:
            return True
    return False


class SoftwareLicenseAndAuthMiddleware:
    """
    Middleware ensuring:
    1. Authentication: Non-public routes require a valid logged-in session.
    2. Automatic Audit Binding: Binds request.current_user to ContextVar storage for model auditing.
    3. License Guard: If software license is inactive or expired, blocks non-developer access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        clear_current_authenticated_user()

        if _is_public_or_exempt(path):
            return self.get_response(request)

        # Check Authentication
        session = getattr(request, 'session', None)
        user_id = session.get('user_id') if session else None
        current_user = None
        if user_id:
            candidate = User.objects.filter(id=user_id, is_active=True).first()
            if candidate:
                stored_fp = session.get('user_pw_fp')
                if stored_fp and stored_fp != compute_session_user_fingerprint(candidate):
                    candidate = None
            if not candidate and session:
                for key in ('user_id', 'user_role', 'user_name', 'user_pw_fp'):
                    session.pop(key, None)
            current_user = candidate

        if not current_user:
            login_target = f"/login/?next={request.path}"
            if path.startswith('/api/'):
                return JsonResponse({'success': False, 'error': 'Authentication required.'}, status=401)
            if request.headers.get('HX-Request') == 'true':
                resp = HttpResponse(status=401)
                resp['HX-Redirect'] = login_target
                return resp
            return redirect(login_target)

        request.current_user = current_user
        token = set_current_authenticated_user(current_user)

        try:
            # Developers are exempt from license expiration block so they can renew/manage license
            if not current_user.is_developer:
                license_info = get_license_status()
                if not license_info['isActive'] or license_info['isExpired']:
                    if path.startswith('/api/'):
                        return JsonResponse(
                            {'success': False, 'error': 'Software subscription plan is inactive or expired.'},
                            status=403,
                        )
                    context = {
                        'license': license_info,
                        'current_user': current_user,
                    }
                    return render(request, 'errors/403_locked.html', context, status=403)

            return self.get_response(request)
        finally:
            _current_user_var.reset(token)
