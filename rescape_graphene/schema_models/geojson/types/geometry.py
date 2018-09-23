import json
import pickle

from graphql.language.ast import ListValue
from rescape_python_helpers import ramda as R
from django.contrib.gis.geos import GEOSGeometry

import graphene
from graphene.types.generic import GenericScalar
from graphql.language import ast

from rescape_graphene.schema_models.geojson.resolvers import geometry_resolver

__all__ = [
    'GrapheneGeometry',
    'GeometryType',
]


class GrapheneGeometry(graphene.Scalar):
    """
        Graphene representation for a GeoDjango Coordinates
    """

    class Meta:
        description = """
`Geometry` coordinates are one, two, or three dimensional array of floats representing points
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


class GeometryCoordinates(graphene.Scalar):
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
        return pickle.dumps(value)

    @classmethod
    def parse_literal(cls, node):
        """
            Parses any array string
        :param node:
        :return:
        """

        def map_value(value):
            """
                value is either a ListValue with values that are ListValues or a ListValue with values that
                are FloatValues
            :param value:
            :return:
            """
            return R.if_else(
                    lambda v: R.isinstance(ListValue, R.head(v.values)),
                    # ListValues
                    lambda v: [reduce(v.values)],
                    # FloatValues
                    lambda v: [R.map(lambda fv: float(fv.value), v.values)]
            )(value)

        def reduce(values):
            return R.reduce(
                lambda accum, list_values: R.concat(accum, map_value(list_values)),
                [],
                values
            )

        # Create the coordinatew by reducing node.values=[node.values=[node.floats], node.value, ...]
        return R.reduce(
            lambda accum, list_values: reduce(node.values),
            [],
            reduce(node.values)
        )

    @classmethod
    def parse_value(cls, value):
        return value


class GeometryType(graphene.ObjectType):
    """
        Graphene representation of a GeoDjango Geometry object
    """
    type = graphene.String()
    coordinates = GenericScalar()

    class Meta:
        default_resolver = geometry_resolver
        description = """
`GeometryObjectType` represents a pair of values:
- Geometry `type`
- Geometry `coordinates`
"""
