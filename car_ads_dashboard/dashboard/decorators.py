from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden

def group_required(group_name):
    def in_group(user):
        if not user.is_authenticated:
            return False
        
        # Super Admin can access all group-required views
        if user.groups.filter(name='Super Admin').exists():
            return True
            
        return user.groups.filter(name=group_name).exists()
    return user_passes_test(in_group)

def super_admin_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and user.groups.filter(name='Super Admin').exists():
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You don't have permission to access this page. Super Admin access required.")
    return _wrapped_view

def user_is_owner_or_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        username = kwargs.get('username')
        if user.is_authenticated:
            # Super Admin has access to everything
            if user.groups.filter(name='Super Admin').exists():
                return view_func(request, *args, **kwargs)
            # Admin has access to admin pages
            elif user.groups.filter(name='Admin').exists():
                return view_func(request, *args, **kwargs)
            # User can only access their own page
            elif username == user.username:
                return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You don't have permission to access this page.")
    return _wrapped_view
