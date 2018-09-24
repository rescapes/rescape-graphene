import json
import graphene
from graphene import String, List
from graphql.language import ast
from rescape_python_helpers import ramda as R
from rescape_python_helpers import geometrycollection_from_feature_collection

from rescape_graphene.graphql_helpers.json_field_helpers import resolver_for_dict_list, type_modify_fields
from rescape_graphene.schema_models.geojson.types.geojson_data_schema import FeatureDataType, feature_data_type_fields
from rescape_graphene.schema_models.geojson.resolvers import geometry_collection_resolver
from rescape_graphene.schema_models.geojson.types import GeometryType

__all__ = [
    'GrapheneGeometryCollection',
    'GeometryCollectionType',
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
        return geometrycollection_from_feature_collection(
            dict(type='FeatureCollection', features=R.map(
                lambda geometry: dict(type='Feature', geometry=geometry),
                value['geometries'])
             )
        )


geometry_collection_fields = dict(
    # type is always 'FeatureCollection'
    type=dict(type=String),
    features=dict(
        type=FeatureDataType,
        graphene_type=FeatureDataType,
        fields=feature_data_type_fields,
        type_modifier=lambda typ: List(typ) #, resolver=resolver_for_dict_list)
    )
)

# This matches the fields of GeoDjango's GeometryCollectionField
GeometryCollectionType = type(
    'GeometryCollectionType',
    (graphene.ObjectType,),
    type_modify_fields(geometry_collection_fields)
)


class GeometryCollectionTypeX(graphene.ObjectType):
    """
        Graphene representation of a GeoDjango GeometryCollection object
    """
    geometries = graphene.List(GeometryType)

    class Meta:
        default_resolver = geometry_collection_resolver
        description = """
`GeometryCollectionObjectType` represents a pair of values:
- Geometry `type`
- Geometry `coordinates`
"""
