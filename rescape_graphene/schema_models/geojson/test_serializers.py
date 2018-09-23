import json

from django.contrib.gis import geos
from django.test import TestCase
from rescape_python_helpers import geometrycollection_from_feature_collection

from rescape_graphene import GrapheneGeometry
from rescape_graphene.schema_models.geojson.types import GrapheneGeometryCollection


class TypesTests(TestCase):

    def test_geometry_geojson_input(self):
        geometry = geos.Point(1, 0)
        geometry_type = GrapheneGeometry()

        # Test Serialize
        serialized = geometry_type.serialize(geometry)
        self.assertEqual(geometry.geom_type, serialized['type'])

        # Go backwards and parse
        geojson_parsed = geometry_type.parse_value(serialized)
        self.assertEqual(geojson_parsed.geojson, geometry.geojson)

    def test_geometry_collection_geojson_input(self):
        geojson = {
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
        geometry_collection = geometrycollection_from_feature_collection(geojson)
        # Test serialize
        geometry_type = GrapheneGeometryCollection()
        serialized = geometry_type.serialize(geometry_collection)
        self.assertEqual(geometry_collection.geom_type, serialized['type'])

