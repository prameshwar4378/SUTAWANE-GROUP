import os
from django.conf import settings as django_settings
from django.core.cache import cache
from .models import Branch, AcademicSession, SystemSetting, User


def get_cached_branches():
    """Returns active branches cached in RAM for 60s."""
    branches = cache.get('global_active_branches')
    if branches is None:
        branches = list(Branch.objects.filter(is_active=True).order_by('name'))
        cache.set('global_active_branches', branches, 60)
    return branches


def get_cached_sessions():
    """Returns active academic sessions cached in RAM for 60s."""
    sessions = cache.get('global_active_sessions')
    if sessions is None:
        sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
        cache.set('global_active_sessions', sessions, 60)
    return sessions


def get_cached_settings_dict():
    """Returns system settings dictionary cached in RAM for 60s."""
    s_dict = cache.get('global_system_settings_dict')
    if s_dict is None:
        settings_qs = SystemSetting.objects.all()
        s_dict = {s.key: s.value for s in settings_qs}
        cache.set('global_system_settings_dict', s_dict, 60)
    return s_dict


def invalidate_global_context_cache():
    """Immediately clears in-memory caches for branches, sessions, and system settings."""
    cache.delete('global_active_branches')
    cache.delete('global_active_sessions')
    cache.delete('global_system_settings_dict')



def global_context(request):
    """
    High-Performance Global Context Processor for Sutawane Classes Management Software.
    Provides session-persistent branch, session, institute branding, and user state
    using memory caching to eliminate duplicate database and disk operations.
    """
    # 1. Active Branches & Selected Branch (In-Memory Cached)
    branches = get_cached_branches()
    selected_branch_id = request.session.get('selected_branch_id', 'ALL')
    
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

    # 3. System Branding & Settings (In-Memory Cached)
    settings_dict = get_cached_settings_dict()
    institute_name = settings_dict.get('institute_name', 'Sutawane Classes')
    
    # Branch Logo fallback
    active_logo_url = None
    if selected_branch and selected_branch.logo_url:
        active_logo_url = selected_branch.logo_url
    elif settings_dict.get('logo_url'):
        active_logo_url = settings_dict.get('logo_url')

    if active_logo_url and active_logo_url.startswith('/api/uploads/'):
        active_logo_url = active_logo_url.replace('/api/uploads/', '/media/')

    # Validate file exists on disk if it points to /media/ (with fast cache)
    if active_logo_url and active_logo_url.startswith('/media/'):
        cache_key = f"logo_exists_{active_logo_url}"
        exists_on_disk = cache.get(cache_key)
        if exists_on_disk is None:
            rel_p = active_logo_url[len('/media/'):]
            full_p = os.path.join(django_settings.MEDIA_ROOT, rel_p.replace('/', os.sep))
            exists_on_disk = os.path.exists(full_p)
            cache.set(cache_key, exists_on_disk, 300)
        if not exists_on_disk:
            active_logo_url = '/static/images/logo-master.png'
    elif not active_logo_url:
        active_logo_url = '/static/images/logo-master.png'

    # 4. User Session Context (Reuse request.current_user if middleware already resolved it)
    current_user = getattr(request, 'current_user', None)
    if not current_user:
        user_id = request.session.get('user_id')
        if user_id:
            current_user = User.objects.filter(id=user_id, is_active=True).first()
        if not current_user:
            current_user = User.objects.filter(role='CLASS_OWNER', is_active=True).first()

    is_developer = current_user.role == 'DEVELOPER' if current_user else False

    # 5. UI Preferences
    is_sidebar_collapsed = request.session.get('is_sidebar_collapsed', False)

    return {
        'branches': branches,
        'sessions': sessions,
        'selected_branch_id': selected_branch_id,
        'selected_branch': selected_branch,
        'selected_session_id': selected_session_id,
        'selected_session': selected_session,
        'institute_settings': settings_dict,
        'institute_name': institute_name,
        'active_logo_url': active_logo_url,
        'current_user': current_user,
        'is_developer': is_developer,
        'is_sidebar_collapsed': is_sidebar_collapsed,
    }
