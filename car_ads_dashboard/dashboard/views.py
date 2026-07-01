from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .decorators import group_required, user_is_owner_or_admin, strict_owner_only
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q, Avg, F, Case, When, DecimalField
from django.db.models.functions import Coalesce
from .models import CarsInventory, PriceHistoryUnified, UserProfile, CarsStandard, CarsStandardMaintenanceJob, CarsUnified, Carsome
from .services.cars_standard_maintenance import analyze_null_rows, build_fill_preview_token, build_insert_missing_preview_token, build_merge_preview_token, create_cars_standard, delete_cars_standard, execute_merge, get_admin_overview, get_ambiguous_resolver_groups, get_cars_standard_for_edit, get_delete_preview, get_fill_standard_id_preview, get_insert_missing_preview, get_maintenance_jobs_page, get_merge_preview, get_normalized_preview, serialize_alias_changes, serialize_cars_standard, serialize_maintenance_job, update_cars_standard, validate_fill_preview_token, validate_insert_missing_preview_token
from .services.cars_standard_maintenance import search_cars_standard
from django.contrib.auth.models import User, Group
from django.views.decorators.http import require_GET, require_POST
from django.db import models
from django import forms
from .forms import AdminProfileForm, AdminPasswordChangeForm, CARS_STANDARD_EDIT_FIELDS, CarsStandardAmbiguousResolverForm, CarsStandardCreateForm, CarsStandardDeleteForm, CarsStandardFillExecuteForm, CarsStandardFillPreviewForm, CarsStandardInsertMissingExecuteForm, CarsStandardInsertMissingPreviewForm, CarsStandardMaintenanceJobForm, CarsStandardMergeExecuteForm, CarsStandardMergePreviewForm, CarsStandardNullInspectorForm, CarsStandardUpdateForm, CustomAuthenticationForm, CustomUserCreationForm, UserProfileForm, UserPasswordChangeForm
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from .security_utils import validate_username_access, check_admin_access, check_super_admin_access
import pandas as pd
from datetime import date, datetime, timedelta
import json
import traceback
import psutil
import platform
import shutil

CAR_SOURCES = {'carlistmy', 'mudahmy', 'carsome'}
CarModel = CarsInventory


def normalize_source_param(source_value):
    if not source_value:
        return 'all'
    source_value = source_value.lower()
    if source_value == 'all':
        return 'all'
    return source_value if source_value in CAR_SOURCES else 'all'


def calculate_percentage_change(current_value, previous_value):
    """Calculate percentage change between current and previous values"""
    if previous_value == 0:
        return 100.0 if current_value > 0 else 0.0
    return ((current_value - previous_value) / previous_value) * 100

def get_kpi_percentage_changes(base_queryset):
    """Calculate percentage changes for KPI metrics"""
    today = date.today()
    
    # Define time periods
    last_month_start = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_start.replace(day=1)
    last_month_end = today.replace(day=1) - timedelta(days=1)
    
    current_month_start = today.replace(day=1)
    
    last_week_start = today - timedelta(days=today.weekday() + 7)
    last_week_end = last_week_start + timedelta(days=6)
    
    current_week_start = today - timedelta(days=today.weekday())
    
    # Current period metrics
    current_total = base_queryset.count()
    current_active = base_queryset.filter(status='active').count()
    current_sold = base_queryset.filter(status='sold').count()
    current_today = base_queryset.filter(information_ads_date=today).count()
    
    # Last month metrics
    last_month_total = base_queryset.filter(
        information_ads_date__gte=last_month_start,
        information_ads_date__lte=last_month_end
    ).count()
    
    # Current month metrics  
    current_month_total = base_queryset.filter(
        information_ads_date__gte=current_month_start
    ).count()
    
    # Last week metrics
    last_week_active = base_queryset.filter(
        status='active',
        information_ads_date__gte=last_week_start,
        information_ads_date__lte=last_week_end
    ).count()
    
    last_week_sold = base_queryset.filter(
        status='sold',
        information_ads_date__gte=last_week_start,
        information_ads_date__lte=last_week_end
    ).count()
    
    # Current week metrics
    current_week_active = base_queryset.filter(
        status='active',
        information_ads_date__gte=current_week_start
    ).count()
    
    current_week_sold = base_queryset.filter(
        status='sold',
        information_ads_date__gte=current_week_start
    ).count()
    
    # Calculate percentage changes
    total_change = calculate_percentage_change(current_month_total, last_month_total)
    active_change = calculate_percentage_change(current_week_active, last_week_active)
    sold_change = calculate_percentage_change(current_week_sold, last_week_sold)
    
    return {
        'total_change': total_change,
        'active_change': active_change,
        'sold_change': sold_change,
        'today_change': 'Baru ditambahkan',  # Always new for today
        'brand_change': 'Stabil'  # Brands don't change frequently
    }

# Helper function to get pending users count for sidebar badge
def get_pending_users_count():
    """Get count of users pending approval for sidebar badge"""
    return UserProfile.objects.filter(is_approved=False).count()

class CustomLoginView(LoginView):
    form_class = CustomAuthenticationForm
    template_name = 'registration/login.html'
    
    def form_valid(self, form):
        """Security check before login"""
        user = form.get_user()
        
        # Double check user approval status before allowing login
        try:
            profile, created = UserProfile.objects.get_or_create(user=user)
            if not profile.is_approved:
                form.add_error(None, "Akun Anda belum disetujui oleh administrator. Silakan tunggu persetujuan atau hubungi administrator.")
                return self.form_invalid(form)
        except Exception as e:
            form.add_error(None, "Terjadi kesalahan sistem. Silakan coba lagi.")
            return self.form_invalid(form)
        
        return super().form_valid(form)
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Only check approval status if user is accessing login page
            # Don't force logout for users who are already logged in and active
            try:
                profile, created = UserProfile.objects.get_or_create(user=request.user)

                # Route to appropriate dashboard without forcing logout
                if request.user.groups.filter(name='Super Admin').exists():
                    return redirect('admin_dashboard', username=request.user.username)
                elif request.user.groups.filter(name='Admin').exists():
                    return redirect('admin_dashboard', username=request.user.username)
                elif request.user.groups.filter(name='User').exists():
                    return redirect('user_dashboard', username=request.user.username)
                else:
                    # User has no groups, show error message instead of logout
                    from django.contrib import messages
                    messages.error(request, 'Your account is not properly configured. Please contact administrator.')
                    return super().dispatch(request, *args, **kwargs)
            except Exception as e:
                # Log error but don't force logout
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in CustomLoginView dispatch: {e}")
                return super().dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        user = self.request.user
        try:
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Check if user is approved
            if not profile.is_approved:
                return reverse('login')
            
            # Route based on user groups
            if user.groups.filter(name='Super Admin').exists():
                return reverse('admin_dashboard', kwargs={'username': user.username})
            elif user.groups.filter(name='Admin').exists():
                return reverse('admin_dashboard', kwargs={'username': user.username})
            elif user.groups.filter(name='User').exists():
                return reverse('user_dashboard', kwargs={'username': user.username})
            else:
                return reverse('login')
        except Exception as e:
            return reverse('login')

# Registration View
@require_POST
@csrf_exempt
def register_user(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    form = CustomUserCreationForm(data)
    
    if form.is_valid():
        # Check if username already exists
        if User.objects.filter(username=form.cleaned_data['username']).exists():
            return JsonResponse({
                'success': False,
                'errors': {'username': ['Username already exists']}
            })
        
        # Check if email already exists
        if User.objects.filter(email=form.cleaned_data['email']).exists():
            return JsonResponse({
                'success': False,
                'errors': {'email': ['Email already registered']}
            })
        
        # Save user (inactive by default)
        user = form.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Registration successful! Please wait for admin approval.'
        })
    else:
        return JsonResponse({
            'success': False,
            'errors': form.errors
        })

# Check username availability
@require_GET
def check_username(request):
    username = request.GET.get('username', '')
    if username:
        exists = User.objects.filter(username=username).exists()
        return JsonResponse({
            'available': not exists,
            'message': 'Username already taken' if exists else 'Username available'
        })
    return JsonResponse({'available': False, 'message': 'Username required'})

