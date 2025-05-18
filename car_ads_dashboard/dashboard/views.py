from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .decorators import group_required, user_is_owner_or_admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from .tasks import sync_data_task
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import connection

class CustomLoginView(LoginView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.groups.filter(name='Admin').exists():
                return redirect('admin_dashboard', username=request.user.username)
            elif request.user.groups.filter(name='User').exists():
                return redirect('user_dashboard', username=request.user.username)
            else:
                return redirect('login')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        user = self.request.user
        if user.groups.filter(name='Admin').exists():
            return reverse('admin_dashboard', kwargs={'username': user.username})
        elif user.groups.filter(name='User').exists():
            return reverse('user_dashboard', kwargs={'username': user.username})
        else:
            return super().get_success_url()

@login_required
@group_required('User')
@user_is_owner_or_admin
def user_dashboard(request, username):
    context = {
        'username': request.user.username,
        'role': 'User',
        'message': 'Welcome to User Dashboard! Here you can view the analysis.'
    }
    return render(request, 'dashboard/user_dashboard.html', context)

@login_required
@group_required('Admin')
@user_is_owner_or_admin
def admin_dashboard(request, username):
    context = {
        'username': request.user.username,
        'role': 'Admin',
        'message': 'Welcome to Admin Dashboard! Here you can manage dashboard settings.'
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

@staff_member_required
@csrf_exempt  # Karena pake JS fetch, pastikan csrf token sudah dikirim
def trigger_sync(request, username):
    if request.method == 'POST':
        try:
            sync_data_task.delay()
            return JsonResponse({'status': 'started', 'message': 'Sinkronisasi dimulai'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'method not allowed'}, status=405)

@login_required
@group_required('User')
@user_is_owner_or_admin
def api_price_vs_mileage(request, username):
    # Ambil filter dari query params
    brand = request.GET.get('brand')
    model = request.GET.get('model')
    variant = request.GET.get('variant')
    year = request.GET.get('year')

    params = []
    query = """
        SELECT brand, price, mileage, year
        FROM dashboard_carscarlistmy
        WHERE 1=1
    """

    if brand:
        query += " AND brand ILIKE %s"
        params.append(f"%{brand}%")
    if model:
        query += " AND model ILIKE %s"
        params.append(f"%{model}%")
    if variant:
        query += " AND variant ILIKE %s"
        params.append(f"%{variant}%")
    if year and year.isdigit():
        query += " AND year = %s"
        params.append(int(year))

    query += " ORDER BY brand, price"

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    data = [
        {"brand": row[0], "price": row[1], "mileage": row[2], "year": row[3]}
        for row in rows
    ]

    return JsonResponse({"data": data})