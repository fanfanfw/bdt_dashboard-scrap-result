"""
Security middleware for dashboard URL validation
"""
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.template.response import TemplateResponse


class URLSecurityMiddleware:
    """
    Middleware to ensure users can only access URLs with their own username
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # URLs that require username validation
        self.protected_patterns = [
            '/dashboard/user/',
            '/dashboard/admin/',
        ]
    
    def __call__(self, request):
        # Skip validation for non-authenticated users
        if not request.user.is_authenticated:
            response = self.get_response(request)
            return response

        # Skip validation for static files, API endpoints, and non-dashboard URLs
        if (request.path.startswith('/static/') or
            request.path.startswith('/api/') or
            request.path.startswith('/accounts/') or
            request.path.startswith('/admin/') or
            not request.path.startswith('/dashboard/')):
            response = self.get_response(request)
            return response

        # Check if this is a protected URL
        path = request.path
        is_protected = any(path.startswith(pattern) for pattern in self.protected_patterns)

        if is_protected:
            # Extract username from URL
            path_parts = path.strip('/').split('/')
            if len(path_parts) >= 3:
                url_username = path_parts[2]  # /dashboard/admin/username/...

                # Allow Super Admin to access any URL
                if request.user.groups.filter(name='Super Admin').exists():
                    pass  # Super Admin can access anything
                # Regular users and admins must use their own username
                elif url_username != request.user.username:
                    # Only redirect if the username is actually different and valid
                    if url_username and url_username != request.user.username:
                        # Determine correct redirect based on user role
                        if request.user.groups.filter(name='Admin').exists():
                            # Redirect admin to their own admin page
                            corrected_path = path.replace(f'/dashboard/admin/{url_username}/', f'/dashboard/admin/{request.user.username}/')
                            return redirect(corrected_path)
                        elif request.user.groups.filter(name='User').exists():
                            # Redirect user to their own user page
                            corrected_path = path.replace(f'/dashboard/user/{url_username}/', f'/dashboard/user/{request.user.username}/')
                            return redirect(corrected_path)
                        else:
                            # Unknown user role, deny access
                            return TemplateResponse(request, '403.html', status=403)

        response = self.get_response(request)
        return response
