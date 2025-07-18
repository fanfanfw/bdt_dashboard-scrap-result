from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .decorators import group_required, user_is_owner_or_admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from .tasks import sync_data_task
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q, Avg, F, Case, When, DecimalField
from .models import CarsMudahmy, CarsCarlistmy, PriceHistoryMudahmy, PriceHistoryCarlistmy
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User, Group
from django.views.decorators.http import require_GET, require_POST
from django.db import models
from django import forms
import pandas as pd
from datetime import date, datetime
import json
import traceback
import psutil
import platform
import shutil

# Helper function to get pending users count for sidebar badge
def get_pending_users_count():
    """Get count of users pending approval for sidebar badge"""
    return User.objects.filter(is_active=False).count()

# Custom Registration Form
class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.is_active = False  # User needs admin approval
        if commit:
            user.save()
        return user

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

    # Analisis tren harga model dan variant
    if source == 'carlistmy':
        from .models import PriceHistoryCarlistmy as PriceHistoryModel
    else:
        from .models import PriceHistoryMudahmy as PriceHistoryModel
    
    # Ambil data tren harga untuk model dan variant
    price_trends_data = []
    try:
        # Query untuk mendapatkan perubahan harga terbaru per model/variant
        from django.db.models import Max
        
        trend_analysis = (
            PriceHistoryModel.objects
            .select_related('car')
            .filter(
                car__status='active',  # Hanya status active
                old_price__isnull=False,
                new_price__isnull=False,
                old_price__gt=0,
                new_price__gt=0
            )
            .annotate(
                price_change=F('new_price') - F('old_price'),
                price_change_percent=Case(
                    When(old_price__gt=0, 
                         then=(F('new_price') - F('old_price')) * 100.0 / F('old_price')),
                    default=0,
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                ),
                brand=F('car__brand'),
                model=F('car__model'),
                variant=F('car__variant'),
                condition=F('car__condition'),
                year=F('car__year'),
                mileage=F('car__mileage')
            )
            .values('brand', 'model', 'variant', 'condition', 'year', 'mileage')
            .annotate(
                avg_price_change=Avg('price_change'),
                avg_price_change_percent=Avg('price_change_percent'),
                total_changes=Count('id'),
                latest_change=Max('changed_at')  # Tambahkan waktu perubahan terbaru
            )
            .filter(total_changes__gte=2)  # Minimal 2 perubahan harga
            .order_by('-latest_change')  # Urutkan berdasarkan perubahan terbaru
        )
        
        # Ambil 20 teratas berdasarkan update terbaru
        latest_trends = list(trend_analysis[:20])
        
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
        
        # Price trends data
        'price_trends': price_trends_data,
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
    # Get user statistics
    total_users = User.objects.count()
    pending_users_count = User.objects.filter(is_active=False).count()
    active_users_count = User.objects.filter(is_active=True).count()
    
    # Get admin and regular user counts
    try:
        admin_group = Group.objects.get(name='Admin')
        user_group = Group.objects.get(name='User')
        admin_users_count = admin_group.user_set.filter(is_active=True).count()
        regular_users_count = user_group.user_set.filter(is_active=True).count()
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
        'admin_users_count': admin_users_count,
        'regular_users_count': regular_users_count,
        'recent_registrations': recent_registrations,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

@login_required
@group_required('Admin')
@user_is_owner_or_admin
def admin_user_approval(request, username):
    """Admin page for user approval management"""
    # Get pending users (inactive users)
    pending_users = User.objects.filter(is_active=False).order_by('-date_joined')
    
    # Get recently approved users
    user_group = Group.objects.get(name='User')
    approved_users = User.objects.filter(
        is_active=True, 
        groups=user_group
    ).order_by('-date_joined')[:10]
    
    context = {
        'username': username,
        'role': 'Admin',
        'pending_users': pending_users,
        'approved_users': approved_users,
        'pending_count': pending_users.count()
    }
    return render(request, 'dashboard/admin_user_approval.html', context)

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
        
        user_to_approve = User.objects.get(username=target_username, is_active=False)
        
        # Activate user
        user_to_approve.is_active = True
        user_to_approve.save()
        
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
        
        user_to_reject = User.objects.get(username=target_username, is_active=False)
        
        # Delete the user completely
        user_to_reject.delete()
        
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
        pending_users = User.objects.filter(is_active=False)
        user_group, created = Group.objects.get_or_create(name='User')
        
        approved_count = 0
        for user in pending_users:
            user.is_active = True
            user.save()
            user.groups.add(user_group)
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
        
        # Get user's last login IP and user agent (if you have middleware to track this)
        # For now, we'll use placeholder data
        user_details = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': user.is_active,
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

# Get dashboard stats for admin
@login_required
@group_required('Admin')
@require_GET
def admin_dashboard_stats(request, username):
    try:
        # Get user statistics
        total_users = User.objects.count()
        pending_users_count = User.objects.filter(is_active=False).count()
        active_users_count = User.objects.filter(is_active=True).count()
        
        # Get admin and regular user counts
        try:
            admin_group = Group.objects.get(name='Admin')
            user_group = Group.objects.get(name='User')
            admin_users_count = admin_group.user_set.filter(is_active=True).count()
            regular_users_count = user_group.user_set.filter(is_active=True).count()
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

@user_is_owner_or_admin
def admin_logs(request, username):
    """Admin page for viewing system logs from cronjobs"""
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

@login_required
def get_price_history(request, username):
    try:
        source = request.GET.get('source', 'mudahmy')
        brand = request.GET.get('brand')
        model = request.GET.get('model')
        variant = request.GET.get('variant')
        condition = request.GET.get('condition')
        year = request.GET.get('year')
        mileage = request.GET.get('mileage')
        
        if source == 'carlistmy':
            from .models import PriceHistoryCarlistmy as PriceHistoryModel
            from .models import CarsCarlistmy as CarModel
        else:
            from .models import PriceHistoryMudahmy as PriceHistoryModel
            from .models import CarsMudahmy as CarModel
        
        # Build filter for cars
        car_filters = {'status': 'active'}  # Hanya status active
        if brand:
            car_filters['brand'] = brand
        if model:
            car_filters['model'] = model
        if variant:
            car_filters['variant'] = variant
        if condition:
            car_filters['condition'] = condition
        if year:
            try:
                car_filters['year'] = int(year)
            except ValueError:
                pass
        if mileage:
            try:
                car_filters['mileage'] = int(mileage)
            except ValueError:
                pass
        
        # Get matching cars
        matching_cars = CarModel.objects.filter(**car_filters)
        
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
        
        for car in matching_cars.order_by('-last_status_check'):
            # Get latest price change for this car
            latest_price_change = (
                PriceHistoryModel.objects
                .filter(
                    car=car,
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
                'brand': car.brand,
                'model': car.model,
                'variant': car.variant,
                'year': car.year,
                'mileage': car.mileage,
                'condition': car.condition,
                'current_price': car.price,
                'location': car.location,
                'transmission': car.transmission,
                'fuel_type': car.fuel_type,
                'engine_cc': car.engine_cc,
                'last_status_check': car.last_status_check.isoformat(),
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