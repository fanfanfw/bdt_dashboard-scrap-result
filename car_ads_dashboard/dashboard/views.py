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
from .models import CarsMudahmy, CarsCarlistmy, PriceHistoryMudahmy, PriceHistoryCarlistmy
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_GET
from django.db import models
import pandas as pd
from datetime import date
import json
import traceback

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
    # Tambah: total data terbaru hari ini
    total_today = queryset.filter(information_ads_date=date.today()).count()

    # Top 10 brand berdasarkan total listing (active+sold)
    top_ads = (
        queryset.values('brand')
        .annotate(total=Count('id'))
        .order_by('-total')
    )
    top_10_brands_labels = [item['brand'] or 'Unknown' for item in top_ads[:10]]
    top_10_brands_data = [item['total'] for item in top_ads[:10]]

    # Data untuk brand chart (active vs sold)
    brand_stats = (
        queryset.values('brand')
        .annotate(
            active_count=Count('id', filter=Q(status='active')),
            sold_count=Count('id', filter=Q(status='sold'))
        )
        .order_by('-active_count')
    )
    brand_labels = [item['brand'] or 'Unknown' for item in brand_stats[:10]]
    brand_active_data = [item['active_count'] for item in brand_stats[:10]]
    brand_sold_data = [item['sold_count'] for item in brand_stats[:10]]

    # Distribusi Tahun Produksi
    year_distribution = (
        queryset.values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )
    year_labels = [str(item['year']) if item['year'] else 'Unknown' for item in year_distribution]
    year_data = [item['count'] for item in year_distribution]

    # Harga rata-rata per brand
    price_stats = (
        queryset.values('brand')
        .annotate(avg_price=Avg('price'))
        .order_by('-avg_price')
    )
    price_labels = [item['brand'] or 'Unknown' for item in price_stats[:10]]
    price_data = [int(item['avg_price']) if item['avg_price'] else 0 for item in price_stats[:10]]

    # Distribusi Transmisi
    transmission_distribution = (
        queryset.values('transmission')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    transmission_labels = [item['transmission'] or 'Unknown' for item in transmission_distribution]
    transmission_data = [item['count'] for item in transmission_distribution]

    # Distribusi Fuel Type
    fuel_distribution = (
        queryset.values('fuel_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    fuel_labels = [item['fuel_type'] or 'Unknown' for item in fuel_distribution]
    fuel_data = [item['count'] for item in fuel_distribution]

    # Distribusi Engine CC
    engine_distribution = (
        queryset.values('engine_cc')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    engine_labels = [str(item['engine_cc']) if item['engine_cc'] else 'Unknown' for item in engine_distribution[:10]]
    engine_data = [item['count'] for item in engine_distribution[:10]]

    # Data untuk filter dropdown
    brands = CarModel.objects.filter(status__in=['active', 'sold']).values_list('brand', flat=True).distinct().order_by('brand')
    # Dropdown years hanya tampilkan tahun yang ada datanya sesuai filter brand/model/variant
    years_qs = queryset.values_list('year', flat=True).distinct().order_by('-year')
    years = [y for y in years_qs if y is not None]

    # Data untuk scatter plot brands
    scatter_brands = CarModel.objects.filter(status__in=['active', 'sold']).values_list('brand', flat=True).distinct().order_by('brand')

    context = {
        'username': username,
        'source': source,
        'total_all': total_all,
        'total_active': total_active,
        'total_sold': total_sold,
        'total_brand': total_brand,
        'avg_price': int(avg_price),
        'total_today': total_today,
        'brands': brands,
        'years': years,
        'scatter_brands': scatter_brands,

        # Chart data
        'top_10_brands_labels': top_10_brands_labels,
        'top_10_brands_data': top_10_brands_data,
        'brand_labels': brand_labels,
        'brand_active_data': brand_active_data,
        'brand_sold_data': brand_sold_data,
        'year_labels': year_labels,
        'year_data': year_data,
        'price_labels': price_labels,
        'price_data': price_data,
        'transmission_labels': transmission_labels,
        'transmission_data': transmission_data,
        'fuel_labels': fuel_labels,
        'fuel_data': fuel_data,
        'engine_labels': engine_labels,
        'engine_data': engine_data,
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
        
        return JsonResponse(models_list, safe=False)
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
        
        return JsonResponse(variants_list, safe=False)
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
            from .models import PriceHistoryCarlistmy as PriceHistoryModel
        else:
            from .models import CarsMudahmy as CarModel
            from .models import PriceHistoryMudahmy as PriceHistoryModel

        queryset = CarModel.objects.filter(status__in=['active', 'sold'])
        
        # Apply filters
        if brand:
            queryset = queryset.filter(brand=brand)
        if model:
            queryset = queryset.filter(model=model)
        if variant:
            queryset = queryset.filter(variant=variant)
        if year:
            try:
                year_int = int(year)
                queryset = queryset.filter(year=year_int)
            except (ValueError, TypeError):
                pass

        # Handle DataTables parameters
        start = int(request.GET.get('start', 0))
        length = int(request.GET.get('length', 10))
        
        # Search functionality
        search_value = request.GET.get('search[value]', '')
        if search_value:
            queryset = queryset.filter(
                Q(brand__icontains=search_value) |
                Q(model__icontains=search_value) |
                Q(variant__icontains=search_value) |
                Q(year__icontains=search_value)
            )
        
        # Ordering
        order_column = int(request.GET.get('order[0][column]', 1))
        order_dir = request.GET.get('order[0][dir]', 'desc')
        order_fields = ['images', 'year', 'brand', 'model', 'variant', 'transmission', 'mileage', 'price', 'price', 'created_at', 'status', 'sold_at']
        
        if 0 <= order_column < len(order_fields):
            order_field = order_fields[order_column]
            if order_dir == 'desc':
                order_field = '-' + order_field
            try:
                queryset = queryset.order_by(order_field)
            except:
                queryset = queryset.order_by('-created_at')
        else:
            queryset = queryset.order_by('-created_at')
        
        total_records = queryset.count()
        cars = queryset[start:start+length]
        
        data = []
        for car in cars:
            # Get price history for starting price
            try:
                if source == 'carlistmy':
                    price_histories = PriceHistoryModel.objects.filter(
                        car=car.listing_url
                    ).order_by('changed_at')
                else:
                    price_histories = PriceHistoryModel.objects.filter(
                        car=car.listing_url
                    ).order_by('changed_at')
                
                starting_price = price_histories.first().old_price if price_histories.exists() else car.price
            except:
                starting_price = car.price
            
            # Calculate sold duration
            sold_duration = '-'
            if car.status == 'sold' and car.sold_at and car.created_at:
                try:
                    duration = (car.sold_at.date() - car.created_at.date()).days
                    if duration < 0:
                        duration = 0
                    sold_duration = f"{duration} hari"
                except:
                    sold_duration = '-'
            
            # Get first image
            first_image = ''
            if car.images:
                try:
                    # Try to parse as JSON array
                    import json
                    images_list = json.loads(car.images)
                    if isinstance(images_list, list) and images_list:
                        first_image = images_list[0]
                except:
                    # If not JSON, treat as single image URL
                    first_image = car.images
            
            data.append({
                'img': first_image,
                'year': car.year or '-',
                'brand': car.brand or '-',
                'model': car.model or '-',
                'variant': car.variant or '-',
                'transmission': car.transmission or '-',
                'mileage': f"{car.mileage:,}" if car.mileage else '-',
                'starting': starting_price if starting_price is not None else '-',
                'latest': car.price if car.price is not None else '-',
                'created_at': car.created_at.strftime("%Y-%m-%d") if car.created_at else '-',
                'status': car.status,
                'sold_duration': sold_duration,
                'id': car.id
            })

        return JsonResponse({
            'draw': int(request.GET.get('draw', 1)),
            'recordsTotal': total_records,
            'recordsFiltered': total_records,
            'data': data,
        })
    
    except Exception as e:
        import traceback
        print(f"Error in get_listing_data: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_brand_stats(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel
        
        brand_stats = (
            CarModel.objects
            .filter(status__in=['active', 'sold'])
            .values('brand')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        return JsonResponse({'brands': list(brand_stats)})
    except Exception as e:
        print(f"Error in get_brand_stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_model_stats(request):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel

        model_stats = (
            CarModel.objects
            .filter(status__in=['active', 'sold'], brand=brand)
            .values('model')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        return JsonResponse({'models': list(model_stats)})
    except Exception as e:
        print(f"Error in get_model_stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_scatter_data(request, username):
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

        # Format data untuk Chart.js scatter plot
        data = []
        for item in queryset.values('price', 'mileage')[:500]:
            data.append({
                'x': item['mileage'],
                'y': item['price']
            })

        return JsonResponse(data, safe=False)
    except Exception as e:
        print(f"Error in get_scatter_data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_avg_mileage_per_year(request, username):
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
            'labels': [str(item['year']) for item in data],
            'data': [round(item['avg_mileage'], 2) if item['avg_mileage'] else 0 for item in data],
        }
        return JsonResponse(result)
    except Exception as e:
        print(f"Error in get_avg_mileage_per_year: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_feature_correlation(request, username):
    try:
        source = request.GET.get('source', 'mudahmy')
        if source == 'carlistmy':
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import CarsMudahmy as CarModel

        qs = CarModel.objects.filter(status__in=['active', 'sold']).values('price', 'mileage', 'year')
        df = pd.DataFrame(list(qs))

        if df.empty:
            return JsonResponse({'error': 'No data'}, status=404)

        corr = df.corr()
        corr_dict = corr.round(3).to_dict()

        return JsonResponse({'correlation': corr_dict})
    except Exception as e:
        print(f"Error in get_feature_correlation: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_years(request):
    try:
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
        return JsonResponse(years, safe=False)
    except Exception as e:
        print(f"Error in get_years: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)