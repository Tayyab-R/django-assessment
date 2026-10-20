from django.db import models

# Create your models here.

class FuelStation(models.Model):
    source_id = models.BigIntegerField(unique=False)
    name = models.CharField(max_length=50)
    
    address = models.CharField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    
    rack_id = models.IntegerField()    
    retail_price = models.DecimalField()

    latitude = models.DecimalField(null=True)
    longitude = models.DecimalField(null=True)