from __future__ import annotations
from django.db import models
from django.utils.timezone import now


def data_directory_path(instance, filename):
    return 'data/{0}/{1}'.format(instance.name, filename)

# Create your models here.
class State(models.Model):
    mode = models.CharField(max_length=10)
    threshold = models.FloatField(default=85)
    work = models.BooleanField(default=False)
    progress = models.IntegerField(default=100)
    target_model = models.CharField(max_length=30, default='')


class Data(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    source_pc = models.CharField(max_length=10, null=True, blank=True)
    original_image = models.ImageField(
        upload_to=data_directory_path, null=True, blank=True)
    segmentation_image = models.ImageField(
        upload_to=data_directory_path, null=True, blank=True)
    margin_ratio = models.FloatField(null=True, blank=True)
    created_date = models.DateField(auto_now_add=True)
    cvat_url = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.name


class Bbox(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    data = models.ForeignKey(
        Data, on_delete=models.CASCADE, related_name='bbox', null=True)
    min_margin_ratio = models.FloatField(null=True, blank=True)
    box_x = models.IntegerField(null=True, blank=True)
    box_y = models.IntegerField(null=True, blank=True)
    box_width = models.IntegerField(null=True, blank=True)
    box_height = models.IntegerField(null=True, blank=True)
    # margin = models.ManyToManyField(Margin, related_name='bbox', blank=True)

    def __str__(self):
        return self.name


class Margin(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    bbox = models.ForeignKey(
        Bbox, on_delete=models.CASCADE, related_name='margin', null=True)
    margin_x = models.IntegerField(null=True, blank=True)
    margin_y = models.IntegerField(null=True, blank=True)
    real_margin = models.FloatField(null=True, blank=True)
    margin_ratio = models.FloatField(null=True, blank=True)
    margin_width = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.name

class ManualLog(models.Model):
    filename = models.CharField(max_length=50)
    dt = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.filename

class InferencePath(models.Model):
    name = models.CharField(max_length=50)
    path = models.CharField(max_length=50)
    acc = models.IntegerField()

    def __str__(self):
        return self.name + ': ' + str(self.acc)
