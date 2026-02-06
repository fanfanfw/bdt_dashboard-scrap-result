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

        # Auto-approve if user is Admin or superuser
        if self.user.groups.filter(name='Admin').exists() or self.user.is_superuser:
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
        if self.user.groups.filter(name='Admin').exists() or self.user.is_superuser:
            return "Admin"
        elif self.user.groups.filter(name='User').exists():
            return "User"
        else:
            return "No Role"

    @property
    def is_admin(self):
        """Check if user is admin"""
        return self.user.groups.filter(name='Admin').exists() or self.user.is_superuser
    
    def can_manage_user(self, target_user):
        """Check if this user can manage target user"""
        # Get target user's profile
        if hasattr(target_user, 'profile'):
            target_profile = target_user.profile
        else:
            # Create profile if it doesn't exist
            target_profile, created = UserProfile.objects.get_or_create(user=target_user)

        # Admin can manage User role only, not other Admins
        if self.is_admin:
            return not target_profile.is_admin

        # Regular users can't manage anyone
        return False
    
    def __str__(self):
        return f"{self.user.username} Profile"

# CarsStandard model moved to unmanaged model for db_test database

# CarsCarlistmy model replaced by CarsUnified in db_test database

# PriceHistoryCarlistmy model replaced by PriceHistoryUnified in db_test database

# CarsMudahmy model replaced by CarsUnified in db_test database

# PriceHistoryMudahmy model replaced by PriceHistoryUnified in db_test database

# ========================
# UNMANAGED MODELS FOR db_test DATABASE
# ========================

class CarsStandard(models.Model):
    """
    Unmanaged model for cars_standard table in db_test database
    Read-only access for car standardization data
    """
    id = models.BigAutoField(primary_key=True)
    brand_norm = models.CharField(max_length=100)
    model_group_norm = models.CharField(max_length=100)
    model_norm = models.CharField(max_length=100)
    variant_norm = models.CharField(max_length=100)
    model_group_raw = models.CharField(max_length=100, blank=True, null=True)
    model_raw = models.CharField(max_length=100, blank=True, null=True)
    variant_raw = models.CharField(max_length=100, blank=True, null=True)
    variant_raw2 = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False  # No migrations for this model
        db_table = 'cars_standard'

    def __str__(self):
        return f"{self.brand_norm} {self.model_norm} {self.variant_norm}"

class CarsUnified(models.Model):
    """
    Unified model for cars data from both carlistmy and mudahmy sources
    Read-only access to cars_unified table in db_test database
    """
    id = models.BigAutoField(primary_key=True)
    cars_standard = models.ForeignKey(CarsStandard, on_delete=models.CASCADE, null=True, blank=True, db_column='cars_standard_id')
    source = models.CharField(max_length=20, choices=[('carlistmy', 'Carlist.my'), ('mudahmy', 'Mudah.my')])
    listing_id = models.TextField(blank=True, null=True)
    listing_url = models.TextField()
    condition = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    variant = models.CharField(max_length=100, blank=True, null=True)
    series = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=100, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=10, blank=True, null=True)
    engine_cc = models.CharField(max_length=50, blank=True, null=True)
    fuel_type = models.CharField(max_length=50, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    information_ads = models.TextField(blank=True, null=True)
    images = ArrayField(models.TextField(), blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(blank=True, null=True)
    last_scraped_at = models.DateTimeField(blank=True, null=True)
    version = models.IntegerField(default=1)
    information_ads_date = models.DateField(blank=True, null=True)

    class Meta:
        managed = False  # No migrations for this model
        db_table = 'cars_unified'

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year}) - {self.source}"

class PriceHistoryUnified(models.Model):
    """
    Unified model for price history from both carlistmy and mudahmy sources
    Read-only access to price_history_unified table in db_test database
    """
    id = models.BigAutoField(primary_key=True)
    source = models.CharField(max_length=20, choices=[('carlistmy', 'Carlist.my'), ('mudahmy', 'Mudah.my')])
    listing_id = models.TextField(blank=True, null=True)
    old_price = models.IntegerField(blank=True, null=True)
    new_price = models.IntegerField()
    listing_url = models.TextField()
    changed_at = models.DateTimeField()

    class Meta:
        managed = False  # No migrations for this model
        db_table = 'price_history_unified'

    def __str__(self):
        return f"Price change {self.listing_url} at {self.changed_at}"

class Carsome(models.Model):
    """
    Unmanaged model for carsome table (Carsome marketplace inventory)
    """
    id = models.BigAutoField(primary_key=True)
    image = models.TextField(blank=True, null=True)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    model_group = models.CharField(max_length=100, blank=True, null=True, default='NO MODEL GROUP')
    variant = models.CharField(max_length=100, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    last_updated_at = models.DateTimeField(blank=True, null=True)
    cars_standard = models.ForeignKey(
        CarsStandard,
        on_delete=models.DO_NOTHING,
        db_column='cars_standard_id',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, default='active')
    is_deleted = models.BooleanField(default=False)
    source = models.CharField(max_length=50, default='carsome')
    reg_no = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'carsome'

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year}) - Carsome"

class NormalizedCarsInventoryManager(models.Manager):
    """Exposes only listings mapped to cars_standard."""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related('cars_standard')
            .filter(cars_standard__isnull=False)
        )


class CarsInventory(models.Model):
    """
    Unified read-only view that combines cars_unified and carsome tables
    """
    id = models.BigIntegerField(primary_key=True)
    cars_standard = models.ForeignKey(
        CarsStandard,
        on_delete=models.DO_NOTHING,
        db_column='cars_standard_id',
        null=True,
        blank=True,
        db_constraint=False
    )
    source = models.CharField(max_length=20)
    listing_id = models.TextField(blank=True, null=True)
    listing_url = models.TextField()
    condition = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    variant = models.CharField(max_length=100, blank=True, null=True)
    series = models.CharField(max_length=100, blank=True, null=True)
    type = models.CharField(max_length=100, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=10, blank=True, null=True)
    engine_cc = models.CharField(max_length=50, blank=True, null=True)
    fuel_type = models.CharField(max_length=50, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    information_ads = models.TextField(blank=True, null=True)
    images = ArrayField(models.TextField(), blank=True, null=True)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(blank=True, null=True)
    last_scraped_at = models.DateTimeField(blank=True, null=True)
    version = models.IntegerField(default=1)
    information_ads_date = models.DateField(blank=True, null=True)
    original_id = models.BigIntegerField()
    origin_table = models.CharField(max_length=20)
    reg_no = models.CharField(max_length=100, blank=True, null=True)
    carsome_created_at = models.DateTimeField(blank=True, null=True)

    objects = NormalizedCarsInventoryManager()
    all_objects = models.Manager()

    class Meta:
        managed = False
        db_table = 'cars_dashboard_combined'

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year}) - {self.source}"

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
