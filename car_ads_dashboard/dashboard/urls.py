from django.urls import path
from . import views
from .views import trigger_sync

urlpatterns = [
    path('register/', views.register_user, name='register_user'),
    path('check-username/', views.check_username, name='check_username'),
    path('user/<str:username>/', views.user_dashboard, name='user_dashboard'),
    path('listing/<str:username>/', views.user_dataListing, name='user_dataListing'),
    path('admin/<str:username>/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/<str:username>/users/', views.admin_user_approval, name='admin_user_approval'),
    path('admin/<str:username>/users/approve/', views.approve_user, name='approve_user'),
    path('admin/<str:username>/users/reject/', views.reject_user, name='reject_user'),
    path('admin/<str:username>/users/approve-all/', views.approve_all_users, name='approve_all_users'),
    path('admin/<str:username>/users/details/', views.get_user_details, name='get_user_details'),
    path('admin/<str:username>/stats/', views.admin_dashboard_stats, name='admin_dashboard_stats'),
    path('admin/<str:username>/server/', views.admin_server_monitor, name='admin_server_monitor'),
    path('admin/<str:username>/logs/', views.admin_logs, name='admin_logs'),
    path('admin/<str:username>/sync/', trigger_sync, name='trigger_sync'),
    path('api/server-metrics/', views.server_metrics_api, name='server_metrics_api'),
    path('get-models/', views.get_models, name='get_models'),
    path('get-variants/', views.get_variants, name='get_variants'),
    path('listing/<str:username>/data/', views.get_listing_data, name='get_listing_data'),
    path('get-brand-stats/', views.get_brand_stats, name='get_brand_stats'),
    path('get-model-stats/', views.get_model_stats, name='get_model_stats'),
    path('user/<str:username>/data/', views.user_dashboard_data, name='user_dashboard_data'),
    path('user/<str:username>/scatter-data/', views.get_scatter_data, name='get_scatter_data'),
    path('user/<str:username>/avg-mileage-year/', views.get_avg_mileage_per_year, name='get_avg_mileage_per_year'),
    path('user/<str:username>/feature-correlation/', views.get_feature_correlation, name='get_feature_correlation'),
    path('user/<str:username>/price-history/', views.get_price_history, name='get_price_history'),
    path('get-years/', views.get_years, name='get_years'),
]