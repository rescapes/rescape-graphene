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
    'GeometryCoordinates'
]


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
        # Do nothing, let the view serializer to the arrays to json
        return value

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

            def handle_floats(v):
                if hasattr(v, 'values'):
                    # Multiple floats:w
                    return R.map(
                        lambda fv: float(fv.value),
                        v.values
                    )
                else:
                    # Single float
                    return float(v.value)

            return R.if_else(
                lambda v: R.isinstance(ListValue, R.head(v.values) if hasattr(v, 'values') else v),
                # ListValues
                lambda v: [reduce(v.values)],
                # FloatValues or single FloatValue
                lambda v: [handle_floats(v)]
            )(value)

        def reduce(values):
            return R.reduce(
                lambda accum, list_values: R.concat(accum, map_value(list_values)),
                [],
                values
            )

        # Create the coordinates by reducing node.values=[node.values=[node.floats], node.value, ...]
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
    # Coordinates can be a single lat,lon array, list of lat,lons, polygons, etc. So make this generic for full
    # flexibility
    coordinates = GenericScalar()

    class Meta:
        default_resolver = geometry_resolver
        description = """
`GeometryObjectType` represents a pair of values:
- Geometry `type`
- Geometry `coordinates`
"""
