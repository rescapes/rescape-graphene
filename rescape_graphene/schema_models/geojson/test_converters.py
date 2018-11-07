from django.contrib.gis.db import models
from django.test import TestCase

from graphene_django.converter import convert_django_field

from rescape_graphene.schema_models.geojson.types.feature_collection import FeatureCollectionDataType


class ConverterTests(TestCase):

    def test_convert_feature_collection(self):
        field = models.GeometryCollectionField()
        graphene_type = convert_django_field(field)
        self.assertEqual(graphene_type.type.of_type, FeatureCollectionDataType)