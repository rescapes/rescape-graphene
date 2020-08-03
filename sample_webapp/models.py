from django.contrib.auth import get_user_model
from django.contrib.gis.db import models
from django.contrib.gis.db.models import GeometryCollectionField, Model
from django.contrib.postgres.fields import JSONField
from django.db.models import CharField, DateTimeField, ForeignKey, ManyToManyField

import reversion
from django.contrib.auth.models import User, Group

# Register Revisions for User and Group
if not reversion.is_registered(User):
    reversion.register(User)
if not reversion.is_registered(Group):
    reversion.register(Group)

@reversion.register()
class Bar(Model):
    key = CharField(max_length=20, unique=True, null=False)

@reversion.register()
class Foo(Model):
    """
        Models a sample model with a json field and user foreign key
    """

    # Unique human readable identifier for URLs, etc
    key = CharField(max_length=20, unique=True, null=False)
    name = CharField(max_length=50, unique=False, null=False)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    # Example of a json field
    data = JSONField(null=False, default=dict(example=1.1))

    # Example of a foreign key
    user = ForeignKey(get_user_model(), on_delete=models.DO_NOTHING)
    bars = ManyToManyField(Bar)
    # Example of geojson container
    geo_collection = GeometryCollectionField(null=False)
    # This stores the full geojson, whereas geo_collection only stores geometry for PostGIS operations
    # The two must be kept in sync. It might be better to get rid of geo_collection and just use this
    geojson = JSONField()

    class Meta:
        app_label = "sample_webapp"

    def __str__(self):
        return self.name
