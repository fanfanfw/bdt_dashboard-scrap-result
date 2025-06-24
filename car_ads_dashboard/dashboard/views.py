from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .decorators import group_required, user_is_owner_or_admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from .tasks import sync_data_task
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q, Avg
from .models import CarsMudahmy, CarsCarlistmy
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_GET
from django.db import models
import pandas as pd

class CustomLoginView(LoginView):
    form_class = AuthenticationForm
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for visible in form.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
            visible.field.widget.attrs['placeholder'] = visible.label
        return form
    
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

    brand = request.GET.get('brand')
    year = request.GET.get('year')

    if source == 'carlistmy':
        from .models import CarsCarlistmy as CarModel
    else:
        from .models import CarsMudahmy as CarModel

    queryset = CarModel.objects.filter(status__in=['active', 'sold'])
    if brand:
        queryset = queryset.filter(brand=brand)
    if year:
        try:
            year_int = int(year)
            queryset = queryset.filter(year=year_int)
        except ValueError:
            pass

    # Statistik umum
    total_all = queryset.count()
    total_active = queryset.filter(status='active').count()
    total_sold = queryset.filter(status='sold').count()
    total_brand = queryset.values('brand').distinct().count()
    avg_price = queryset.aggregate(avg=Avg('price'))['avg'] or 0

    # Top 10 brand berdasarkan total listing (active+sold)
    top_ads = (
        queryset.values('brand')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    chart_labels_ads = [item['brand'] or 'Unknown' for item in top_ads[:10]]
    chart_data_ads = [item['total'] for item in top_ads[:10]]

    # Top 10 brand berdasarkan penjualan terbanyak (status='sold')
    sold_queryset = queryset.filter(status='sold')
    top_sold = (
        sold_queryset.values('brand')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    chart_labels_sold = [item['brand'] or 'Unknown' for item in top_sold[:10]]
    chart_data_sold = [item['total'] for item in top_sold[:10]]

    # Distribusi Tahun Produksi
    year_distribution = (
        queryset.values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )
    years_hist_labels = [item['year'] or 'Unknown' for item in year_distribution]
    years_hist_data = [item['count'] for item in year_distribution]

    # Distribusi Transmisi
    transmission_distribution = (
        queryset.values('transmission')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    transmission_labels = [item['transmission'] or 'Unknown' for item in transmission_distribution]
    transmission_data = [item['count'] for item in transmission_distribution]

    # Distribusi Kapasitas Kursi
    seat_distribution = (
        queryset.values('seat_capacity')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    seat_labels = [item['seat_capacity'] or 'Unknown' for item in seat_distribution]
    seat_data = [item['count'] for item in seat_distribution]

    # Data untuk filter dropdown
    brands = CarModel.objects.filter(status__in=['active', 'sold']).values_list('brand', flat=True).distinct().order_by('brand')
    # Dropdown years hanya tampilkan tahun yang ada datanya sesuai filter brand/model/variant
    years_qs = queryset.values_list('year', flat=True).distinct().order_by('-year')
    years = [y for y in years_qs if y is not None]

    context = {
        'username': username,
        'source': source,
        'total_all': total_all,
        'total_active': total_active,
        'total_sold': total_sold,
        'total_brand': total_brand,
        'avg_price': int(avg_price),
        'brands': brands,
        'years': years,

        'chart_labels_ads': chart_labels_ads,
        'chart_data_ads': chart_data_ads,
        'chart_labels_sold': chart_labels_sold,
        'chart_data_sold': chart_data_sold,

        'years_hist_labels': years_hist_labels,
        'years_hist_data': years_hist_data,
        'transmission_labels': transmission_labels,
        'transmission_data': transmission_data,
        'seat_labels': seat_labels,
        'seat_data': seat_data,
    }
    return render(request, 'dashboard/user_dashboard.html', context)

@login_required
@group_required('User')
@user_is_owner_or_admin
@require_GET
def user_dashboard_data(request, username):
    source = request.GET.get('source', 'mudahmy')
    brand = request.GET.get('brand')
    year = request.GET.get('year')

    if source not in ['mudahmy', 'carlistmy']:
        source = 'mudahmy'

    if source == 'carlistmy':
        from .models import CarsCarlistmy as CarModel
    else:
        from .models import CarsMudahmy as CarModel

    queryset = CarModel.objects.filter(status__in=['active', 'sold'])
    if brand:
        queryset = queryset.filter(brand=brand)
    if year:
        queryset = queryset.filter(year=year)

    top_ads = (
        queryset.values('brand')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    chart_labels = [item['brand'] or 'Unknown' for item in top_ads[:10]]
    chart_data = [item['total'] for item in top_ads[:10]]

    total_active = queryset.filter(status='active').count()
    total_sold = queryset.filter(status='sold').count()
    avg_price = queryset.aggregate(avg=models.Avg('price'))['avg'] or 0

    return JsonResponse({
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'total_active': total_active,
        'total_sold': total_sold,
        'avg_price': int(avg_price),
    })

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
def user_dataListing(request, username):
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

    return render(request, 'dashboard/user_dataListing.html', {
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

        start = int(request.GET.get('start', 0))
        length = int(request.GET.get('length', 10))
        
        total_records = queryset.count()
        cars = queryset[start:start+length]
        
        data = []
        for car in cars:
            price_histories = list(car.price_histories.order_by('changed_at'))
            starting = price_histories[0].old_price if price_histories else None
            
            sold_duration = '-'
            if car.status == 'sold' and car.sold_at and car.created_at:
                duration = (car.sold_at.date() - car.created_at.date()).days
                if duration < 0:
                    duration = 0
                sold_duration = f"{duration} hari"
            
            data.append({
                'img': car.gambar[0] if car.gambar else '',
                'year': car.year or '-',
                'brand': car.brand or '-',
                'model': car.model or '-',
                'variant': car.variant or '-',
                'transmission': car.transmission or '-',
                'mileage': f"{car.mileage:,}" if car.mileage else '-',
                'starting': starting if starting is not None else '-',
                'latest': car.price if car.price is not None else '-',
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
        return JsonResponse({'error': str(e)}, status=500)

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

@login_required
def get_scatter_data(request, username):
    source = request.GET.get('source', 'mudahmy')
    brand = request.GET.get('brand')
    model = request.GET.get('model')
    variant = request.GET.get('variant')
    year = request.GET.get('year')

    if source == 'carlistmy':
        CarModel = CarsCarlistmy
    else:
        CarModel = CarsMudahmy

    if not brand:
        return JsonResponse({'error': 'Brand is required'}, status=400)

    queryset = CarModel.objects.filter(status__in=['active', 'sold'], brand=brand)
    if model:
        queryset = queryset.filter(model=model)
    if variant:
        queryset = queryset.filter(variant=variant)
    if year:
        try:
            year_int = int(year)
            queryset = queryset.filter(year=year_int)
        except ValueError:
            pass

    queryset = queryset.filter(price__gt=0, mileage__gt=0)

    data = list(
        queryset.values('brand', 'model', 'variant', 'price', 'mileage')[:500]
    )

    return JsonResponse(data, safe=False)

@login_required
def get_avg_mileage_per_year(request, username):
    source = request.GET.get('source', 'mudahmy')
    brand = request.GET.get('brand')
    model = request.GET.get('model')
    variant = request.GET.get('variant')
    year = request.GET.get('year')

    if source == 'carlistmy':
        CarModel = CarsCarlistmy
    else:
        CarModel = CarsMudahmy
    
    qs = CarModel.objects.filter(status__in=['active', 'sold'], mileage__isnull=False, year__isnull=False)

    if brand:
        qs = qs.filter(brand=brand)
    if model:
        qs = qs.filter(model=model)
    if variant:
        qs = qs.filter(variant=variant)
    if year:
        try:
            year_int = int(year)
            qs = qs.filter(year=year_int)
        except ValueError:
            pass

    data = qs.values('year').annotate(avg_mileage=models.Avg('mileage')).order_by('year')

    result = {
        'years': [item['year'] for item in data],
        'avg_mileages': [round(item['avg_mileage'], 2) if item['avg_mileage'] else 0 for item in data],
    }
    return JsonResponse(result)

@login_required
def get_feature_correlation(request, username):
    source = request.GET.get('source', 'mudahmy')
    if source == 'carlistmy':
        CarModel = CarsCarlistmy
    else:
        CarModel = CarsMudahmy

    qs = CarModel.objects.filter(status__in=['active', 'sold']).values('price', 'mileage', 'year')
    df = pd.DataFrame(list(qs))

    if df.empty:
        return JsonResponse({'error': 'No data'}, status=404)

    corr = df.corr()
    corr_dict = corr.round(3).to_dict()

    return JsonResponse({'correlation': corr_dict})

@login_required
def get_years(request):
    source = request.GET.get('source', 'mudahmy')
    brand = request.GET.get('brand')
    model = request.GET.get('model')
    variant = request.GET.get('variant')

    if source == 'carlistmy':
        from .models import CarsCarlistmy as CarModel
    else:
        from .models import CarsMudahmy as CarModel

    qs = CarModel.objects.filter(status__in=['active', 'sold'])
    if brand:
        qs = qs.filter(brand=brand)
    if model:
        qs = qs.filter(model=model)
    if variant:
        qs = qs.filter(variant=variant)

    years = list(qs.values_list('year', flat=True).distinct().order_by('-year'))
    years = [y for y in years if y is not None]
    return JsonResponse({'years': years})