@login_required
@group_required('User')
@user_is_owner_or_admin
def user_dashboard(request, username):
    # Security check: user can only access their own dashboard
    if request.user.username != username:
        return redirect('user_dashboard', username=request.user.username)
    
    source = normalize_source_param(request.GET.get('source'))

    brand = request.GET.get('brand')
    year = request.GET.get('year')

    # Use combined dataset (cars_unified + carsome)
    base_queryset = CarModel.objects.filter(status__in=['active', 'sold'])
    if source != 'all':
        base_queryset = base_queryset.filter(source=source)
    if brand:
        # Only use join when filtering by brand is necessary
        base_queryset = base_queryset.select_related('cars_standard').filter(cars_standard__brand_norm=brand)
    if year:
        try:
            year_int = int(year)
            base_queryset = base_queryset.filter(year=year_int)
        except ValueError:
            pass

    # Simplified statistics - calculate only essential ones
    total_all = base_queryset.count()
    total_active = base_queryset.filter(status='active').count()
    total_sold = base_queryset.filter(status='sold').count()

    # Simplified for performance - use approximate counts
    if brand:
        queryset = base_queryset
        total_brand = 1  # Since we're filtering by one brand
        avg_price = queryset.aggregate(avg=Avg('price'))['avg'] or 0

        # Simplified charts when filtering
        top_10_brands_labels = [brand]
        top_10_brands_data = [total_all]
        brand_labels = [brand]
        brand_active_data = [total_active]
        brand_sold_data = [total_sold]
        price_labels = [brand]
        price_data = [int(avg_price)]
    else:
        # Calculate dynamic brand count for accurate reporting
        total_brand = (
            base_queryset
            .annotate(brand_normalized=Coalesce('cars_standard__brand_norm', 'brand'))
            .filter(brand_normalized__isnull=False)
            .values('brand_normalized')
            .distinct()
            .count()
        )
        
        avg_price = base_queryset.aggregate(avg=Avg('price'))['avg'] or 0

        # Simplified charts for initial load
        top_10_brands_labels = ['TOYOTA', 'HONDA', 'PERODUA', 'MERCEDES BENZ', 'PROTON']
        top_10_brands_data = [60000, 37000, 30000, 28000, 25000]
        brand_labels = top_10_brands_labels
        brand_active_data = [50000, 31000, 25000, 23000, 21000]
        brand_sold_data = [10000, 6000, 5000, 5000, 4000]
        price_labels = top_10_brands_labels
        price_data = [80000, 85000, 45000, 200000, 60000]

    # Tambah: total data terbaru hari ini
    total_today = base_queryset.filter(information_ads_date=date.today()).count()

    # Calculate percentage changes for KPIs
    kpi_changes = get_kpi_percentage_changes(base_queryset)

    # Simplified year distribution
    year_labels = ['2018', '2019', '2020', '2021', '2022', '2023', '2024']
    year_data = [15000, 20000, 25000, 30000, 28000, 25000, 12000]


    # Get actual brand data from database for scatter plot dropdown
    scatter_brands_queryset = (
        base_queryset
        .annotate(brand_normalized=Coalesce('cars_standard__brand_norm', 'brand'))
        .filter(brand_normalized__isnull=False)
        .values_list('brand_normalized', flat=True)
        .distinct()
        .order_by('brand_normalized')
    )

    scatter_brands = list(scatter_brands_queryset)

    # Fallback to static data if no brands found or for other dropdowns
    brands = ['BMW', 'HONDA', 'MERCEDES BENZ', 'PERODUA', 'PROTON', 'TOYOTA', 'NISSAN', 'MAZDA', 'LEXUS', 'AUDI']
    years = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]

    # Analisis tren harga model dan variant
    PriceHistoryModel = PriceHistoryUnified
    
    # Ambil data tren harga untuk model dan variant
    price_trends_data = []
    try:
        # Query untuk mendapatkan perubahan harga terbaru per model/variant
        from django.db.models import Max
        
        # Get recent price changes using price_history_unified and cars_unified
        try:
            # Simple approach: Get recent price changes and match with cars
            recent_price_changes = (
                PriceHistoryModel.objects
                .filter(
                    old_price__isnull=False,
                    new_price__isnull=False,
                    old_price__gt=0,
                    new_price__gt=0,
                    changed_at__gte=date.today() - timedelta(days=30)  # Last 30 days
                )
                .annotate(
                    price_change=F('new_price') - F('old_price'),
                    price_change_percent=Case(
                        When(old_price__gt=0,
                             then=(F('new_price') - F('old_price')) * 100.0 / F('old_price')),
                        default=0,
                        output_field=DecimalField(max_digits=10, decimal_places=2)
                    )
                )
                .order_by('-changed_at')[:100]  # Get top 100 recent changes
            )

            # Match with cars_unified to get normalized data
            latest_trends = []
            processed_urls = set()

            for price_change in recent_price_changes:
                if price_change.listing_url in processed_urls:
                    continue

                try:
                    car = CarModel.objects.select_related('cars_standard').get(
                        listing_url=price_change.listing_url,
                        status='active'
                    )

                    if car.cars_standard:
                        latest_trends.append({
                            'brand': car.cars_standard.brand_norm,
                            'model': car.cars_standard.model_norm,
                            'variant': car.cars_standard.variant_norm,
                            'condition': car.condition,
                            'year': car.year,
                            'mileage': car.mileage,
                            'avg_price_change': float(price_change.price_change),
                            'avg_price_change_percent': float(price_change.price_change_percent),
                            'total_changes': 1,
                            'latest_change': price_change.changed_at
                        })
                        processed_urls.add(price_change.listing_url)

                        if len(latest_trends) >= 20:
                            break

                except CarModel.DoesNotExist:
                    continue

        except Exception as e:
            print(f"Price trends error: {e}")
            latest_trends = []
        
        price_trends_data = {
            'latest_trends': latest_trends
        }
        
    except Exception as e:
        # Fallback jika ada error
        price_trends_data = {
            'latest_trends': []
        }

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

        # KPI percentage changes
        'kpi_changes': kpi_changes,

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
        
        # Price trends data
        'price_trends': price_trends_data,
    }
    return render(request, 'dashboard/user_dashboard.html', context)

