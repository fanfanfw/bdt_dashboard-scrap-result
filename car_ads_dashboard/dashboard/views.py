from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .decorators import group_required, user_is_owner_or_admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from .tasks import sync_data_task
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import connection
from django.db.models import Count
from django.core.paginator import Paginator
from django.db.models import Q
from .models import CarsMudahmy, CarsCarlistmy

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
    source = request.GET.get('source', 'mudahmy')
    if source not in ['mudahmy', 'carlistmy']:
        source = 'mudahmy'

    if source == 'carlistmy':
        from .models import CarsCarlistmy as CarModel
    else:
        from .models import CarsMudahmy as CarModel

    # Get unique brands
    brands = CarModel.objects.filter(
        status='active'
    ).values_list('brand', flat=True).distinct().order_by('brand')
    
    # Get unique years
    years = CarModel.objects.filter(
        status='active'
    ).values_list('year', flat=True).distinct().order_by('-year')

    # Hanya ambil total data
    total_data = CarModel.objects.filter(status__in=['active', 'sold']).count()

    return render(request, 'dashboard/data_listing.html', {
        'username': username,
        'source': source,
        'total_data': total_data,
        'brands': brands,
        'years': years,
    })

@login_required
def get_models(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel
        
        # Hapus filter status='active'
        models = CarModel.objects.filter(
            brand=brand
        ).values_list('model', flat=True).distinct().order_by('model')
        
        models_list = list(models)
        print(f"Brand: {brand}, Models found: {models_list}")  # Debug print
        
        return JsonResponse({'models': models_list})
    except Exception as e:
        print(f"Error in get_models: {str(e)}")  # Debug print
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_variants(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel
        
        variants = CarModel.objects.filter(
            brand=brand,
            model=model,
            status='active'
        ).values_list('variant', flat=True).distinct().order_by('variant')
        
        variants_list = list(variants)
        print(f"Brand: {brand}, Model: {model}, Variants found: {variants_list}")  # Debug print
        
        return JsonResponse({'variants': variants_list})
    except Exception as e:
        print(f"Error in get_variants: {str(e)}")  # Debug print
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_listing_data(request, username):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')
        
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel

        queryset = CarModel.objects.filter(status__in=['active', 'sold'])
        
        # Apply filters
        if brand:
            queryset = queryset.filter(brand=brand)
        if model:
            queryset = queryset.filter(model=model)
        if variant:
            queryset = queryset.filter(variant=variant)
        if year:
            queryset = queryset.filter(year=year)

        # Handle DataTables parameters
        start = int(request.GET.get('start', 0))
        length = int(request.GET.get('length', 10))
        
        total_records = queryset.count()
        cars = queryset[start:start+length]
        
        data = []
        for car in cars:
            price_histories = list(car.price_histories.order_by('changed_at'))
            starting = price_histories[0].old_price if price_histories else '-'
            
            # Calculate sold duration (sold_at - created_at), ensure non-negative
            sold_duration = '-'
            if car.status == 'sold' and car.sold_at and car.created_at:
                duration = (car.sold_at.date() - car.created_at.date()).days
                if duration < 0:
                    duration = 0  # minimal 0 hari jika tanggal tidak valid
                sold_duration = f"{duration} hari"
            
            data.append({
                'img': f'<img src="{car.gambar[0]}" alt="img" style="width:70px; height:50px; object-fit:cover; border-radius:6px;">' if car.gambar else '-',
                'year': car.year or '-',
                'brand': car.brand or '-',
                'model': car.model or '-',
                'variant': car.variant or '-',
                'transmission': car.transmission or '-',
                'mileage': f"{car.mileage:,}" if car.mileage else '-',
                'starting': f"RM {starting:,}" if isinstance(starting, int) else '-',
                'latest': f"RM {car.price:,}" if car.price else '-',
                'created_at': car.created_at.strftime("%Y-%m-%d") if car.created_at else '-',
                'status': car.status,
                'sold_duration': sold_duration
            })

        return JsonResponse({
            'draw': int(request.GET.get('draw', 1)),
            'recordsTotal': total_records,
            'recordsFiltered': total_records,
            'data': data,
        })
    
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
def get_brand_stats(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        if source == 'carlistmy':
            CarModel = CarsCarlistmy
        else:
            CarModel = CarsMudahmy
        
        brand_stats = (
            CarModel.objects
            .filter(status__in=['active', 'sold'])
            .values('brand')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        return JsonResponse({'brands': list(brand_stats)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_model_stats(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        if source == 'carlistmy':
            CarModel = CarsCarlistmy
        else:
            CarModel = CarsMudahmy

        model_stats = (
            CarModel.objects
            .filter(status__in=['active', 'sold'], brand=brand)
            .values('model')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        return JsonResponse({'models': list(model_stats)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
