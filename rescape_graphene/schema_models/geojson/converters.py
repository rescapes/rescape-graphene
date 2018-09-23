
from django.contrib.gis.db import models

import graphene
from graphene_django.converter import convert_django_field


@convert_django_field.register(models.GeometryField)
def convert_field_to_geometry(field, registry=None):
    return graphene.Field(
        'GeometryType',
        description=field.help_text,
        required=not field.null)

@convert_django_field.register(models.GeometryCollectionField)
def convert_field_to_geometry_collection(field, registry=None):
    return graphene.Field(
        'GeometryCollectionType',
        description=field.help_text,
        required=not field.null)