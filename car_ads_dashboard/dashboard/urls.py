from django.urls import path
from . import views
from .views import trigger_sync

urlpatterns = [
    path('user/<str:username>/', views.user_dashboard, name='user_dashboard'),
    path('admin/<str:username>/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/<str:username>/sync/', trigger_sync, name='trigger_sync'),
    path('api/price-vs-mileage/<str:username>/', views.api_price_vs_mileage, name='api_price_vs_mileage'),
]
