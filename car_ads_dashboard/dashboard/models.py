from django.db import models
from django.contrib.postgres.fields import ArrayField

class CarsStandard(models.Model):
    brand_norm = models.CharField(max_length=255, blank=True, null=True)
    model_norm = models.CharField(max_length=255, blank=True, null=True)
    variant_norm = models.CharField(max_length=255, blank=True, null=True)
    model_raw = models.CharField(max_length=255, blank=True, null=True)
    variant_raw = models.CharField(max_length=255, blank=True, null=True)
    variant_raw2 = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.brand_norm} {self.model_norm} {self.variant_norm}"

class CarsCarlistmy(models.Model):
    listing_url = models.TextField(unique=True)
    brand = models.CharField(max_length=50, blank=True, null=True)
    model = models.CharField(max_length=50, blank=True, null=True)
    variant = models.CharField(max_length=50, blank=True, null=True)
    informasi_iklan = models.TextField(blank=True, null=True)
    lokasi = models.CharField(max_length=255, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=2, blank=True, null=True)
    gambar = ArrayField(models.TextField(), blank=True, null=True)
    last_scraped_at = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    source = models.CharField(max_length=15, blank=True, null=True)
    cars_standard = models.ForeignKey(CarsStandard, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year})"

class PriceHistoryCarlistmy(models.Model):
    car = models.ForeignKey(CarsCarlistmy, on_delete=models.CASCADE, related_name='price_histories')
    old_price = models.IntegerField(blank=True, null=True)
    new_price = models.IntegerField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('car', 'changed_at')

    def __str__(self):
        return f"Price change {self.car} at {self.changed_at}"

class CarsMudahmy(models.Model):
    listing_url = models.TextField(unique=True)
    brand = models.CharField(max_length=50, blank=True, null=True)
    model = models.CharField(max_length=50, blank=True, null=True)
    variant = models.CharField(max_length=50, blank=True, null=True)
    informasi_iklan = models.TextField(blank=True, null=True)
    lokasi = models.CharField(max_length=255, blank=True, null=True)
    price = models.IntegerField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    mileage = models.IntegerField(blank=True, null=True)
    transmission = models.CharField(max_length=50, blank=True, null=True)
    seat_capacity = models.CharField(max_length=2, blank=True, null=True)
    gambar = ArrayField(models.TextField(), blank=True, null=True)
    last_scraped_at = models.DateTimeField(auto_now=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='active')
    source = models.CharField(max_length=15, blank=True, null=True)
    cars_standard = models.ForeignKey(CarsStandard, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.brand} {self.model} {self.variant} ({self.year})"

class PriceHistoryMudahmy(models.Model):
    car = models.ForeignKey(CarsMudahmy, on_delete=models.CASCADE, related_name='price_histories')
    old_price = models.IntegerField(blank=True, null=True)
    new_price = models.IntegerField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('car', 'changed_at')

    def __str__(self):
        return f"Price change {self.car} at {self.changed_at}"
