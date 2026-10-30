import os
from django.conf import settings as django_settings
from .models import Branch, AcademicSession, SystemSetting, User
from .auth_utils import get_user_permissions
from .cache_utils import (
    safe_cache_get,
    safe_cache_set,
    safe_cache_delete,
    build_cache_key,
    invalidate_context_cache,
    TTL_CONTEXT,
)


def get_cached_branches():
    """Returns active branches cached with automated signal-based invalidation."""
    cache_key = build_cache_key('context', 'active_branches')
    branches = safe_cache_get(cache_key)
    if branches is None:
        branches = list(Branch.objects.filter(is_active=True).order_by('name'))
        safe_cache_set(cache_key, branches, TTL_CONTEXT)
    return branches


def get_cached_sessions():
    """Returns active academic sessions cached with automated signal-based invalidation."""
    cache_key = build_cache_key('context', 'active_sessions')
    sessions = safe_cache_get(cache_key)
    if sessions is None:
        sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
        safe_cache_set(cache_key, sessions, TTL_CONTEXT)
    return sessions


def get_cached_settings_dict():
    """Returns system settings dictionary cached with automated signal-based invalidation."""
    cache_key = build_cache_key('context', 'system_settings_dict')
    s_dict = safe_cache_get(cache_key)
    if s_dict is None:
        settings_qs = SystemSetting.objects.all()
        s_dict = {s.key: s.value for s in settings_qs}
        safe_cache_set(cache_key, s_dict, TTL_CONTEXT)
    return s_dict


def get_branch_branding(branch=None):
    """
    Returns dedicated branding dict for a given branch with graceful fallback to central institute settings.
    Used across headers, fee receipts, and WhatsApp dispatches.
    """
    settings = get_cached_settings_dict()
    master_name = settings.get('institute_name', 'Sutawane Classes')
    master_logo = settings.get('logo_url') or '/static/images/logo-master.png'
    master_address = settings.get('address', '')
    master_phone = settings.get('phone', '')
    master_email = settings.get('email', '')
    master_tagline = settings.get('tagline', '')
    if branch:
        b_class_name = getattr(branch, 'class_name', None) or master_name
        b_logo = branch.logo_url or master_logo
        b_address = branch.address or master_address
        b_phone = branch.phone or master_phone
        b_email = getattr(branch, 'email', None) or master_email
        b_tagline = getattr(branch, 'tagline', None) or master_tagline
        return {
            'class_name': b_class_name,
            'branch_name': branch.name,
            'code': branch.code,
            'address': b_address,
            'phone': b_phone,
            'email': b_email,
            'tagline': b_tagline,
            'logo_url': b_logo,
            'is_branch_specific': bool(getattr(branch, 'class_name', None) or branch.logo_url),
        }
    return {
        'class_name': master_name,
        'branch_name': 'Central Campus',
        'code': 'MAIN',
        'address': master_address,
        'phone': master_phone,
        'email': master_email,
        'tagline': master_tagline,
        'logo_url': master_logo,
        'is_branch_specific': False,
    }


def invalidate_global_context_cache():
    """Immediately clears caches for branches, sessions, and system settings."""
    invalidate_context_cache()



