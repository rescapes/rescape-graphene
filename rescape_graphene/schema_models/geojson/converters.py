
from django.contrib.gis.db import models

import graphene
from graphene_django.converter import convert_django_field

from rescape_graphene.schema_models.geojson.types import FeatureCollectionDataType

@convert_django_field.register(models.GeometryCollectionField)
def convert_field_to_feature_collection(field, registry=None):
    """
    This converts a GeometryCollectionField, which holds a GEOSGeometryCollection, into a FeatureCollectionDataType
    We are trending toward avoiding GeometryCollectionField in favor of Json fields, so this might not be relevant
    :param field:
    :param registry:
    :return:
    """
    return graphene.Field(
        FeatureCollectionDataType,
        description=field.help_text,
        required=not field.null)