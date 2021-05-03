import graphene
from django.contrib.auth import get_user_model
from graphene import ObjectType, Float, InputObjectType, Field, Mutation, List
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required
from rescape_python_helpers import ramda as R
from rescape_python_helpers.geospatial.geometry_helpers import ewkt_from_feature_collection

from rescape_graphene import increment_prop_until_unique, enforce_unique_props
from rescape_graphene.graphql_helpers.json_field_helpers import model_resolver_for_dict_field, \
    resolver_for_feature_collection, resolver_for_dict_field
from rescape_graphene.graphql_helpers.schema_helpers import REQUIRE, \
    merge_with_django_properties, guess_update_or_create, \
    CREATE, UPDATE, input_type_parameters_for_update_or_create, graphql_update_or_create, graphql_query, \
    input_type_fields, DENY, IGNORE, top_level_allowed_filter_arguments, allowed_filter_arguments, \
    update_or_create_with_revision, process_filter_kwargs, process_filter_kwargs_with_to_manys, query_sequentially, \
    type_modify_fields
from rescape_graphene.schema_models.geojson.types.feature_collection import FeatureCollectionDataType, \
    feature_collection_data_type_fields
from rescape_graphene.schema_models.user_schema import UserType, user_fields
from sample_webapp.models import Foo, Bar


class BarType(DjangoObjectType):
    """
        This is the Graphene Type for Bar.
    """
    id = graphene.Int(source='pk')

    class Meta:
        model = Bar


bar_fields = merge_with_django_properties(BarType, dict(
    id=dict(create=DENY, update=REQUIRE),
    key=dict(create=REQUIRE, unique_with=increment_prop_until_unique(Bar, None, 'key', {})),
))

bar_mutation_config = dict(
    class_name='Bar',
    crud={
        CREATE: 'createBar',
        UPDATE: 'updateBar'
    },
    resolve=guess_update_or_create
)

foo_data_fields = dict(
    example=dict(type=Float),
    # References a User stored in a blob. This tests our ability to reference Django model instance ids in json blobs
    # and resolve them correctly.
    # For simplicity we limit fields to id. Mutations can only us id, and a query doesn't need other
    # details of the user--it can query separately for that. We could offer all fields in a query only
    # version of these fields
    friend=dict(
        type=UserType,
        graphene_type=UserType,
        fields=user_fields,
        type_modifier=lambda *type_and_args: Field(
            *type_and_args,
            resolver=model_resolver_for_dict_field(get_user_model())
        )
    )
)

# This is the Graphene type for the Foo.data field. Note that we use foo_data_fields for the Field
# and pass them through type_modify_fields to handle the type_modifier lambda of Foo.data['friend']
FooDataType = type(
    'FooDataType',
    (ObjectType,),
    type_modify_fields(foo_data_fields)
)


class FooType(DjangoObjectType):
    """
        This is the Graphene Type for Foo.
    """
    id = graphene.Int(source='pk')

    class Meta:
        model = Foo


# Modify data field to use the resolver.
# There's no way to specify a resolver and queryable fields upon field creation,
# since graphene just reads the underlying. Django model to generate the fields
FooType._meta.fields['data'] = Field(
    FooDataType,
    resolver=resolver_for_dict_field
)
FooType._meta.fields['geojson'] = Field(
    FeatureCollectionDataType,
    resolver=resolver_for_dict_field
)
FooType._meta.fields['geo_collection'] = Field(
    FeatureCollectionDataType,
    resolver=resolver_for_feature_collection
)

foo_fields = merge_with_django_properties(FooType, dict(
    id=dict(create=DENY, update=REQUIRE),
    key=dict(create=REQUIRE, unique_with=increment_prop_until_unique(Foo, None, 'key', {})),
    name=dict(create=REQUIRE),
    bars=dict(
        type=BarType,
        graphene_type=BarType,
        fields=bar_fields,
        type_modifier=lambda *type_and_args: List(*type_and_args)
    ),
    created_at=dict(),
    updated_at=dict(),
    # This refers to the FooDataType, which is a representation of all the json fields of Foo.data
    data=dict(graphene_type=FooDataType, fields=foo_data_fields, default=lambda: dict()),
    # This is a reference to a Django model instance.
    user=dict(graphene_type=UserType, fields=user_fields),
    geojson=dict(
        create=REQUIRE,
        graphene_type=FeatureCollectionDataType,
        fields=feature_collection_data_type_fields
    ),
    # This is just geojson as GeosGeometryCollection, so it maintains the geometry but loses other geojson properties
    # It's kept synced to the geojson in the UpsertFoo mutate function. In practice this probably isn't needed
    # since in PostGIS we could just extract the geometry from geojson
    geo_collection=dict(
        create=DENY,
        update=DENY,
        read=IGNORE,
        graphene_type=FeatureCollectionDataType,
        fields=feature_collection_data_type_fields,
    )
))


class FooQuery(ObjectType):
    id = graphene.Int(source='pk')

    foos = graphene.List(
        FooType,
        **top_level_allowed_filter_arguments(foo_fields, FooType)
    )

    @login_required
    def resolve_foos(self, info, **kwargs):
        q_expressions_sets = process_filter_kwargs_with_to_manys(Foo, **kwargs)
        return query_sequentially(Foo.objects, 'filter', q_expressions_sets)


foo_mutation_config = dict(
    class_name='Foo',
    crud={
        CREATE: 'createFoo',
        UPDATE: 'updateFoo'
    },
    resolve=guess_update_or_create
)


class UpsertFoo(Mutation):
    """
        Abstract base class for mutation
    """
    foo = Field(FooType)

    def mutate(self, info, foo_data=None):
        modified_foo_data = R.merge(
            # Make sure unique fields are enforced, here by incrementing foo.key
            enforce_unique_props(foo_fields, foo_data),
            dict(
                # Force the FeatureCollection geojson into the GEOSGeometryCollection. This is just Geometry
                geo_collection=ewkt_from_feature_collection(foo_data['geojson']) if R.prop('geojson', foo_data) else {},
                # Put the full FeatureCollection geojson into the geojson field.
                geojson=foo_data['geojson'] if R.prop('geojson', foo_data) else {}
            )
        )
        update_or_create_values = input_type_parameters_for_update_or_create(foo_fields, modified_foo_data)
        foo, created = update_or_create_with_revision(Foo, update_or_create_values)
        return UpsertFoo(foo=foo)


class CreateFoo(UpsertFoo):
    """
        Create Foo mutation class
    """

    class Arguments:
        foo_data = type('CreateFooInputType', (InputObjectType,),
                        input_type_fields(foo_fields, CREATE, FooType))(required=True)


class UpdateFoo(UpsertFoo):
    """
        Update Foo mutation class
    """

    class Arguments:
        foo_data = type('UpdateFooInputType', (InputObjectType,),
                        input_type_fields(foo_fields, UPDATE, FooType))(required=True)


graphql_update_or_create_bar = graphql_update_or_create(bar_mutation_config, bar_fields)
graphql_query_bars = graphql_query(BarType, bar_fields, 'bars')

graphql_update_or_create_foo = graphql_update_or_create(foo_mutation_config, foo_fields)
graphql_query_foos = graphql_query(FooType, foo_fields, 'foos')


class FooMutation(graphene.ObjectType):
    create_foo = CreateFoo.Field()
    update_foo = UpdateFoo.Field()