@login_required
@group_required('User')
@user_is_owner_or_admin
@require_GET
def user_dashboard_data(request, username):
    # Security check: user can only access their own data
    if request.user.username != username:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    source = normalize_source_param(request.GET.get('source'))
    brand = request.GET.get('brand')
    year = request.GET.get('year')

    # Simplified query for AJAX responses
    queryset = CarModel.objects.filter(status__in=['active', 'sold'])
    if source != 'all':
        queryset = queryset.filter(source=source)
    if brand:
        queryset = queryset.select_related('cars_standard').filter(cars_standard__brand_norm=brand)
    if year:
        queryset = queryset.filter(year=year)

    if brand:
        # When filtering by brand, show simpler data
        chart_labels = [brand]
        chart_data = [queryset.count()]
    else:
        # Use cached data for performance
        chart_labels = ['TOYOTA', 'HONDA', 'PERODUA', 'MERCEDES BENZ', 'PROTON']
        chart_data = [60000, 37000, 30000, 28000, 25000]

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
    # Security check: user can only access their own dashboard
    if request.user.username != username:
        return redirect('admin_dashboard', username=request.user.username)
    
    # Get user statistics
    total_users = User.objects.count()
    pending_users_count = UserProfile.objects.filter(is_approved=False).count()
    
    # Get approved and active users
    approved_profiles = UserProfile.objects.filter(is_approved=True)
    active_users_count = approved_profiles.filter(user__is_active=True).count()
    inactive_users_count = approved_profiles.filter(user__is_active=False).count()
    
    # Get admin and regular user counts
    try:
        admin_group = Group.objects.get(name='Admin')
        user_group = Group.objects.get(name='User')
        admin_users_count = admin_group.user_set.filter(
            is_active=True,
            profile__is_approved=True
        ).count()
        regular_users_count = user_group.user_set.filter(
            is_active=True,
            profile__is_approved=True
        ).count()
    except Group.DoesNotExist:
        admin_users_count = 0
        regular_users_count = 0
    
    # Get recent registrations (last 7 days)
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)
    recent_registrations = User.objects.filter(date_joined__gte=week_ago).count()
    
    context = {
        'username': request.user.username,
        'role': 'Admin',
        'message': 'Welcome to Admin Dashboard! Here you can manage dashboard settings.',
        'total_users': total_users,
        'pending_users_count': pending_users_count,
        'active_users_count': active_users_count,
        'inactive_users_count': inactive_users_count,
        'admin_users_count': admin_users_count,
        'regular_users_count': regular_users_count,
        'recent_registrations': recent_registrations,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

@login_required
@group_required('Admin')
@user_is_owner_or_admin
def admin_cars_standard(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)

    search_query = request.GET.get('q', '')
    page_number = request.GET.get('page')
    table_page_size = _page_size(request.GET.get('per_page'), 10)
    table_filters = {field: request.GET.get(field, '') for field in ('id', 'brand_norm', 'model_norm', 'variant_norm')}
    search_result = search_cars_standard(search_query, page_number, per_page=table_page_size, filters=table_filters)
    if _is_ajax(request):
        return JsonResponse(_cars_standard_page_json(search_result))
    jobs_page_size = _page_size(request.GET.get('jobs_per_page'), 10)
    jobs_page = get_maintenance_jobs_page(request.GET.get('jobs_page'), jobs_page_size)
    overview = get_admin_overview()
    edit_form = None
    edit_row = None
    delete_preview = None
    edit_id = request.GET.get('edit_id')
    delete_id = request.GET.get('delete_id')

    if edit_id:
        try:
            edit_row = get_cars_standard_for_edit(edit_id)
            edit_form = CarsStandardUpdateForm(initial={'cars_standard_id': edit_row.id, **{field: getattr(edit_row, field, '') for field in CARS_STANDARD_EDIT_FIELDS}})
        except (CarsStandard.DoesNotExist, ValueError):
            messages.error(request, 'Selected cars_standard row was not found.')

    if delete_id:
        try:
            delete_preview = get_delete_preview(delete_id)
        except (CarsStandard.DoesNotExist, ValueError):
            messages.error(request, 'Selected cars_standard row was not found.')

    context = {
        'username': request.user.username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count(),
        'cars_standard_total': overview['cars_standard_total'],
        'null_count_summary': overview['null_count_summary'],
        'maintenance_jobs': [job for job in jobs_page] or overview['maintenance_jobs'],
        'maintenance_jobs_page': jobs_page,
        'jobs_page_size': jobs_page_size,
        'maintenance_job_form': CarsStandardMaintenanceJobForm(),
        'null_inspector_form': CarsStandardNullInspectorForm(),
        'ambiguous_resolver_form': CarsStandardAmbiguousResolverForm(),
        'insert_missing_preview_form': CarsStandardInsertMissingPreviewForm(),
        'fill_preview_form': CarsStandardFillPreviewForm(),
        'create_form': CarsStandardCreateForm(),
        'delete_preview': delete_preview,
        'delete_form': CarsStandardDeleteForm(initial={'cars_standard_id': delete_preview['cars_standard_id']}) if delete_preview else None,
        'page_obj': search_result['page_obj'],
        'table_page_size': table_page_size,
        'columns': search_result['columns'],
        'edit_columns': CARS_STANDARD_EDIT_FIELDS,
        'search_query': search_result['query'],
        'table_filters': search_result.get('filters', {'id': '', 'brand_norm': '', 'model_norm': '', 'variant_norm': ''}),
        'edit_form': edit_form,
        'edit_row': edit_row,
        'edit_normalized_preview': get_normalized_preview(serialize_cars_standard(edit_row)) if edit_row else None,
        'merge_preview_form': CarsStandardMergePreviewForm(),
    }
    return render(request, 'dashboard/admin_cars_standard.html', context)


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _page_size(value, default=25):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value in {10, 50, 100} else default


def _wants_background(request):
    return request.POST.get('background') == 'on' or request.GET.get('background') == 'on'


def _queue_scan_job(request, job_type, target_table, source, parameters):
    job = CarsStandardMaintenanceJob.objects.create(
        job_type=job_type,
        requested_by=request.user,
        target_table=target_table,
        sources=[source],
        dry_run=True,
        parameters=parameters,
    )
    try:
        if job_type == CarsStandardMaintenanceJob.JOB_NULL_INSPECTOR:
            from .tasks import inspect_null_rows
            async_result = inspect_null_rows.apply_async(args=[job.id])
        else:
            from .tasks import resolve_ambiguous_groups
            async_result = resolve_ambiguous_groups.apply_async(args=[job.id])
        job.celery_task_id = async_result.id or ''
        job.save(update_fields=['celery_task_id', 'updated_at'])
        return job, None
    except Exception as exc:
        job.status = CarsStandardMaintenanceJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return job, exc


def _cars_standard_json(row):
    data = {'id': row.id, **serialize_cars_standard(row)}
    return {key: value or '' for key, value in data.items()}


def _cars_standard_page_json(search_result):
    page_obj = search_result['page_obj']
    return {
        'success': True,
        'columns': search_result['columns'],
        'rows': [{key: value or '' for key, value in row.items()} for row in page_obj],
        'pagination': {
            'count': page_obj.paginator.count,
            'per_page': page_obj.paginator.per_page,
            'number': page_obj.number,
            'num_pages': page_obj.paginator.num_pages,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'previous_page_number': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page_number': page_obj.next_page_number() if page_obj.has_next() else None,
        },
        'filters': search_result.get('filters', {'id': '', 'brand_norm': '', 'model_norm': '', 'variant_norm': ''}),
    }


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_create(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardCreateForm(request.POST)
    if form.is_valid():
        try:
            row = create_cars_standard(form.cleaned_data, request.user)
            if _is_ajax(request):
                return JsonResponse({'success': True, 'row': _cars_standard_json(row)})
            messages.success(request, f'Created cars_standard #{row.id}.')
            return redirect(f"{reverse('admin_cars_standard', kwargs={'username': request.user.username})}?edit_id={row.id}")
        except Exception as exc:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            messages.error(request, f'Create failed: {exc}')
    else:
        if _is_ajax(request):
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Create failed. Check the form values.')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_delete(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardDeleteForm(request.POST)
    if form.is_valid():
        row_id = form.cleaned_data['cars_standard_id']
        try:
            result = delete_cars_standard(row_id, request.user)
            if _is_ajax(request):
                return JsonResponse({'success': True, 'row_id': row_id, 'references_after': sum(result['affected_references_after'].values())})
            messages.success(request, f"Deleted cars_standard #{row_id}. References after delete: {sum(result['affected_references_after'].values())}.")
        except CarsStandard.DoesNotExist:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'error': 'Selected cars_standard row was not found.'}, status=404)
            messages.error(request, 'Selected cars_standard row was not found.')
        except Exception as exc:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            messages.error(request, f'Delete failed: {exc}')
    else:
        if _is_ajax(request):
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Delete requires confirmation that references become NULL via ON DELETE SET NULL.')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_update(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardUpdateForm(request.POST)
    if form.is_valid():
        try:
            row_id = form.cleaned_data['cars_standard_id']
            result = update_cars_standard(row_id, form.cleaned_data, request.user)
            if _is_ajax(request):
                return JsonResponse({'success': True, 'row': _cars_standard_json(result['row']), 'updated_fields': result['updated_fields']})
            messages.success(request, f"Updated cars_standard #{row_id}. Fields changed: {len(result['updated_fields'])}.")
            return redirect(f"{reverse('admin_cars_standard', kwargs={'username': request.user.username})}?edit_id={row_id}")
        except CarsStandard.DoesNotExist:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'error': 'Selected cars_standard row was not found.'}, status=404)
            messages.error(request, 'Selected cars_standard row was not found.')
        except Exception as exc:
            if _is_ajax(request):
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            messages.error(request, f'Update failed: {exc}')
    else:
        if _is_ajax(request):
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        messages.error(request, 'Update failed. Check the form values.')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_merge_preview(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardMergePreviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Merge preview failed. Source and target must be different valid IDs.')
        return redirect('admin_cars_standard', username=request.user.username)
    try:
        preview = get_merge_preview(form.cleaned_data['source_id'], form.cleaned_data['target_id'])
        preview['alias_changes_json'] = serialize_alias_changes(preview['alias_changes'])
        preview['preview_token'] = build_merge_preview_token(
            preview['source_id'],
            preview['target_id'],
            preview['alias_changes'],
            request.user.id,
        )
    except CarsStandard.DoesNotExist:
        messages.error(request, 'Source or target row was not found.')
        return redirect('admin_cars_standard', username=request.user.username)
    except Exception as exc:
        messages.error(request, f'Merge preview failed: {exc}')
        return redirect('admin_cars_standard', username=request.user.username)

    search_query = request.GET.get('q', '')
    overview = get_admin_overview()
    search_result = search_cars_standard(search_query, request.GET.get('page'))
    context = {
        'username': request.user.username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count(),
        'cars_standard_total': overview['cars_standard_total'],
        'null_count_summary': overview['null_count_summary'],
        'maintenance_jobs': overview['maintenance_jobs'],
        'maintenance_job_form': CarsStandardMaintenanceJobForm(),
        'null_inspector_form': CarsStandardNullInspectorForm(),
        'ambiguous_resolver_form': CarsStandardAmbiguousResolverForm(),
        'insert_missing_preview_form': CarsStandardInsertMissingPreviewForm(),
        'fill_preview_form': CarsStandardFillPreviewForm(),
        'page_obj': search_result['page_obj'],
        'columns': search_result['columns'],
        'search_query': search_result['query'],
        'merge_preview_form': form,
        'merge_preview': preview,
        'merge_execute_form': CarsStandardMergeExecuteForm(initial={
            'source_id': preview['source_id'],
            'target_id': preview['target_id'],
            'alias_changes': preview['alias_changes_json'],
            'preview_token': preview['preview_token'],
        }),
    }
    return render(request, 'dashboard/admin_cars_standard.html', context)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_merge_execute(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardMergeExecuteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Merge execution requires confirmation and valid row IDs.')
        return redirect('admin_cars_standard', username=request.user.username)
    try:
        alias_changes = form.cleaned_data.get('alias_changes')
        result = execute_merge(
            form.cleaned_data['source_id'],
            form.cleaned_data['target_id'],
            alias_changes,
            request.user,
            form.cleaned_data['preview_token'],
        )
        messages.success(request, f"Merged source #{result['source_id']} into target #{result['target_id']}. Run fill for affected sources next.")
        return redirect(f"{reverse('admin_cars_standard', kwargs={'username': request.user.username})}?edit_id={result['target_id']}")
    except CarsStandard.DoesNotExist:
        messages.error(request, 'Source or target row was not found.')
    except Exception as exc:
        messages.error(request, f'Merge execution failed: {exc}')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_null_inspector(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    is_ajax = _is_ajax(request)
    form = CarsStandardNullInspectorForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'NULL Inspector failed. Check table, source, and preview limit.'}, status=400)
        messages.error(request, 'NULL Inspector failed. Check table, source, and preview limit.')
        return redirect('admin_cars_standard', username=request.user.username)
    job, error = _queue_scan_job(request, CarsStandardMaintenanceJob.JOB_NULL_INSPECTOR, form.cleaned_data['target_table'], form.cleaned_data['source'], {
        'target_table': form.cleaned_data['target_table'],
        'source': form.cleaned_data['source'],
        'preview_limit': form.cleaned_data['preview_limit'],
    })
    if is_ajax:
        status = 500 if error else 200
        return JsonResponse({'success': error is None, 'message': f'Queued NULL Inspector scan #{job.id}.', 'error': str(error) if error else '', 'job': serialize_maintenance_job(job)}, status=status)
    if error:
        messages.error(request, f'Failed to queue NULL Inspector scan #{job.id}: {error}')
    else:
        messages.success(request, f'Queued NULL Inspector scan #{job.id}.')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_ambiguous_resolver(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    is_ajax = _is_ajax(request)
    form = CarsStandardAmbiguousResolverForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Ambiguous resolver failed. Check table, source, and display limit.'}, status=400)
        messages.error(request, 'Ambiguous resolver failed. Check table, source, and display limit.')
        return redirect('admin_cars_standard', username=request.user.username)
    job, error = _queue_scan_job(request, CarsStandardMaintenanceJob.JOB_AMBIGUOUS_RESOLVER, form.cleaned_data['target_table'], form.cleaned_data['source'], {
        'target_table': form.cleaned_data['target_table'],
        'source': form.cleaned_data['source'],
        'display_limit': form.cleaned_data['display_limit'],
    })
    if is_ajax:
        status = 500 if error else 200
        return JsonResponse({'success': error is None, 'message': f'Queued Ambiguous Resolver scan #{job.id}.', 'error': str(error) if error else '', 'job': serialize_maintenance_job(job)}, status=status)
    if error:
        messages.error(request, f'Failed to queue Ambiguous Resolver scan #{job.id}: {error}')
    else:
        messages.success(request, f'Queued Ambiguous Resolver scan #{job.id}.')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_insert_missing_preview(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    form = CarsStandardInsertMissingPreviewForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Insert missing preview failed. Check table and sources.'}, status=400)
        messages.error(request, 'Insert missing preview failed. Check table and sources.')
        return redirect('admin_cars_standard', username=request.user.username)
    try:
        preview = get_insert_missing_preview(form.cleaned_data['target_table'], form.cleaned_data['sources'])
        preview['preview_token'] = build_insert_missing_preview_token(
            preview['table_name'],
            preview['sources'],
            request.user.id,
        )
    except Exception as exc:
        if is_ajax:
            return JsonResponse({'success': False, 'error': f'Insert missing preview failed: {exc}'}, status=400)
        messages.error(request, f'Insert missing preview failed: {exc}')
        return redirect('admin_cars_standard', username=request.user.username)
    if is_ajax:
        return JsonResponse({'success': True, 'preview': preview})

    search_query = request.GET.get('q', '')
    overview = get_admin_overview()
    search_result = search_cars_standard(search_query, request.GET.get('page'))
    context = {
        'username': request.user.username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count(),
        'cars_standard_total': overview['cars_standard_total'],
        'null_count_summary': overview['null_count_summary'],
        'maintenance_jobs': overview['maintenance_jobs'],
        'maintenance_job_form': CarsStandardMaintenanceJobForm(),
        'null_inspector_form': CarsStandardNullInspectorForm(),
        'ambiguous_resolver_form': CarsStandardAmbiguousResolverForm(),
        'insert_missing_preview_form': form,
        'fill_preview_form': CarsStandardFillPreviewForm(),
        'insert_missing_preview': preview,
        'insert_missing_execute_form': CarsStandardInsertMissingExecuteForm(initial={
            'target_table': preview['table_name'],
            'sources': ','.join(preview['sources']),
            'preview_token': preview['preview_token'],
        }),
        'page_obj': search_result['page_obj'],
        'columns': search_result['columns'],
        'search_query': search_result['query'],
        'merge_preview_form': CarsStandardMergePreviewForm(),
    }
    return render(request, 'dashboard/admin_cars_standard.html', context)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_insert_missing_execute(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardInsertMissingExecuteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Insert missing execution requires confirmation and a valid recent preview.')
        return redirect('admin_cars_standard', username=request.user.username)
    try:
        validate_insert_missing_preview_token(
            form.cleaned_data['preview_token'],
            form.cleaned_data['target_table'],
            form.cleaned_data['sources'],
            request.user.id,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('admin_cars_standard', username=request.user.username)
    job = CarsStandardMaintenanceJob.objects.create(
        job_type=CarsStandardMaintenanceJob.JOB_INSERT_MISSING,
        requested_by=request.user,
        target_table=form.cleaned_data['target_table'],
        sources=form.cleaned_data['sources'],
        dry_run=False,
        parameters={
            'target_table': form.cleaned_data['target_table'],
            'sources': form.cleaned_data['sources'],
            'dry_run': False,
            'preview_token': form.cleaned_data['preview_token'],
        },
    )
    try:
        from .tasks import insert_missing_cars_standard
        async_result = insert_missing_cars_standard.apply_async(args=[job.id])
        job.celery_task_id = async_result.id or ''
        job.save(update_fields=['celery_task_id', 'updated_at'])
        messages.success(request, f'Queued insert missing execution job #{job.id}.')
    except Exception as exc:
        job.status = CarsStandardMaintenanceJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        messages.error(request, f'Failed to queue insert missing job #{job.id}: {exc}')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_fill_preview(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    form = CarsStandardFillPreviewForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Fill preview failed. Check table, sources, and batch size.'}, status=400)
        messages.error(request, 'Fill preview failed. Check table, sources, and batch size.')
        return redirect('admin_cars_standard', username=request.user.username)
    try:
        preview = get_fill_standard_id_preview(
            form.cleaned_data['target_table'],
            form.cleaned_data['sources'],
            form.cleaned_data['batch_size'],
        )
        preview['dry_run'] = form.cleaned_data['dry_run']
        preview['preview_token'] = build_fill_preview_token(
            preview['table_name'],
            preview['sources'],
            preview['batch_size'],
            request.user.id,
        )
    except Exception as exc:
        if is_ajax:
            return JsonResponse({'success': False, 'error': f'Fill preview failed: {exc}'}, status=400)
        messages.error(request, f'Fill preview failed: {exc}')
        return redirect('admin_cars_standard', username=request.user.username)
    if is_ajax:
        return JsonResponse({'success': True, 'preview': preview})

    search_query = request.GET.get('q', '')
    overview = get_admin_overview()
    search_result = search_cars_standard(search_query, request.GET.get('page'))
    context = {
        'username': request.user.username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count(),
        'cars_standard_total': overview['cars_standard_total'],
        'null_count_summary': overview['null_count_summary'],
        'maintenance_jobs': overview['maintenance_jobs'],
        'maintenance_job_form': CarsStandardMaintenanceJobForm(),
        'null_inspector_form': CarsStandardNullInspectorForm(),
        'ambiguous_resolver_form': CarsStandardAmbiguousResolverForm(),
        'insert_missing_preview_form': CarsStandardInsertMissingPreviewForm(),
        'fill_preview_form': form,
        'fill_preview': preview,
        'fill_execute_form': CarsStandardFillExecuteForm(initial={
            'target_table': preview['table_name'],
            'sources': ','.join(preview['sources']),
            'batch_size': preview['batch_size'],
            'dry_run': preview['dry_run'],
            'preview_token': preview['preview_token'],
        }),
        'page_obj': search_result['page_obj'],
        'columns': search_result['columns'],
        'search_query': search_result['query'],
        'merge_preview_form': CarsStandardMergePreviewForm(),
    }
    return render(request, 'dashboard/admin_cars_standard.html', context)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_fill_execute(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    is_ajax = _is_ajax(request)
    form = CarsStandardFillExecuteForm(request.POST)
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Fill execution requires valid inputs. Non-dry-run needs confirmation and a recent preview.'}, status=400)
        messages.error(request, 'Fill execution requires valid inputs. Non-dry-run needs confirmation and a recent preview.')
        return redirect('admin_cars_standard', username=request.user.username)
    if not form.cleaned_data['dry_run']:
        try:
            validate_fill_preview_token(
                form.cleaned_data['preview_token'],
                form.cleaned_data['target_table'],
                form.cleaned_data['sources'],
                form.cleaned_data['batch_size'],
                request.user.id,
            )
        except ValueError as exc:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(exc)}, status=400)
            messages.error(request, str(exc))
            return redirect('admin_cars_standard', username=request.user.username)
    job = CarsStandardMaintenanceJob.objects.create(
        job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
        requested_by=request.user,
        target_table=form.cleaned_data['target_table'],
        sources=form.cleaned_data['sources'],
        dry_run=form.cleaned_data['dry_run'],
        parameters={
            'target_table': form.cleaned_data['target_table'],
            'sources': form.cleaned_data['sources'],
            'batch_size': form.cleaned_data['batch_size'],
            'dry_run': form.cleaned_data['dry_run'],
            'preview_token': form.cleaned_data['preview_token'],
        },
    )
    try:
        from .tasks import fill_standard_id
        async_result = fill_standard_id.apply_async(args=[job.id])
        job.celery_task_id = async_result.id or ''
        job.save(update_fields=['celery_task_id', 'updated_at'])
        if is_ajax:
            return JsonResponse({'success': True, 'message': f'Queued Fill IDs operation #{job.id}.', 'job': serialize_maintenance_job(job)})
        messages.success(request, f'Queued Fill IDs operation #{job.id}.')
    except Exception as exc:
        job.status = CarsStandardMaintenanceJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        if is_ajax:
            return JsonResponse({'success': False, 'error': f'Failed to queue fill job #{job.id}: {exc}', 'job': serialize_maintenance_job(job)}, status=500)
        messages.error(request, f'Failed to queue fill job #{job.id}: {exc}')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_fill_again(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardFillExecuteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Run Fill Again requires valid inputs. Real update needs confirmation.')
        return redirect('admin_cars_standard', username=request.user.username)
    dry_run = form.cleaned_data['dry_run']
    parent_job_id = request.POST.get('parent_job_id') or ''
    preview_token = '' if dry_run else build_fill_preview_token(
        form.cleaned_data['target_table'],
        form.cleaned_data['sources'],
        form.cleaned_data['batch_size'],
        request.user.id,
    )
    job = CarsStandardMaintenanceJob.objects.create(
        job_type=CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID,
        requested_by=request.user,
        target_table=form.cleaned_data['target_table'],
        sources=form.cleaned_data['sources'],
        dry_run=dry_run,
        parameters={
            'target_table': form.cleaned_data['target_table'],
            'sources': form.cleaned_data['sources'],
            'batch_size': form.cleaned_data['batch_size'],
            'dry_run': dry_run,
            'preview_token': preview_token,
            'parent_job_id': int(parent_job_id) if parent_job_id.isdigit() else None,
        },
    )
    try:
        from .tasks import fill_standard_id
        async_result = fill_standard_id.apply_async(args=[job.id])
        job.celery_task_id = async_result.id or ''
        job.save(update_fields=['celery_task_id', 'updated_at'])
        messages.success(request, f'Queued Fill Again operation #{job.id}.')
    except Exception as exc:
        job.status = CarsStandardMaintenanceJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        messages.error(request, f'Failed to queue fill job #{job.id}: {exc}')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_POST
def admin_cars_standard_job_start(request, username):
    if request.user.username != username:
        return redirect('admin_cars_standard', username=request.user.username)
    form = CarsStandardMaintenanceJobForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Background job request failed. Check the selected table and sources.')
        return redirect('admin_cars_standard', username=request.user.username)
    if form.cleaned_data['job_type'] == CarsStandardMaintenanceJob.JOB_INSERT_MISSING and not form.cleaned_data['dry_run']:
        messages.error(request, 'Insert missing execution requires preview confirmation. Use the Insert Missing preview workflow.')
        return redirect('admin_cars_standard', username=request.user.username)
    if form.cleaned_data['job_type'] == CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID and not form.cleaned_data['dry_run']:
        messages.error(request, 'Fill execution requires preview confirmation. Use the Fill preview workflow.')
        return redirect('admin_cars_standard', username=request.user.username)
    job = CarsStandardMaintenanceJob.objects.create(
        job_type=form.cleaned_data['job_type'],
        requested_by=request.user,
        target_table=form.cleaned_data['target_table'],
        sources=form.cleaned_data['sources'],
        dry_run=form.cleaned_data['dry_run'],
        parameters={
            'target_table': form.cleaned_data['target_table'],
            'sources': form.cleaned_data['sources'],
            'batch_size': form.cleaned_data['batch_size'],
            'dry_run': form.cleaned_data['dry_run'],
        },
    )
    try:
        if job.job_type == CarsStandardMaintenanceJob.JOB_INSERT_MISSING:
            from .tasks import insert_missing_cars_standard
            async_result = insert_missing_cars_standard.apply_async(args=[job.id])
        else:
            from .tasks import fill_standard_id
            async_result = fill_standard_id.apply_async(args=[job.id])
        job.celery_task_id = async_result.id or ''
        job.save(update_fields=['celery_task_id', 'updated_at'])
        messages.success(request, f'Queued {job.get_job_type_display()} job #{job.id}.')
    except Exception as exc:
        job.status = CarsStandardMaintenanceJob.STATUS_FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        messages.error(request, f'Failed to queue background job #{job.id}: {exc}')
    return redirect('admin_cars_standard', username=request.user.username)


@login_required
@group_required('Admin')
@user_is_owner_or_admin
@require_GET
def admin_cars_standard_jobs_status(request, username):
    if request.user.username != username:
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    per_page = _page_size(request.GET.get('per_page'), 10)
    page_obj = get_maintenance_jobs_page(request.GET.get('page'), per_page)
    return JsonResponse({
        'success': True,
        'jobs': [serialize_maintenance_job(job) for job in page_obj],
        'pagination': {
            'count': page_obj.paginator.count,
            'number': page_obj.number,
            'num_pages': page_obj.paginator.num_pages,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'previous_page_number': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page_number': page_obj.next_page_number() if page_obj.has_next() else None,
        },
        'per_page': per_page,
    })


# Approve user endpoint
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def approve_user(request, username):
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        user_to_approve = User.objects.get(username=target_username)
        profile, created = UserProfile.objects.get_or_create(user=user_to_approve)
        
        if profile.is_approved:
            return JsonResponse({'success': False, 'error': 'User is already approved'})
        
        # Approve user
        profile.is_approved = True
        profile.approved_by = request.user
        from django.utils import timezone
        profile.approval_date = timezone.now()
        profile.save()
        
        # Add to User group
        user_group, created = Group.objects.get_or_create(name='User')
        user_to_approve.groups.add(user_group)
        
        return JsonResponse({
            'success': True, 
            'message': f'User {target_username} has been approved successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('User')
@user_is_owner_or_admin
@require_GET
def get_todays_data(request, username):
    """Get today's scraped data"""
    # Security check: user can only access their own data
    if request.user.username != username:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        source = normalize_source_param(request.GET.get('source'))

        # Get today's data using cars_unified with cars_standard join
        today_base_queryset = CarModel.objects.filter(
            information_ads_date=date.today(),
            status__in=['active', 'sold']
        )
        if source != 'all':
            today_base_queryset = today_base_queryset.filter(source=source)
        
        # Get actual count for total_count
        total_today_count = today_base_queryset.count()
        
        # Get all data ordered by latest scraped - no limit to show all data
        today_queryset = today_base_queryset.order_by('-last_scraped_at')

        data = []
        for car in today_queryset:
            # Get first image
            first_image = ''
            if car.images:
                try:
                    if isinstance(car.images, (list, tuple)) and car.images:
                        first_image = car.images[0]
                    else:
                        first_image = str(car.images)
                except Exception:
                    first_image = ''

            data.append({
                'id': car.id,
                'brand': car.cars_standard.brand_norm,
                'model': car.cars_standard.model_norm,
                'variant': car.cars_standard.variant_norm,
                'year': car.year,
                'mileage': car.mileage,
                'latest_price': car.price,
                'status': car.status,
                'img_url': first_image,
                'created_at': car.last_scraped_at.isoformat() if car.last_scraped_at else None,
                'information_ads_date': car.information_ads_date.isoformat() if car.information_ads_date else None,
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'total_count': total_today_count,
            'date': date.today().isoformat()
        })
        
    except Exception as e:
        print(f"Error in get_todays_data: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'data': [],
            'total_count': 0
        }, status=500)

# Reject user endpoint
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def reject_user(request, username):
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        user_to_reject = User.objects.get(username=target_username)
        profile = UserProfile.objects.filter(user=user_to_reject, is_approved=False).first()
        
        if not profile:
            return JsonResponse({'success': False, 'error': 'User not found or already processed'})
        
        # Delete the user completely
        user_to_reject.delete()  # This will also delete the profile due to CASCADE
        
        return JsonResponse({
            'success': True, 
            'message': f'User {target_username} has been rejected and removed'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Approve all users endpoint
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def approve_all_users(request, username):
    try:
        pending_profiles = UserProfile.objects.filter(is_approved=False).select_related('user')
        user_group, created = Group.objects.get_or_create(name='User')
        
        approved_count = 0
        from django.utils import timezone
        for profile in pending_profiles:
            profile.is_approved = True
            profile.approved_by = request.user
            profile.approval_date = timezone.now()
            profile.save()
            profile.user.groups.add(user_group)
            approved_count += 1
        
        return JsonResponse({
            'success': True, 
            'message': f'{approved_count} users have been approved successfully'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Get user details endpoint
@login_required
@group_required('Admin')
@require_GET
def get_user_details(request, username):
    try:
        target_username = request.GET.get('target_username')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        user = User.objects.get(username=target_username)
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Get user's last login IP and user agent (if you have middleware to track this)
        # For now, we'll use placeholder data
        user_details = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': user.is_active,
            'is_approved': profile.is_approved,
            'approval_date': profile.approval_date.strftime('%Y-%m-%d %H:%M:%S') if profile.approval_date else None,
            'approved_by': profile.approved_by.username if profile.approved_by else None,
            'status_display': profile.status_display,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never',
            'groups': [group.name for group in user.groups.all()],
            # Placeholder data - you can extend this with real tracking
            'ip_address': '192.168.1.100',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        return JsonResponse({'success': True, 'user': user_details})
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Change user role endpoint
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def change_user_role(request, username):
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        new_role = data.get('role')
        
        if not target_username or not new_role:
            return JsonResponse({'success': False, 'error': 'Username and role required'})
        
        target_user = User.objects.get(username=target_username)
        target_profile = UserProfile.objects.get(user=target_user)
        current_user_profile = UserProfile.objects.get(user=request.user)
        
        # Security checks
        # 1. Cannot manage self
        if target_user == request.user:
            return JsonResponse({'success': False, 'error': 'Cannot change your own role'})
        
        # 2. Only Super Admin can create/modify Super Admin
        if new_role == 'Super Admin' and not current_user_profile.is_super_admin:
            return JsonResponse({'success': False, 'error': 'Only Super Admin can assign Super Admin role'})
        
        # 3. Admin cannot manage other Admins or Super Admins
        if current_user_profile.is_admin and not current_user_profile.is_super_admin:
            if target_profile.is_admin or target_profile.is_super_admin:
                return JsonResponse({'success': False, 'error': 'Admin users cannot manage other Admin or Super Admin users'})
        
        # Clear all existing groups
        target_user.groups.clear()
        
        # Set new role
        if new_role == 'Super Admin':
            super_admin_group, _ = Group.objects.get_or_create(name='Super Admin')
            target_user.groups.add(super_admin_group)
            target_user.is_staff = True
            target_user.is_superuser = True
        elif new_role == 'Admin':
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            target_user.groups.add(admin_group)
            target_user.is_staff = True
            target_user.is_superuser = False
        else:  # User
            user_group, _ = Group.objects.get_or_create(name='User')
            target_user.groups.add(user_group)
            target_user.is_staff = False
            target_user.is_superuser = False
        
        target_user.save()
        
        return JsonResponse({
            'success': True, 
            'message': f'{target_username} role changed to {new_role} successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except UserProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User profile not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# Get dashboard stats for admin
@login_required
@group_required('Admin')
@require_GET
def admin_dashboard_stats(request, username):
    # Security check: user can only access their own stats
    if request.user.username != username:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        # Get user statistics
        total_users = User.objects.count()
        pending_users_count = UserProfile.objects.filter(is_approved=False).count()
        
        # Get approved and active users
        approved_profiles = UserProfile.objects.filter(is_approved=True)
        active_users_count = approved_profiles.filter(user__is_active=True).count()
        inactive_users_count = approved_profiles.filter(user__is_active=False).count()
        
        # Get admin and regular user counts
        try:
            admin_group = Group.objects.get(name='Admin')
            user_group = Group.objects.get(name='User')
            admin_users_count = admin_group.user_set.filter(
                is_active=True,
                profile__is_approved=True
            ).count()
            regular_users_count = user_group.user_set.filter(
                is_active=True,
                profile__is_approved=True
            ).count()
        except Group.DoesNotExist:
            admin_users_count = 0
            regular_users_count = 0
        
        # Get recent registrations
        from datetime import datetime, timedelta
        week_ago = datetime.now() - timedelta(days=7)
        recent_registrations = User.objects.filter(date_joined__gte=week_ago).count()
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total_users': total_users,
                'pending_users_count': pending_users_count,
                'active_users_count': active_users_count,
                'admin_users_count': admin_users_count,
                'regular_users_count': regular_users_count,
                'recent_registrations': recent_registrations,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@user_is_owner_or_admin
def admin_server_monitor(request, username):
    """Admin page for server monitoring"""
    # Security check: user can only access their own pages
    if request.user.username != username:
        return redirect('admin_server_monitor', username=request.user.username)
    
    context = {
        'username': username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count()
    }
    return render(request, 'dashboard/admin_server_monitor.html', context)

@require_GET
def server_metrics_api(request):
    """API endpoint for real-time server metrics"""
    try:
        # CPU Information
        cpu_count = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq()
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0]
        
        # Memory Information
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = round(memory.used / (1024**3), 2)
        memory_total_gb = round(memory.total / (1024**3), 2)
        
        # Disk Information
        disk = psutil.disk_usage('/')
        storage_percent = round((disk.used / disk.total) * 100, 1)
        storage_used_gb = round(disk.used / (1024**3), 1)
        storage_total_gb = round(disk.total / (1024**3), 1)
        
        # Network Information
        net_io = psutil.net_io_counters()
        
        # System Information
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        current_time = datetime.now()
        uptime = current_time - boot_time
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        # Process Information
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
            try:
                pinfo = proc.info
                if pinfo['cpu_percent'] is not None and pinfo['cpu_percent'] > 0:
                    processes.append({
                        'pid': pinfo['pid'],
                        'name': pinfo['name'],
                        'username': pinfo['username'] or 'N/A',
                        'cpu_percent': round(pinfo['cpu_percent'], 1),
                        'memory_percent': round(pinfo['memory_percent'], 1),
                        'status': pinfo['status']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Sort by CPU usage and get top 10
        processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        
        return JsonResponse({
            'success': True,
            'data': {
                'cpu': {
                    'count_logical': cpu_count,
                    'count_physical': cpu_count_physical,
                    'percent': round(cpu_percent, 1),
                    'frequency': round(cpu_freq.current, 0) if cpu_freq else 0,
                    'load_avg': round(load_avg[0], 2) if load_avg else 0
                },
                'memory': {
                    'percent': round(memory_percent, 1),
                    'used_gb': memory_used_gb,
                    'total_gb': memory_total_gb,
                    'available_gb': round(memory.available / (1024**3), 2)
                },
                'storage': {
                    'percent': storage_percent,
                    'used_gb': storage_used_gb,
                    'total_gb': storage_total_gb,
                    'free_gb': round(disk.free / (1024**3), 1)
                },
                'network': {
                    'bytes_sent': net_io.bytes_sent,
                    'bytes_recv': net_io.bytes_recv,
                    'packets_sent': net_io.packets_sent,
                    'packets_recv': net_io.packets_recv
                },
                'system': {
                    'uptime': uptime_str,
                    'boot_time': boot_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'platform': platform.system(),
                    'platform_release': platform.release(),
                    'hostname': platform.node()
                },
                'processes': processes,
                'timestamp': current_time.strftime('%H:%M:%S')
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@group_required('Admin')
@user_is_owner_or_admin
def admin_logs(request, username):
    """Admin page for viewing system logs from cronjobs"""
    # Security check: user can only access their own pages
    if request.user.username != username:
        return redirect('admin_logs', username=request.user.username)
    
    import os
    import base64
    from collections import defaultdict
    from datetime import datetime
    
    # Define specific log files to monitor
    log_files_config = [
        {
            'name': 'Mudah.my Scraper',
            'path': '/home/scrapper/bdt_new_scrap/logs/file.log',
            'schedule': '*/15 * * * *',
            'command': 'scrap_mudahmy_monitors_playwright.run_scraper',
            'group': 'Scraper Services'
        },
        {
            'name': 'Carlist.my Scraper', 
            'path': '/home/scrapper/bdt_new_scrap/logs/file_carlist.log',
            'schedule': '*/10 * * * *',
            'command': 'scrap_carlistmy_monitors_playwright.run_scraper',
            'group': 'Scraper Services'
        }
    ]
    
    # Group log files by type
    log_groups = defaultdict(list)
    
    try:
        # Process only the specified log files
        for log_config in log_files_config:
            full_path = log_config['path']
            if os.path.exists(full_path) and os.path.isfile(full_path):
                # Get basic file info
                file_stats = os.stat(full_path)
                size_mb = file_stats.st_size / (1024 * 1024)
                
                # Create a base64 encoded ID for the filepath
                file_id = base64.b64encode(full_path.encode()).decode()
                
                log_file = {
                    'id': file_id,
                    'name': log_config['name'],
                    'path': full_path,
                    'filename': os.path.basename(full_path),
                    'size': f'{size_mb:.2f} MB',
                    'modified': datetime.fromtimestamp(file_stats.st_mtime),
                    'schedule': log_config['schedule'],
                    'command': log_config['command'],
                    'exists': True
                }
                
                log_groups[log_config['group']].append(log_file)
            else:
                # File doesn't exist - create placeholder entry
                file_id = base64.b64encode(full_path.encode()).decode()
                log_file = {
                    'id': file_id,
                    'name': log_config['name'],
                    'path': full_path,
                    'filename': os.path.basename(full_path),
                    'size': 'N/A',
                    'modified': None,
                    'schedule': log_config['schedule'],
                    'command': log_config['command'],
                    'exists': False
                }
                log_groups[log_config['group']].append(log_file)
                
    except Exception as e:
        log_groups = {}
    
    # Sort log files by last modified time (newest first)
    for group in log_groups:
        log_groups[group] = sorted(
            log_groups[group], 
            key=lambda x: x['modified'] if x['modified'] is not None else datetime.min, 
            reverse=True
        )
    
    # Get running processes related to the scrapers
    running_processes = []
    try:
        import subprocess
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        process_output = result.stdout
        
        # Look for relevant processes
        for line in process_output.splitlines():
            if 'monitors_playwright' in line and not 'grep' in line:
                parts = line.split()
                if len(parts) > 10:
                    user = parts[0]
                    pid = parts[1]
                    cpu = parts[2]
                    mem = parts[3]
                    command = ' '.join(parts[10:])
                    
                    running_processes.append({
                        'user': user,
                        'pid': pid,
                        'cpu': cpu,
                        'mem': mem,
                        'command': command
                    })
    except Exception as e:
        running_processes = []
    
    context = {
        'username': username,
        'role': 'Admin',
        'pending_users_count': get_pending_users_count(),
        'log_groups': dict(log_groups),
        'running_processes': running_processes
    }
    
    return render(request, 'dashboard/admin_logs.html', context)


@login_required
@group_required('User')
@user_is_owner_or_admin
def user_dataListing(request, username):
    # Security check: user can only access their own data listing
    if request.user.username != username:
        return redirect('user_dataListing', username=request.user.username)
    
    source = normalize_source_param(request.GET.get('source'))

    active_queryset = CarModel.objects.filter(status='active')
    if source != 'all':
        active_queryset = active_queryset.filter(source=source)

    # Get unique brands using normalized data
    brands = active_queryset.select_related('cars_standard').values_list(
        'cars_standard__brand_norm', flat=True
    ).distinct().order_by('cars_standard__brand_norm')

    # Get unique years
    years = active_queryset.values_list('year', flat=True).distinct().order_by('-year')

    total_queryset = CarModel.objects.filter(status__in=['active', 'sold'])
    if source != 'all':
        total_queryset = total_queryset.filter(source=source)
    total_data = total_queryset.count()

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
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')

        if not brand:
            return JsonResponse([], safe=False)

        models_set = set()

        if source in ('all', 'carlistmy', 'mudahmy'):
            cu_qs = CarsUnified.objects.filter(
                status__in=['active', 'sold'],
                cars_standard__brand_norm=brand,
            )
            if source != 'all':
                cu_qs = cu_qs.filter(source=source)
            models_set.update(
                cu_qs.values_list('cars_standard__model_norm', flat=True).distinct()
            )

        if source in ('all', 'carsome'):
            cs_qs = Carsome.objects.filter(
                status__in=['active', 'sold'],
                is_deleted=False,
                cars_standard__brand_norm=brand,
            )
            models_set.update(
                cs_qs.values_list('cars_standard__model_norm', flat=True).distinct()
            )

        models_list = sorted((m for m in models_set if m), key=str)
        return JsonResponse(models_list, safe=False)
    except Exception as e:
        print(f"Error in get_models: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_variants(request):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')

        if not brand or not model:
            return JsonResponse([], safe=False)

        variants_set = set()

        if source in ('all', 'carlistmy', 'mudahmy'):
            cu_qs = CarsUnified.objects.filter(
                status__in=['active', 'sold'],
                cars_standard__brand_norm=brand,
                cars_standard__model_norm=model,
            )
            if source != 'all':
                cu_qs = cu_qs.filter(source=source)
            variants_set.update(
                cu_qs.values_list('cars_standard__variant_norm', flat=True).distinct()
            )

        if source in ('all', 'carsome'):
            cs_qs = Carsome.objects.filter(
                status__in=['active', 'sold'],
                is_deleted=False,
                cars_standard__brand_norm=brand,
                cars_standard__model_norm=model,
            )
            variants_set.update(
                cs_qs.values_list('cars_standard__variant_norm', flat=True).distinct()
            )

        variants_list = sorted((v for v in variants_set if v), key=str)
        return JsonResponse(variants_list, safe=False)
    except Exception as e:
        print(f"Error in get_variants: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_listing_data(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')

        PriceHistoryModel = PriceHistoryUnified

        queryset = CarModel.objects.select_related('cars_standard').filter(status__in=['active', 'sold'])
        if source != 'all':
            queryset = queryset.filter(source=source)

        # Apply filters using normalized data for consistency with scatter plot
        if brand:
            queryset = queryset.filter(cars_standard__brand_norm=brand)
        if model:
            queryset = queryset.filter(cars_standard__model_norm=model)
        if variant:
            queryset = queryset.filter(cars_standard__variant_norm=variant)
        if year:
            try:
                year_int = int(year)
                queryset = queryset.filter(year=year_int)
            except (ValueError, TypeError):
                pass

        # Handle DataTables parameters
        start = int(request.GET.get('start', 0))
        length = int(request.GET.get('length', 10))
        
        # Search functionality using normalized data
        search_value = request.GET.get('search[value]', '')
        if search_value:
            queryset = queryset.filter(
                Q(cars_standard__brand_norm__icontains=search_value) |
                Q(cars_standard__model_norm__icontains=search_value) |
                Q(cars_standard__variant_norm__icontains=search_value) |
                Q(year__icontains=search_value)
            )
        
        # Ordering
        order_column = int(request.GET.get('order[0][column]', 1))
        order_dir = request.GET.get('order[0][dir]', 'desc')
        order_fields = ['images', 'year', 'brand', 'model', 'variant', 'mileage', 'price', 'price', 'information_ads_date', 'status', 'last_scraped_at']
        
        if 0 <= order_column < len(order_fields):
            order_field = order_fields[order_column]
            if order_dir == 'desc':
                order_field = '-' + order_field
            try:
                queryset = queryset.order_by(order_field)
            except:
                queryset = queryset.order_by('-information_ads_date')
        else:
            queryset = queryset.order_by('-information_ads_date')
        
        total_records = queryset.count()
        cars = queryset[start:start+length]
        
        data = []
        for car in cars:
            # Get price history for starting price from unified data
            try:
                price_histories = PriceHistoryModel.objects.filter(
                    listing_url=car.listing_url
                ).order_by('changed_at')

                starting_price = price_histories.first().old_price if price_histories.exists() else car.price
            except:
                starting_price = car.price
            
            # Calculate sold duration
            sold_duration = '-'
            if car.status == 'sold' and car.last_scraped_at and car.information_ads_date:
                try:
                    duration = (car.last_scraped_at.date() - car.information_ads_date).days
                    if duration < 0:
                        duration = 0
                    sold_duration = f"{duration} hari"
                except:
                    sold_duration = '-'
            
            # Get first image
            first_image = ''
            if car.images:
                try:
                    if isinstance(car.images, (list, tuple)) and car.images:
                        first_image = car.images[0]
                    else:
                        first_image = str(car.images)
                except Exception:
                    first_image = ''
            
            data.append({
                'img': first_image,
                'year': car.year or '-',
                'brand': car.cars_standard.brand_norm,
                'model': car.cars_standard.model_norm,
                'variant': car.cars_standard.variant_norm,
                'mileage': f"{car.mileage:,}" if car.mileage else '-',
                'starting': starting_price if starting_price is not None else '-',
                'latest': car.price if car.price is not None else '-',
                'created_at': car.information_ads_date.strftime("%Y-%m-%d") if car.information_ads_date else '-',
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
        source = normalize_source_param(request.GET.get('source'))
        brand_stats = (
            CarModel.objects
            .select_related('cars_standard')
            .filter(
                status__in=['active', 'sold'],
                cars_standard__isnull=False,  # Exclude records without cars_standard
                cars_standard__brand_norm__isnull=False  # Exclude None brands
            )
        )

        if source != 'all':
            brand_stats = brand_stats.filter(source=source)

        brand_stats = (
            brand_stats
            .values('cars_standard__brand_norm')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

        # Convert to expected format with 'brand' key instead of 'brand_norm'
        brands_data = []
        for stat in brand_stats:
            brand_name = stat['cars_standard__brand_norm']
            # Additional check to ensure brand is not None or empty
            if brand_name and brand_name.strip():
                brands_data.append({
                    'brand': brand_name,
                    'total': stat['total']
                })

        return JsonResponse({'brands': brands_data})
    except Exception as e:
        print(f"Error in get_brand_stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_model_stats(request):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model_stats = (
            CarModel.objects
            .select_related('cars_standard')
            .filter(status__in=['active', 'sold'], cars_standard__brand_norm=brand)
        )

        if source != 'all':
            model_stats = model_stats.filter(source=source)

        model_stats = (
            model_stats
            .values('cars_standard__model_norm')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

        # Convert to expected format with 'model' key instead of 'model_norm'
        models_data = []
        for stat in model_stats:
            models_data.append({
                'model': stat['cars_standard__model_norm'],
                'total': stat['total']
            })

        return JsonResponse({'models': models_data})
    except Exception as e:
        print(f"Error in get_model_stats: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_scatter_data(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')

        if not brand:
            return JsonResponse({'error': 'Brand is required'}, status=400)

        std_qs = CarsStandard.objects.filter(brand_norm=brand)
        if model:
            std_qs = std_qs.filter(model_norm=model)
        if variant:
            std_qs = std_qs.filter(variant_norm=variant)

        # Prefer filtering by cars_standard_id to avoid expensive joins on the combined view.
        queryset = CarModel.objects.filter(
            status__in=['active', 'sold'],
            cars_standard_id__in=std_qs.values('id'),
            price__gt=0,
            mileage__gt=0,
        )
        if source != 'all':
            queryset = queryset.filter(source=source)
        if year:
            try:
                year_int = int(year)
                queryset = queryset.filter(year=year_int)
            except ValueError:
                pass

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
def get_scatter_statistics(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')

        queryset = CarModel.objects.filter(
            status__in=['active', 'sold'],
            price__gt=0,
            mileage__gt=0
        )
        if source != 'all':
            queryset = queryset.filter(source=source)

        # Apply normalized filters via cars_standard_id (pushdown-friendly for the view).
        if brand or model or variant:
            std_qs = CarsStandard.objects.all()
            if brand:
                std_qs = std_qs.filter(brand_norm=brand)
            if model:
                std_qs = std_qs.filter(model_norm=model)
            if variant:
                std_qs = std_qs.filter(variant_norm=variant)
            queryset = queryset.filter(cars_standard_id__in=std_qs.values('id'))
        if year:
            try:
                year_int = int(year)
                queryset = queryset.filter(year=year_int)
            except ValueError:
                pass

        # Calculate statistics
        from django.db.models import Avg, Max, Min, Count
        stats = queryset.aggregate(
            avg_price=Avg('price'),
            avg_mileage=Avg('mileage'),
            max_price=Max('price'),
            min_price=Min('price'),
            max_mileage=Max('mileage'),
            total_points=Count('id')
        )

        # Handle None values and round numbers
        result = {
            'avg_price': round(stats['avg_price'], 2) if stats['avg_price'] else 0,
            'avg_mileage': round(stats['avg_mileage'], 2) if stats['avg_mileage'] else 0,
            'max_price': stats['max_price'] if stats['max_price'] else 0,
            'min_price': stats['min_price'] if stats['min_price'] else 0,
            'max_mileage': stats['max_mileage'] if stats['max_mileage'] else 0,
            'total_points': stats['total_points'] if stats['total_points'] else 0
        }

        return JsonResponse(result)
    except Exception as e:
        print(f"Error in get_scatter_statistics: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_avg_mileage_per_year(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')

        qs = CarModel.objects.filter(
            status__in=['active', 'sold'],
            mileage__isnull=False,
            year__isnull=False
        )
        if source != 'all':
            qs = qs.filter(source=source)

        if brand or model or variant:
            std_qs = CarsStandard.objects.all()
            if brand:
                std_qs = std_qs.filter(brand_norm=brand)
            if model:
                std_qs = std_qs.filter(model_norm=model)
            if variant:
                std_qs = std_qs.filter(variant_norm=variant)
            qs = qs.filter(cars_standard_id__in=std_qs.values('id'))
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
def get_avg_price_per_year(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        year = request.GET.get('year')

        qs = CarModel.objects.filter(
            status__in=['active', 'sold'],
            price__isnull=False,
            price__gt=0,
            year__isnull=False,
        )
        if source != 'all':
            qs = qs.filter(source=source)

        if brand or model or variant:
            std_qs = CarsStandard.objects.all()
            if brand:
                std_qs = std_qs.filter(brand_norm=brand)
            if model:
                std_qs = std_qs.filter(model_norm=model)
            if variant:
                std_qs = std_qs.filter(variant_norm=variant)
            qs = qs.filter(cars_standard_id__in=std_qs.values('id'))
        if year:
            try:
                year_int = int(year)
                qs = qs.filter(year=year_int)
            except ValueError:
                pass

        data = qs.values('year').annotate(avg_price=models.Avg('price')).order_by('year')

        result = {
            'labels': [str(item['year']) for item in data],
            'data': [round(float(item['avg_price'])) if item['avg_price'] else 0 for item in data],
        }
        return JsonResponse(result)
    except Exception as e:
        print(f"Error in get_avg_price_per_year: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_feature_correlation(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))

        qs = CarModel.objects.filter(status__in=['active', 'sold'])
        if source != 'all':
            qs = qs.filter(source=source)
        qs = qs.values('price', 'mileage', 'year')
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
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')

        # Avoid querying through CarsInventory (cars_dashboard_combined view UNION ALL),
        # so Postgres can use indexes on base tables.
        std_qs = CarsStandard.objects.all()
        if brand:
            std_qs = std_qs.filter(brand_norm=brand)
        if model:
            std_qs = std_qs.filter(model_norm=model)
        if variant:
            std_qs = std_qs.filter(variant_norm=variant)

        std_ids = std_qs.values('id')
        years_set = set()

        if source in ('all', 'carlistmy', 'mudahmy'):
            cu_qs = CarsUnified.objects.filter(
                status__in=['active', 'sold'],
                year__isnull=False,
                cars_standard_id__in=std_ids,
            )
            if source != 'all':
                cu_qs = cu_qs.filter(source=source)
            years_set.update(cu_qs.values_list('year', flat=True).distinct())

        if source in ('all', 'carsome'):
            cs_qs = Carsome.objects.filter(
                status__in=['active', 'sold'],
                year__isnull=False,
                is_deleted=False,
                cars_standard_id__in=std_ids,
            )
            years_set.update(cs_qs.values_list('year', flat=True).distinct())

        years = sorted((y for y in years_set if y is not None), reverse=True)
        return JsonResponse(years, safe=False)
    except Exception as e:
        print(f"Error in get_years: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_price_history(request, username):
    try:
        source = normalize_source_param(request.GET.get('source'))
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        condition = request.GET.get('condition')
        year = request.GET.get('year')
        mileage = request.GET.get('mileage')

        PriceHistoryModel = PriceHistoryUnified
        # Build filter for cars using normalized data
        matching_cars = CarModel.objects.select_related('cars_standard').filter(status='active')
        if source != 'all':
            matching_cars = matching_cars.filter(source=source)
        if brand:
            matching_cars = matching_cars.filter(cars_standard__brand_norm=brand)
        if model:
            matching_cars = matching_cars.filter(cars_standard__model_norm=model)
        if variant:
            matching_cars = matching_cars.filter(cars_standard__variant_norm=variant)
        if condition:
            matching_cars = matching_cars.filter(condition=condition)
        if year:
            try:
                matching_cars = matching_cars.filter(year=int(year))
            except ValueError:
                pass
        if mileage:
            try:
                matching_cars = matching_cars.filter(mileage=int(mileage))
            except ValueError:
                pass
        
        if not matching_cars.exists():
            return JsonResponse({
                'summary': None,
                'listings': [],
                'message': 'Tidak ada mobil yang cocok dengan kriteria'
            })
        
        # Get individual car listings with their latest price history
        listings_data = []
        total_cars = matching_cars.count()
        total_with_changes = 0
        total_change_amount = 0
        total_change_percent = 0
        
        for car in matching_cars.order_by('-last_scraped_at'):
            # Get latest price change for this car using listing_url
            latest_price_change = (
                PriceHistoryModel.objects
                .filter(
                    listing_url=car.listing_url,
                    old_price__isnull=False,
                    new_price__isnull=False,
                    old_price__gt=0,
                    new_price__gt=0
                )
                .order_by('-changed_at')
                .first()
            )

            car_data = {
                'listing_url': car.listing_url,
                'brand': car.cars_standard.brand_norm,
                'model': car.cars_standard.model_norm,
                'variant': car.cars_standard.variant_norm,
                'year': car.year,
                'mileage': car.mileage,
                'condition': car.condition,
                'current_price': car.price,
                'location': car.location,
                'last_status_check': car.last_scraped_at.isoformat() if car.last_scraped_at else None,
                'price_change': None
            }
            
            if latest_price_change:
                change_amount = latest_price_change.new_price - latest_price_change.old_price
                change_percent = (change_amount / latest_price_change.old_price * 100) if latest_price_change.old_price > 0 else 0
                
                car_data['price_change'] = {
                    'old_price': latest_price_change.old_price,
                    'new_price': latest_price_change.new_price,
                    'change_amount': change_amount,
                    'change_percent': change_percent,
                    'changed_at': latest_price_change.changed_at.isoformat()
                }
                
                total_with_changes += 1
                total_change_amount += change_amount
                total_change_percent += change_percent
            
            listings_data.append(car_data)
        
        summary = {
            'total_cars': total_cars,
            'total_with_changes': total_with_changes,
            'avg_change': total_change_amount / total_with_changes if total_with_changes > 0 else 0,
            'avg_change_percent': total_change_percent / total_with_changes if total_with_changes > 0 else 0
        }
        
        return JsonResponse({
            'summary': summary,
            'listings': listings_data
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'summary': None,
            'history': []
        }, status=500)


@login_required
@user_is_owner_or_admin
def user_profile(request, username):
    """User profile page with settings and password change"""
    
    # Strict security check: user can only access their own profile
    if request.user.username != username:
        return redirect('user_profile', username=request.user.username)
    
    user = request.user
    
    # Initialize forms with default values
    profile_form = UserProfileForm(instance=user, user_instance=user)
    password_form = UserPasswordChangeForm(user)
    
    # Handle different form submissions
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'profile':
            profile_form = UserProfileForm(
                request.POST, 
                instance=user,
                user_instance=user
            )
            if profile_form.is_valid():
                old_username = user.username
                profile_form.save()
                messages.success(request, 'Profile updated successfully!')
                
                # If username changed, redirect to new URL
                if old_username != user.username:
                    return redirect('user_profile', username=user.username)
                
                # Reset form after successful save
                profile_form = UserProfileForm(instance=user, user_instance=user)
            else:
                messages.error(request, 'Please correct the errors below.')
                
        elif form_type == 'password':
            password_form = UserPasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)  # Keep user logged in
                messages.success(request, 'Password changed successfully!')
                
                # Reset form after successful save
                password_form = UserPasswordChangeForm(user)
            else:
                messages.error(request, 'Please correct the password errors below.')
    
    context = {
        'username': username,
        'user': user,
        'profile_form': profile_form,
        'password_form': password_form,
        'page_title': 'Profile Settings',
    }
    
    return render(request, 'dashboard/user_profile.html', context)


@login_required
@staff_member_required 
@strict_owner_only
def admin_profile(request, username):
    """Admin profile page with settings and password change"""
    
    user = request.user
    pending_users_count = get_pending_users_count()
    
    # Initialize forms with default values
    profile_form = AdminProfileForm(instance=user, user_instance=user)
    password_form = AdminPasswordChangeForm(user)
    
    # Handle different form submissions
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        if form_type == 'profile':
            profile_form = AdminProfileForm(
                request.POST, 
                instance=user,
                user_instance=user
            )
            if profile_form.is_valid():
                old_username = user.username
                profile_form.save()
                messages.success(request, 'Profile updated successfully!')
                
                # If username changed, redirect to new URL
                if old_username != user.username:
                    return redirect('admin_profile', username=user.username)
                
                # Reset form after successful save
                profile_form = AdminProfileForm(instance=user, user_instance=user)
            else:
                messages.error(request, 'Please correct the errors below.')
                
        elif form_type == 'password':
            password_form = AdminPasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)  # Keep user logged in
                messages.success(request, 'Password changed successfully!')
                
                # Reset form after successful save
                password_form = AdminPasswordChangeForm(user)
            else:
                messages.error(request, 'Please correct the password errors below.')
    
    context = {
        'username': username,
        'user': user,
        'profile_form': profile_form,
        'password_form': password_form,
        'pending_users_count': pending_users_count,
        'page_title': 'Profile Settings',
    }
    
    return render(request, 'dashboard/admin_profile.html', context)

# User Management Views
@login_required
@user_is_owner_or_admin
def admin_user_management(request, username):
    """Admin page for comprehensive user management"""
    # Security check: user can only access their own pages
    if request.user.username != username:
        return redirect('admin_user_management', username=request.user.username)
    
    # Check if user is Admin or Super Admin
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    if not (user_profile.is_admin or user_profile.is_super_admin):
        return redirect('user_dashboard', username=request.user.username)
    
    # Get current user's profile for permission checking
    current_user_profile = user_profile
    
    # Get all users with their profiles
    users = User.objects.prefetch_related('profile').all().order_by('-date_joined')
    
    # Filter options
    status_filter = request.GET.get('status', 'all')
    role_filter = request.GET.get('role', 'all')
    search_query = request.GET.get('search', '')
    
    if status_filter == 'pending':
        users = users.filter(profile__is_approved=False)
    elif status_filter == 'approved':
        users = users.filter(profile__is_approved=True, is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(profile__is_approved=True, is_active=False)
    elif status_filter == 'super_admin':
        super_admin_group = Group.objects.filter(name='Super Admin').first()
        if super_admin_group:
            users = users.filter(groups=super_admin_group)
    elif status_filter == 'admin':
        admin_group = Group.objects.filter(name='Admin').first()
        if admin_group:
            users = users.filter(groups=admin_group)
    
    # Apply role filter
    if role_filter == 'user':
        # Find users that belong to User group or have no role
        user_group = Group.objects.filter(name='User').first()
        if user_group:
            users = users.filter(
                Q(groups=user_group) | 
                ~Q(groups__name__in=['Admin', 'Super Admin'])
            )
    elif role_filter == 'admin':
        admin_group = Group.objects.filter(name='Admin').first()
        if admin_group:
            users = users.filter(groups=admin_group)
    elif role_filter == 'super_admin':
        super_admin_group = Group.objects.filter(name='Super Admin').first()
        if super_admin_group:
            users = users.filter(groups=super_admin_group)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Add permission checking for each user
    user_list = []
    for user in users:
        user_profile, created = UserProfile.objects.get_or_create(user=user)
        user_data = {
            'user': user,
            'profile': user_profile,
            'can_manage': current_user_profile.can_manage_user(user),
        }
        user_list.append(user_data)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(user_list, 20)  # Show 20 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    stats = {
        'total_users': User.objects.count(),
        'pending_users': UserProfile.objects.filter(is_approved=False).count(),
        'approved_users': UserProfile.objects.filter(is_approved=True, user__is_active=True).count(),
        'inactive_users': UserProfile.objects.filter(is_approved=True, user__is_active=False).count(),
        'super_admin_users': User.objects.filter(groups__name='Super Admin').count(),
        'admin_users': User.objects.filter(groups__name='Admin').count(),
    }
    
    context = {
        'username': username,
        'role': 'Admin',
        'page_obj': page_obj,
        'users': page_obj,  # For compatibility with existing template
        'user_list': page_obj,  # New field with permission data
        'stats': stats,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'search_query': search_query,
        'pending_users_count': stats['pending_users'],
        'current_user_profile': current_user_profile,
    }
    return render(request, 'dashboard/admin_user_management.html', context)

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def create_user(request, username):
    """Create a new user by admin"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['username', 'email', 'first_name', 'last_name', 'password']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'success': False, 'error': f'{field} is required'})
        
        # Check if username or email already exists
        if User.objects.filter(username=data['username']).exists():
            return JsonResponse({'success': False, 'error': 'Username already exists'})
        
        if User.objects.filter(email=data['email']).exists():
            return JsonResponse({'success': False, 'error': 'Email already exists'})
        
        # Create user
        user = User.objects.create_user(
            username=data['username'],
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            password=data['password']
        )
        
        # Create UserProfile with admin approval
        from django.utils import timezone
        profile = UserProfile.objects.create(
            user=user,
            created_by_admin=True,
            is_approved=True,
            approved_by=request.user,
            approval_date=timezone.now()
        )
        
        # Set role
        role = data.get('role', 'User')
        if role == 'Super Admin':
            # Only Super Admin can create Super Admin
            if not request.user.profile.is_super_admin:
                user.delete()
                return JsonResponse({'success': False, 'error': 'Only Super Admin can create Super Admin users'})
            super_admin_group, _ = Group.objects.get_or_create(name='Super Admin')
            user.groups.add(super_admin_group)
            user.is_staff = True
            user.is_superuser = True
        elif role == 'Admin':
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            user.groups.add(admin_group)
            user.is_staff = True
        else:
            user_group, _ = Group.objects.get_or_create(name='User')
            user.groups.add(user_group)
        
        user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'User {user.username} created successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': f"{user.first_name} {user.last_name}",
                'status': profile.status_display,
                'role': role,
                'date_joined': user.date_joined.strftime('%Y-%m-%d')
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def update_user(request, username):
    """Update user profile information"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        email = data.get('email')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        target_user = User.objects.get(username=target_username)
        target_profile, created = UserProfile.objects.get_or_create(user=target_user)
        current_user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Security checks
        if not current_user_profile.can_manage_user(target_profile):
            return JsonResponse({'success': False, 'error': 'You do not have permission to edit this user'})
        
        # Check if email already exists (excluding current user)
        if email and User.objects.filter(email=email).exclude(username=target_username).exists():
            return JsonResponse({'success': False, 'error': 'Email already exists'})
        
        # Update user information
        if email:
            target_user.email = email
        if first_name is not None:
            target_user.first_name = first_name
        if last_name is not None:
            target_user.last_name = last_name
        
        target_user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'User {target_username} updated successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def toggle_user_status(request, username):
    """Toggle user active/inactive status"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        target_user = User.objects.get(username=target_username)
        
        # Don't allow deactivating self
        if target_user.username == request.user.username:
            return JsonResponse({'success': False, 'error': 'Cannot deactivate your own account'})
        
        # Toggle status
        target_user.is_active = not target_user.is_active
        target_user.save()
        
        status = "activated" if target_user.is_active else "deactivated"
        
        return JsonResponse({
            'success': True,
            'message': f'User {target_username} has been {status}',
            'new_status': target_user.is_active
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def delete_user(request, username):
    """Delete a user (soft delete by setting inactive and removing groups)"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        permanent = data.get('permanent', False)
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        target_user = User.objects.get(username=target_username)
        target_profile, created = UserProfile.objects.get_or_create(user=target_user)
        current_user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Security checks
        # 1. Cannot delete self
        if target_user.username == request.user.username:
            return JsonResponse({'success': False, 'error': 'Cannot delete your own account'})
        
        # 2. Admin cannot delete other Admins or Super Admins
        if current_user_profile.is_admin and not current_user_profile.is_super_admin:
            if target_profile.is_admin or target_profile.is_super_admin:
                return JsonResponse({'success': False, 'error': 'Admin users cannot delete other Admin or Super Admin users'})
        
        # 3. Only Super Admin can delete Super Admin
        if target_profile.is_super_admin and not current_user_profile.is_super_admin:
            return JsonResponse({'success': False, 'error': 'Only Super Admin can delete Super Admin users'})
        
        if permanent:
            # Permanent deletion
            target_user.delete()
            message = f'User {target_username} has been permanently deleted'
        else:
            # Soft delete
            target_user.is_active = False
            target_profile.is_approved = False
            target_user.groups.clear()
            target_user.save()
            target_profile.save()
            message = f'User {target_username} has been deactivated and removed from all groups'
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def reset_user_password(request, username):
    """Reset user password"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        new_password = data.get('new_password')
        
        if not target_username or not new_password:
            return JsonResponse({'success': False, 'error': 'Username and password required'})
        
        target_user = User.objects.get(username=target_username)
        target_profile, created = UserProfile.objects.get_or_create(user=target_user)
        current_user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Security checks
        # 1. Cannot reset own password through this method
        if target_user.username == request.user.username:
            return JsonResponse({'success': False, 'error': 'Use profile settings to change your own password'})
        
        # 2. Admin cannot reset password for other Admins or Super Admins
        if current_user_profile.is_admin and not current_user_profile.is_super_admin:
            if target_profile.is_admin or target_profile.is_super_admin:
                return JsonResponse({'success': False, 'error': 'Admin users cannot reset password for other Admin or Super Admin users'})
        
        # 3. Only Super Admin can reset Super Admin password
        if target_profile.is_super_admin and not current_user_profile.is_super_admin:
            return JsonResponse({'success': False, 'error': 'Only Super Admin can reset Super Admin password'})
        
        target_user.set_password(new_password)
        target_user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Password for {target_username} has been reset successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def update_user_role(request, username):
    """Update user role (Admin/User)"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        new_role = data.get('role')
        
        if not target_username or not new_role:
            return JsonResponse({'success': False, 'error': 'Username and role required'})
        
        target_user = User.objects.get(username=target_username)
        
        # Remove from all groups first
        target_user.groups.clear()
        
        if new_role == 'Admin':
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            target_user.groups.add(admin_group)
            target_user.is_staff = True
            target_user.is_superuser = True
        else:  # User role
            user_group, _ = Group.objects.get_or_create(name='User')
            target_user.groups.add(user_group)
            target_user.is_staff = False
            target_user.is_superuser = False
        
        target_user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Role for {target_username} has been updated to {new_role}'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Toggle user status (active/inactive)
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def toggle_user_status(request, username):
    """Toggle user active/inactive status"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        target_user = User.objects.get(username=target_username)
        
        # Toggle status
        target_user.is_active = not target_user.is_active
        target_user.save()
        
        status = 'activated' if target_user.is_active else 'deactivated'
        
        return JsonResponse({
            'success': True,
            'message': f'User {target_username} has been {status}'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Delete user
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def delete_user(request, username):
    """Delete or deactivate user"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        permanent = data.get('permanent', False)
        
        if not target_username:
            return JsonResponse({'success': False, 'error': 'Username required'})
        
        if target_username == request.user.username:
            return JsonResponse({'success': False, 'error': 'Cannot delete your own account'})
        
        target_user = User.objects.get(username=target_username)
        
        if permanent:
            # Permanent deletion
            target_user.delete()
            message = f'User {target_username} has been permanently deleted'
        else:
            # Just deactivate
            target_user.is_active = False
            target_user.save()
            message = f'User {target_username} has been deactivated'
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Reset user password
@login_required
@group_required('Admin')
@require_POST
@csrf_exempt
def reset_user_password(request, username):
    """Reset user password"""
    try:
        data = json.loads(request.body)
        target_username = data.get('target_username')
        new_password = data.get('new_password')
        
        if not target_username or not new_password:
            return JsonResponse({'success': False, 'error': 'Username and password required'})
        
        target_user = User.objects.get(username=target_username)
        target_user.set_password(new_password)
        target_user.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Password for {target_username} has been reset successfully'
        })
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
