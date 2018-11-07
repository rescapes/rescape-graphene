import json

from django.contrib.gis import geos
from django.test import TestCase
from rescape_python_helpers import geometrycollection_from_feature_collection

from rescape_graphene.schema_models.geojson.types import GrapheneFeatureCollection


class TypesTests(TestCase):

    def test_feature_collection_geojson_input(self):
        geojson = {
            'copyright': '2018',
            'generator': 'Me made it',
            'type': 'FeatureCollection',
            'features': [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[49.5294835476, 2.51357303225], [51.4750237087, 2.51357303225],
                             [51.4750237087, 6.15665815596],
                             [49.5294835476, 6.15665815596], [49.5294835476, 2.51357303225]]]
                    },
                    "properties": {
                        "something": "great",
                        "else": {
                            "some": "embedded"
                        }
                    }
                },
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[49.5294835476, 2.51357303225], [51.4750237087, 2.51357303225],
                             [51.4750237087, 6.15665815596],
                             [49.5294835476, 6.15665815596], [49.5294835476, 2.51357303225]]]
                    }
                }
            ]
        }
        feature_collection = geometrycollection_from_feature_collection(geojson)
        # Test serialize
        geometry_type = GrapheneFeatureCollection()
        serialized = geometry_type.serialize(feature_collection)
        self.assertEqual(feature_collection.geom_type, serialized['type'])

        # Go backwards and parse
        geojson_parsed = geometry_type.parse_value(serialized)
        self.assertEqual(geojson_parsed, feature_collection)