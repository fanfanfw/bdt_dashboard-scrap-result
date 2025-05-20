from django.urls import path
from . import views
from .views import trigger_sync

urlpatterns = [
    path('user/<str:username>/', views.user_dashboard, name='user_dashboard'),
    path('listing/<str:username>/', views.data_listing, name='data_listing'),
    path('admin/<str:username>/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/<str:username>/sync/', trigger_sync, name='trigger_sync'),
    path('get-models/', views.get_models, name='get_models'),
    path('get-variants/', views.get_variants, name='get_variants'),
    path('listing/<str:username>/data/', views.get_listing_data, name='get_listing_data'),
    path('get-brand-stats/', views.get_brand_stats, name='get_brand_stats'),
    path('get-model-stats/', views.get_model_stats, name='get_model_stats'),
]