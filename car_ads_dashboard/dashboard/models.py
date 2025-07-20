from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth.models import User
from django.conf import settings

class UserProfile(models.Model):
    """
    Extended User model with approval and additional fields
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_approved = models.BooleanField(
        default=False, 
        help_text="Designates whether this user has been approved by admin."
    )
    created_by_admin = models.BooleanField(
        default=False,
        help_text="Designates whether this user was created by admin (auto-approved)."
    )
    approval_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Date when user was approved by admin."
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_user_profiles',
        help_text="Admin who approved this user."
    )
    
    def save(self, *args, **kwargs):
        # Auto-approve if created by admin
        if self.created_by_admin and not self.is_approved:
            self.is_approved = True
            if not self.approval_date:
                from django.utils import timezone
                self.approval_date = timezone.now()
        
        super().save(*args, **kwargs)
    
    def can_login(self):
        """Check if user can login (must be both approved and active)"""
        return self.is_approved and self.user.is_active
    
    @property
    def status_display(self):
        """Get human-readable status"""
        if not self.is_approved:
            return "Pending Approval"
        elif not self.user.is_active:
            return "Inactive"
        else:
            return "Active"
    
    @property
    def role_display(self):
        """Get user role display"""
        if self.user.groups.filter(name='Super Admin').exists():
            return "Super Admin"
        elif self.user.groups.filter(name='Admin').exists():
            return "Admin"
        elif self.user.groups.filter(name='User').exists():
            return "User"
        else:
            return "No Role"
    
    @property
    def is_super_admin(self):
        """Check if user is super admin"""
        return self.user.groups.filter(name='Super Admin').exists()
    
    @property
    def is_admin(self):
        """Check if user is admin or super admin"""
        return self.user.groups.filter(name__in=['Admin', 'Super Admin']).exists()
    
    def can_manage_user(self, target_user):
        """Check if this user can manage target user"""
        # Get target user's profile
        if hasattr(target_user, 'profile'):
            target_profile = target_user.profile
        else:
            # Create profile if it doesn't exist
            target_profile, created = UserProfile.objects.get_or_create(user=target_user)
        
        # Super Admin can manage everyone except themselves for dangerous operations
        if self.is_super_admin:
            return True
        
        # Admin can only manage regular users, not other admins or super admins
        if self.is_admin and not self.is_super_admin:
            return not target_profile.is_admin and not target_profile.is_super_admin
        
        # Regular users can't manage anyone
        return False
    
    def __str__(self):
        return f"{self.user.username} Profile"

class CarsStandard(models.Model):
    brand_norm = models.CharField(max_length=100, blank=True, null=True)
    model_group_norm = models.CharField(max_length=100, blank=True, null=True)
    model_norm = models.CharField(max_length=100, blank=True, null=True)
    variant_norm = models.CharField(max_length=100, blank=True, null=True)
    model_group_raw = models.CharField(max_length=100, blank=True, null=True)
    model_raw = models.CharField(max_length=100, blank=True, null=True)
    variant_raw = models.CharField(max_length=100, blank=True, null=True)
    variant_raw2 = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.brand_norm} {self.model_norm} {self.variant_norm}"

class CarsCarlistmy(models.Model):
    listing_url = models.TextField(unique=True)
    condition = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    model_group = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    variant = models.CharField(max_length=100, blank=True, null=True)
    information_ads = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=2, blank=True, null=True)
    engine_cc = models.CharField(max_length=50, blank=True, null=True)
    fuel_type = models.CharField(max_length=50, blank=True, null=True)
    last_scraped_at = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    images = models.TextField(blank=True, null=True)
    last_status_check = models.DateTimeField(auto_now_add=True, null=True)
    information_ads_date = models.DateField(blank=True, null=True)
    ads_tag = models.CharField(max_length=50, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    source = models.CharField(max_length=15, blank=True, null=True)
    cars_standard = models.ForeignKey('CarsStandard', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year})"

class PriceHistoryCarlistmy(models.Model):
    car = models.ForeignKey('CarsCarlistmy', on_delete=models.CASCADE, to_field='listing_url', db_column='listing_url')
    old_price = models.IntegerField(blank=True, null=True)
    new_price = models.IntegerField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('car', 'changed_at')
        constraints = [
            models.CheckConstraint(check=models.Q(car__isnull=False), name='car_not_null_carlistmy')
        ]
    
    def __str__(self):
        return f"Price change for {self.car} at {self.changed_at}"

class CarsMudahmy(models.Model):
    listing_url = models.TextField(unique=True)
    condition = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    model_group = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    variant = models.CharField(max_length=100, blank=True, null=True)
    information_ads = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=2, blank=True, null=True)
    engine_cc = models.CharField(max_length=50, blank=True, null=True)
    fuel_type = models.CharField(max_length=50, blank=True, null=True)
    last_scraped_at = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    images = models.TextField(blank=True, null=True)
    last_status_check = models.DateTimeField(auto_now_add=True, null=True)
    information_ads_date = models.DateField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    source = models.CharField(max_length=15, blank=True, null=True)
    cars_standard = models.ForeignKey('CarsStandard', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year})"

class PriceHistoryMudahmy(models.Model):
    car = models.ForeignKey('CarsMudahmy', on_delete=models.CASCADE, to_field='listing_url', db_column='listing_url')
    old_price = models.IntegerField(blank=True, null=True)
    new_price = models.IntegerField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('car', 'changed_at')
        constraints = [
            models.CheckConstraint(check=models.Q(car__isnull=False), name='car_not_null_mudahmy')
        ]

    def __str__(self):
        return f"Price change for {self.car} at {self.changed_at}"

class LocationStandard(models.Model):
    states = models.CharField(max_length=255)
    district = models.CharField(max_length=255)
    town = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="Latitude coordinate in decimal degrees")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="Longitude coordinate in decimal degrees")
    location_raw1 = models.CharField(max_length=255, blank=True, null=True)
    location_raw2 = models.CharField(max_length=255, blank=True, null=True)
    location_raw3 = models.CharField(max_length=255, blank=True, null=True)
    location_raw4 = models.CharField(max_length=255, blank=True, null=True)
    location_raw5 = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.town}, {self.district}, {self.states}"

class SyncStatus(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('success', 'Success'),
        ('failure', 'Failure'),
    ]
    
    task_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    progress_percentage = models.IntegerField(default=0)
    current_step = models.CharField(max_length=255, blank=True, null=True)
    total_steps = models.IntegerField(default=1)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Sync {self.task_id} - {self.status}"
    
    @classmethod
    def get_latest_sync(cls):
        """Get the latest sync status"""
        return cls.objects.first()
    
    @classmethod
    def is_sync_running(cls):
        """Check if there's currently a sync running"""
        return cls.objects.filter(status='in_progress').exists()