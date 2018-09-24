from graphene import String, ObjectType, Field

from rescape_graphene.graphql_helpers.json_field_helpers import resolver_for_dict_field, type_modify_fields
from rescape_python_helpers import ramda as R

from rescape_graphene.schema_models.geojson.types.geometry import GeometryCoordinates

feature_geometry_data_type_fields = dict(
    # Polygon, Linestring, Point, etc
    type=dict(type=String),
    # Geometry Coordinates is a graphene.Scalar specially designed to handle arrays of of coordinates,
    # Either a single array point, a linestring array of points, or a (multi)polygon, array of array of points
    coordinates=dict(type=GeometryCoordinates)
)

# This matches the fields of GeoDjango's GeometryCollectionField features[...].geometry property
FeatureGeometryDataType = type(
    'FeatureGeometryDataType',
    (ObjectType,),
    type_modify_fields(feature_geometry_data_type_fields)
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
    type_modify_fields(feature_data_type_fields)
)
