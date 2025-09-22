from django.shortcuts import redirect, render

def group_required(group_name):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            user = request.user

            # Check if user is authenticated
            if not user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            # Super Admin can access all group-required views
            if user.groups.filter(name='Super Admin').exists():
                return view_func(request, *args, **kwargs)

            # Check if user has required group
            if user.groups.filter(name=group_name).exists():
                return view_func(request, *args, **kwargs)

            # User doesn't have required group - show 403 instead of redirecting to login
            return render(request, '403.html', status=403)

        return _wrapped_view
    return decorator

def super_admin_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and user.groups.filter(name='Super Admin').exists():
            return view_func(request, *args, **kwargs)
        return render(request, '403.html', status=403)
    return _wrapped_view

def user_is_owner_or_admin(view_func):
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        username = kwargs.get('username')
        if user.is_authenticated:
            # Super Admin has access to everything
            if user.groups.filter(name='Super Admin').exists():
                return view_func(request, *args, **kwargs)
            # Admin and regular users can only access their own page
            elif username == user.username:
                return view_func(request, *args, **kwargs)
            # If admin tries to access other admin's page, redirect to their own
            elif user.groups.filter(name='Admin').exists():
                view_name = request.resolver_match.url_name
                return redirect(view_name, username=user.username)
        return render(request, '403.html', status=403)
    return _wrapped_view

def strict_owner_only(view_func):
    """
    Decorator that only allows user to access their own pages
    Even Super Admin must use their own username
    """
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        username = kwargs.get('username')
        if user.is_authenticated and username == user.username:
            return view_func(request, *args, **kwargs)
        elif user.is_authenticated:
            # Redirect to their own page
            view_name = request.resolver_match.url_name
            return redirect(view_name, username=user.username)
        return render(request, '403.html', status=403)
    return _wrapped_view
