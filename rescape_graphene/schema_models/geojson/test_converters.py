from django.contrib.gis.db import models
from django.test import TestCase

from graphene_django.converter import convert_django_field
from rescape_graphene.schema_models.geojson.types import GeometryObjectType
from rescape_graphene.schema_models.geojson.types.geometry_collection import GeometryCollectionObjectType


class ConverterTests(TestCase):

    def test_convert_geometry(self):
        field = models.GeometryField()
        graphene_type = convert_django_field(field)
        self.assertEqual(graphene_type.type.of_type, GeometryObjectType)

    def test_convert_geometry_collection(self):
        field = models.GeometryCollectionField()
        graphene_type = convert_django_field(field)
        self.assertEqual(graphene_type.type.of_type, GeometryCollectionObjectType)