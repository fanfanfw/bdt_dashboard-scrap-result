from django.db import models
from django.contrib.postgres.fields import ArrayField

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