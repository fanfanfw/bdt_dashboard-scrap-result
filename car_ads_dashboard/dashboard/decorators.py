from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponseForbidden

def group_required(group_name):
    def in_group(user):
        return user.is_authenticated and user.groups.filter(name=group_name).exists()
    return user_passes_test(in_group)

def user_is_owner_or_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        username = kwargs.get('username')
        if user.is_authenticated:
            if user.groups.filter(name='Admin').exists():
                return view_func(request, *args, **kwargs)
            elif username == user.username:
                return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You don't have permission to access this page.")
    return _wrapped_view
