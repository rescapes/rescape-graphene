import json

from django.contrib.gis.geos import GEOSGeometry

import graphene
from graphene.types.generic import GenericScalar
from graphql.language import ast

from .. import resolver

__all__ = [
    'GrapheneGeometry',
    'GeometryObjectType',
]


class GrapheneGeometry(graphene.Scalar):
    """
        Graphene representation for a GeoDjango GeometryField, which can contain the feature of a geojson blob
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
        return GEOSGeometry(value)


class GeometryObjectType(graphene.ObjectType):
    """
        Graphene representation of a GeoDjango Geometry object
    """
    type = graphene.String()
    coordinates = GenericScalar()

    class Meta:
        default_resolver = resolver.geometry_resolver
        description = """
`GeometryObjectType` represents a pair of values:
- Geometry `type`
- Geometry `coordinates`
"""

