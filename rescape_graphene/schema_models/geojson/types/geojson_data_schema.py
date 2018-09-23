from graphene import String, ObjectType, Field

from rescape_graphene.schema_models.geojson.types import GrapheneGeometry
from rescape_graphene.graphql_helpers.json_field_helpers import resolver_for_dict_field
from rescape_python_helpers import ramda as R


feature_geometry_data_type_fields = dict(
    # Polygon, Linestring, Point, etc
    type=dict(type=String),
    coordinates=dict(type=GrapheneGeometry)
)

# This matches the fields of GeoDjango's GeometryCollectionField features[...].geometry property
FeatureGeometryDataType = type(
    'FeatureGeometryDataType',
    (ObjectType,),
    R.map_with_obj(
        # If we have a type_modifier function, pass the type to it, otherwise simply construct the type
        lambda k, v: R.prop_or(lambda typ: typ(), 'type_modifier', v)(R.prop('type', v)),
        feature_geometry_data_type_fields
    )
)

feature_data_type_fields = dict(
    # Always Feature
    type=dict(type=String),
    geometry=dict(
        type=FeatureGeometryDataType,
        graphene_type=FeatureGeometryDataType,
        fields=feature_geometry_data_type_fields,
        type_modifier=lambda typ: Field(typ, resolver=resolver_for_dict_field),
    )
)

# This matches the fields of GeoDjango's GeometryCollectionField features property
FeatureDataType = type(
    'FeatureDataType',
    (ObjectType,),
    R.map_with_obj(
        # If we have a type_modifier function, pass the type to it, otherwise simply construct the type
        lambda k, v: R.prop_or(lambda typ: typ(), 'type_modifier', v)(R.prop('type', v)),
        feature_data_type_fields)
)
