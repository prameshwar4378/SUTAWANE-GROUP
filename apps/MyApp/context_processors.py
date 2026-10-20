from .models import Branch, AcademicSession, SystemSetting, User


def global_context(request):
    """
    Global Context Processor for Sutawane Classes Management Software.
    Provides session-persistent branch, session, institute branding, and user state.
    """
    # 1. Active Branches & Selected Branch
    branches = list(Branch.objects.filter(is_active=True).order_by('name'))
    selected_branch_id = request.session.get('selected_branch_id', 'ALL')
    
    selected_branch = None
    if selected_branch_id and selected_branch_id != 'ALL':
        selected_branch = next((b for b in branches if str(b.id) == str(selected_branch_id)), None)
        if not selected_branch:
            selected_branch_id = 'ALL'

    # 2. Active Academic Sessions & Selected Session
    sessions = list(AcademicSession.objects.filter(isActive=True).order_by('-start_date'))
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

    # 3. System Branding & Settings
    settings_qs = SystemSetting.objects.all()
    settings_dict = {s.key: s.value for s in settings_qs}
    institute_name = settings_dict.get('institute_name', 'Sutawane Classes')
    
    # Branch Logo fallback
    import os
    from django.conf import settings as django_settings

    active_logo_url = None
    if selected_branch and selected_branch.logo_url:
        active_logo_url = selected_branch.logo_url
    elif settings_dict.get('logo_url'):
        active_logo_url = settings_dict.get('logo_url')

    if active_logo_url and active_logo_url.startswith('/api/uploads/'):
        active_logo_url = active_logo_url.replace('/api/uploads/', '/media/')

    # Validate file exists on disk if it points to /media/
    if active_logo_url and active_logo_url.startswith('/media/'):
        rel_p = active_logo_url[len('/media/'):]
        full_p = os.path.join(django_settings.MEDIA_ROOT, rel_p.replace('/', os.sep))
        if not os.path.exists(full_p):
            active_logo_url = '/static/images/logo-master.png'
    elif not active_logo_url:
        active_logo_url = '/static/images/logo-master.png'

    # 4. User Session Context
    user_id = request.session.get('user_id')
    current_user = None
    if user_id:
        current_user = User.objects.filter(id=user_id, is_active=True).first()
    if not current_user:
        # Default to Class Owner account for preview / development if not yet logged in
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
