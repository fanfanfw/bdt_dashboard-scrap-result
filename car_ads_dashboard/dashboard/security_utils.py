"""
Security utilities for dashboard views
"""
from django.shortcuts import redirect
from django.http import JsonResponse


def validate_username_access(request, username, view_name=None, is_api=False):
    """
    Validate that the user can only access their own profile/pages
    
    Args:
        request: Django request object
        username: Username from URL parameter
        view_name: View name for redirect (optional)
        is_api: Whether this is an API endpoint
        
    Returns:
        True if access is allowed, redirect/JsonResponse if not
    """
    if not request.user.is_authenticated:
        if is_api:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return redirect('login')
    
    # Super Admin can access any page
    if request.user.groups.filter(name='Super Admin').exists():
        return True
    
    # Regular users and admins can only access their own pages
    if request.user.username != username:
        if is_api:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Redirect to their own page if view_name is provided
        if view_name:
            return redirect(view_name, username=request.user.username)
        else:
            # Default redirect based on user role
            if request.user.groups.filter(name='Admin').exists():
                return redirect('admin_dashboard', username=request.user.username)
            else:
                return redirect('user_dashboard', username=request.user.username)
    
    return True


def check_admin_access(user):
    """
    Check if user has admin access
    """
    return (user.is_authenticated and 
            (user.groups.filter(name__in=['Admin', 'Super Admin']).exists() or user.is_staff))


def check_super_admin_access(user):
    """
    Check if user has super admin access
    """
    return (user.is_authenticated and 
            (user.groups.filter(name='Super Admin').exists() or user.is_superuser))