def global_context(request):
    """
    High-Performance Global Context Processor for Sutawane Classes Management Software.
    Provides session-persistent branch, session, institute branding, and user state
    using memory caching to eliminate duplicate database and disk operations.
    """
    # 0. User Session & Permissions Context
    current_user = getattr(request, 'current_user', None)
    if not current_user:
        user_id = request.session.get('user_id')
        if user_id:
            current_user = User.objects.filter(id=user_id, is_active=True).first()
        if not current_user:
            current_user = User.objects.filter(role='CLASS_OWNER', is_active=True).first()

    is_developer = current_user.role == 'DEVELOPER' if current_user else False
    is_class_owner = current_user.role == 'CLASS_OWNER' if current_user else False
    is_branch_manager = current_user.role == 'BRANCH_MANAGER' if current_user else False
    user_permissions = get_user_permissions(current_user)

    # 1. Active Branches & Selected Branch (In-Memory Cached)
    branches = get_cached_branches()
    selected_branch_id = request.session.get('selected_branch_id', 'ALL')

    # Strict branch restriction for Branch Managers
    if is_branch_manager and current_user.branch_id and user_permissions.get('restricted_to_assigned_branch', True):
        selected_branch_id = str(current_user.branch_id)
        selected_branch = current_user.branch
    else:
        selected_branch = None
        if selected_branch_id and selected_branch_id != 'ALL':
            selected_branch = next((b for b in branches if str(b.id) == str(selected_branch_id)), None)
            if not selected_branch:
                selected_branch_id = 'ALL'

    # 2. Active Academic Sessions & Selected Session (In-Memory Cached)
    sessions = get_cached_sessions()
    selected_session_id = request.session.get('selected_session_id')
    
    if not selected_session_id:
        current_sess = next((s for s in sessions if s.is_current), None)
        if current_sess:
            selected_session_id = str(current_sess.id)
            request.session['selected_session_id'] = selected_session_id
        elif sessions:
            selected_session_id = str(sessions[0].id)
            request.session['selected_session_id'] = selected_session_id
        else:
            selected_session_id = 'ALL'

    selected_session = None
    if selected_session_id and selected_session_id != 'ALL':
        selected_session = next((s for s in sessions if str(s.id) == str(selected_session_id)), None)
        if not selected_session:
            current_sess = next((s for s in sessions if s.is_current), None)
            if current_sess:
                selected_session_id = str(current_sess.id)
                selected_session = current_sess
                request.session['selected_session_id'] = selected_session_id
            else:
                selected_session_id = 'ALL'
                request.session['selected_session_id'] = 'ALL'

    # 3. System Branding & Settings (In-Memory Cached with Dedicated Branch Branding)
    settings_dict = get_cached_settings_dict()
    branch_branding = get_branch_branding(selected_branch)
    institute_name = branch_branding['class_name']
    
    # Branch Logo fallback
    active_logo_url = branch_branding['logo_url']

    if active_logo_url and active_logo_url.startswith('/api/uploads/'):
        active_logo_url = active_logo_url.replace('/api/uploads/', '/media/')

    # Validate file exists on disk if it points to /media/ (with fast cache)
    if active_logo_url and active_logo_url.startswith('/media/'):
        cache_key = f"logo_exists_{active_logo_url}"
        exists_on_disk = safe_cache_get(cache_key)
        if exists_on_disk is None:
            rel_p = active_logo_url[len('/media/'):]
            full_p = os.path.join(django_settings.MEDIA_ROOT, rel_p.replace('/', os.sep))
            exists_on_disk = os.path.exists(full_p)
            safe_cache_set(cache_key, exists_on_disk, 600)
        if not exists_on_disk:
            active_logo_url = '/static/images/logo-master.png'
    elif not active_logo_url:
        active_logo_url = '/static/images/logo-master.png'

    # 4. UI Preferences
    is_sidebar_collapsed = bool(request.session.get('is_sidebar_collapsed', False))

    # 5. WhatsApp Configuration & Visibility Controls
    whatsapp_enabled = settings_dict.get('whatsapp_enabled', 'true') != 'false'
    whatsapp_mode = settings_dict.get('whatsapp_mode', 'both')  # 'automatic' | 'manual' | 'both' | 'off'
    whatsapp_show_manual_buttons = whatsapp_enabled and (whatsapp_mode in ('manual', 'both'))
    whatsapp_auto_enabled = whatsapp_enabled and (whatsapp_mode in ('automatic', 'both'))

    return {
        'branches': branches,
        'sessions': sessions,
        'selected_branch_id': selected_branch_id,
        'selected_branch': selected_branch,
        'selected_session_id': selected_session_id,
        'selected_session': selected_session,
        'institute_settings': settings_dict,
        'active_branch_branding': branch_branding,
        'institute_name': institute_name,
        'active_logo_url': active_logo_url,
        'current_user': current_user,
        'is_developer': is_developer,
        'is_class_owner': is_class_owner,
        'is_branch_manager': is_branch_manager,
        'assigned_branch': current_user.branch if (current_user and is_branch_manager) else None,
        'user_permissions': user_permissions,
        'is_sidebar_collapsed': is_sidebar_collapsed,
        'whatsapp_enabled': whatsapp_enabled,
        'whatsapp_mode': whatsapp_mode,
        'whatsapp_show_manual_buttons': whatsapp_show_manual_buttons,
        'whatsapp_auto_enabled': whatsapp_auto_enabled,
    }

