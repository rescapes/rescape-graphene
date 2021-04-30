import json
import graphene
from graphene import String, List
from graphql.language import ast
from rescape_python_helpers import ramda as R
from rescape_python_helpers import geometrycollection_from_feature_collection

from rescape_graphene.graphql_helpers.json_field_helpers import resolver_for_dict_list
from rescape_graphene.graphql_helpers.schema_helpers import type_modify_fields
from rescape_graphene.schema_models.geojson.types.geojson_data_schema import FeatureDataType, feature_data_type_fields

__all__ = [
    'GrapheneFeatureCollection',
    'FeatureCollectionDataType',
]


class GrapheneFeatureCollection(graphene.Scalar):
    """
        Graphene representation for a GeoDjango FeatureCollection
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


feature_collection_data_type_fields = dict(
    # type is always 'FeatureCollection'
    type=dict(type=String),
    features=dict(
        type=FeatureDataType,
        graphene_type=FeatureDataType,
        fields=feature_data_type_fields,
        type_modifier=lambda *type_and_args: List(*type_and_args, resolver=resolver_for_dict_list)
    ),
    generator=dict(type=String),
    copyright=dict(type=String)
)

# represents a geojson holding a feature collection
FeatureCollectionDataType = type(
    'FeatureCollectionDataType',
    (graphene.ObjectType,),
    type_modify_fields(feature_collection_data_type_fields)
)
