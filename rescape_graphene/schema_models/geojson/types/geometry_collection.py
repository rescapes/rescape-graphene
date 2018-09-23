
import json

from django.contrib.gis.geos import GeometryCollection

import graphene
from graphql.language import ast

from rescape_graphene.schema_models.geojson.types import GeometryObjectType
from .. import resolver

__all__ = [
    'GrapheneGeometryCollection',
    'GeometryCollectionObjectType',
]


class GrapheneGeometryCollection(graphene.Scalar):
    """
        Graphene representation for a GeoDjango GeometryCollectionField, which can contain the features of a geojson blob
    """

    class Meta:
        description = """
`Geometry` scalar may be represented in a few ways:
- Well-known text (WKT)
- Hexadecimal (HEX)
- GeoJSON
"""

    @classmethod
    def serialize(cls, value):
        return json.loads(value.geojson)

    @classmethod
    def parse_literal(cls, node):
        if isinstance(node, ast.StringValue):
            return cls.parse_value(node.value)
        return None

    @classmethod
    def parse_value(cls, value):
        if isinstance(value, dict):
            value = json.dumps(value)
        return GrapheneGeometryCollection(value)


class GeometryCollectionObjectType(graphene.ObjectType):
    """
        Graphene representation of a GeoDjango GeometryCollection object
    """
    geometries = graphene.List(GeometryObjectType)

    class Meta:
        default_resolver = resolver.geometry_collection_resolver
        description = """
`GeometryCollectionObjectType` represents a pair of values:
- Geometry `type`
- Geometry `coordinates`
"""