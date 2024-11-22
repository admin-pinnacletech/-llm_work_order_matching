from django.db import models
import uuid

class Asset(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    rawData = models.JSONField()
    tenantId = models.CharField(max_length=100)
    facilityScenarioId = models.CharField(max_length=100)

    class Meta:
        db_table = 'assets'

    def __str__(self):
        return f"Asset-{self.id}"

class Component(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    rawData = models.JSONField()
    tenantId = models.CharField(max_length=100)
    facilityScenarioId = models.CharField(max_length=100)

    class Meta:
        db_table = 'components'

    def __str__(self):
        return f"Component-{self.id}"

class WorkOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    externalId = models.CharField(max_length=100, unique=True)
    rawData = models.JSONField()
    tenantId = models.CharField(max_length=100)
    facilityScenarioId = models.CharField(max_length=100)

    class Meta:
        db_table = 'workOrders'

    def __str__(self):
        return f"WO-{self.externalId}"

class Assessment(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    rawData = models.JSONField()
    tenantId = models.CharField(max_length=100)
    facilityScenarioId = models.CharField(max_length=100)

    class Meta:
        db_table = 'assessments'

    def __str__(self):
        return f"Assessment-{self.id}"

class Tenant(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    rawData = models.JSONField()

    class Meta:
        db_table = 'tenants'

    def __str__(self):
        return f"Tenant-{self.name}"
    
class Facility(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    tenantId = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    rawData = models.JSONField()
    class Meta:
        db_table = 'facilities'

    def __str__(self):
        return f"Facility-{self.name}"
    
class FacilityScenario(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    tenantId = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    facilityId = models.ForeignKey(Facility, on_delete=models.CASCADE)
    rawData = models.JSONField(null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facilityScenarios'
        unique_together = ('tenantId', 'facilityId', 'id')

    def __str__(self):
        return f"FacilityScenario-{self.name}"
