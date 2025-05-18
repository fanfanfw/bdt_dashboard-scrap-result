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
from django.db.models import Count

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
    source = request.GET.get('source', 'mudahmy')
    if source not in ['mudahmy', 'carlistmy']:
        source = 'mudahmy'

    if source == 'carlistmy':
        from .models import CarsCarlistmy as CarModel
    else:
        from .models import CarsMudahmy as CarModel

    # Ambil 10 brand/model dengan iklan terbanyak
    top_ads = (
        CarModel.objects.values('brand')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    chart_labels = [item['brand'] or 'Unknown' for item in top_ads[:10]]
    chart_data = [item['total'] for item in top_ads[:10]]
    top_ads_list = [(item['brand'] or 'Unknown', item['total']) for item in top_ads]

    context = {
        'username': request.user.username,
        'role': 'User',
        'message': f'Welcome to User Dashboard! Showing data from {source}.',
        'source': source,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'top_ads': top_ads_list,  # <-- gunakan ini di template
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
def data_listing(request, username):
    # Contoh: ambil semua data dari CarsCarlistmy
    from .models import CarsCarlistmy
    listings = CarsCarlistmy.objects.all()[:100]  # batasi 100 data untuk contoh
    return render(request, 'dashboard/data_listing.html', {
        'username': username,
        'listings': listings,
    })