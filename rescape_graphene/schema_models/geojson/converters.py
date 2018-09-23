
from django.contrib.gis import forms
from django.contrib.gis.db import models

import graphene
from graphene_django.converter import convert_django_field
from graphene_django.forms.converter import convert_form_field

#https://raw.githubusercontent.com/flavors/django-graphql-geojson/master/graphql_geojson/converter.py
from rescape_graphene.schema_models.geojson.types import GeometryObjectType
from rescape_graphene.schema_models.geojson.types.geometry_collection import GeometryCollectionObjectType


@convert_django_field.register(models.GeometryField)
def convert_field_to_geometry(field, registry=None):
    return graphene.Field(
        GeometryObjectType,
        description=field.help_text,
        required=not field.null)

@convert_django_field.register(models.GeometryCollectionField)
def convert_field_to_geometry_collection(field, registry=None):
    return graphene.Field(
        GeometryCollectionObjectType,
        description=field.help_text,
        required=not field.null)