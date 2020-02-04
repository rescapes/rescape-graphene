import ast
from collections import namedtuple

from more_itertools import first
from rescape_python_helpers import ramda as R
from inflection import underscore

###
# Helpers for json fields. json fields are not a Django model,
# rather a json blob that is the field data of the Region and Resource models
###
from rescape_graphene.graphql_helpers.schema_helpers import allowed_filter_arguments


def resolve_selections(context):
    """
        Returns the query fields for the current context.
    :param {ResolveInfo} context: The graphene resolution context
    :return: {[String]} The field names to that are in the query
    """
    return R.map(lambda sel: sel.name.value, context.field_asts[0].selection_set.selections)


def pick_selections(selections, data):
    """
        Pick the selections from the current data
    :param {[Sting]} selections: The field names to that are in the query
    :param {dict} data: Data to pick from
    :return: {DataTuple} data with limited to selections
    """
    dct = R.pick(selections, data)
    return namedtuple('DataTuple', R.keys(dct))(*R.values(dct))


def resolver_for_dict_field(resource, context, **kwargs):
    """
        Resolver for the data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for drilling into json types
    :param resource:
    :param context:
    :params kwargs: Arguments to filter with
    :return:
    """
    selections = resolve_selections(context)
    field_name = context.field_name
    data = getattr(resource, field_name) if (hasattr(resource, field_name) and R.prop(field_name, resource)) else {}
    # We only let this value through if it matches the kwargs
    # TODO data doesn't include full values for embedded model values, rather just {id: ...}. So if kwargs have
    # searches on other values of the model this will fail. The solution is to load the model values, but I
    # need some way to figure out where they are in data
    passes = R.dict_matches_params_deep(kwargs, data)
    # Pick the selections from our resource json field value default to {} if resource[field_name] is null
    return pick_selections(selections, data) if passes else namedtuple('DataTuple', [])()


def resolver_for_dict_list(resource, context, **kwargs):
    """
        Resolver for the data field that is a list. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for drilling into json types.
        The property value must be a list or null. Null values will return null, list values will be processed
        in turn by graphene
    :param resource:
    :param context:
    :params kwargs: Arguments to filter with
    :return:
    """
    selections = resolve_selections(context)
    field_name = context.field_name
    value = R.prop_or([], field_name, resource)

    return R.map(
        lambda data: pick_selections(selections, data),
        R.filter(
            # We only let this value through if it matches the kwargs
            # TODO data doesn't include full values for embedded model values, rather just {id: ...}. So if kwargs have
            # searches on other values of the model this will fail. The solution is to load the model values, but I
            # need some way to figure out where they are in data
            lambda data: R.dict_matches_params_deep(kwargs, data),
            value
        )
    ) if value else None


def model_resolver_for_dict_field(model_class):
    """
        Resolves a Django model referenced in a data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for drilling into json types
        TODO this naively assumes that the 'id' property is among the query selections and uses that
        to resolve the instance
    :param model_class:
    :param resource:
    :param context:
    :params kwargs: Arguments to filter with
    :return:
    """

    from rescape_graphene.graphql_helpers.schema_helpers import flatten_query_kwargs

    def _model_resolver_for_dict_field(resource, context, **kwargs):
        field_name = underscore(context.field_name)
        id = R.prop_or(None, 'id', getattr(resource, field_name))
        # If no instance id is assigned to this data, we can't resolve it
        if not id:
            return None

        # Now filter based on any query arguments beyond id. If it doesn't match we also return None
        return first(model_class.objects.filter(
            **dict(
                # These are Q expressions
                *flatten_query_kwargs(model_class, kwargs),
                id=id
            )
        ), None)

    return _model_resolver_for_dict_field


def resolver_for_feature_collection(resource, context, **kwargs):
    """
        Like resolver but takes care of converting the geos value stored in the field to a dict that
        has the values we want to resolve, namely type and features.
    :param {string} resource: The instance whose json field data is being resolved
    :param {ResolveInfo} context: Graphene context which contains the fields queried in field_asts
    :return: {DataTuple} Standard resolver return value
    """

    # Take the camelized keys. We don't store data fields slugified. We leave them camelized
    selections = R.map(lambda sel: sel.name.value, context.field_asts[0].selection_set.selections)
    # Recover the json by parsing the string provided by GeometryCollection and mapping the geometries property to features
    json = R.compose(
        # Map the value GeometryCollection to FeatureCollection for the type property
        R.map_with_obj(lambda k, v: R.if_else(
            R.equals('type'),
            R.always('FeatureCollection'),
            R.always(v)
        )(k)),
        # Map geometries to features: [{type: Feature, geometry: geometry}]
        lambda dct: R.merge(
            # Remove geometries
            R.omit(['geometries'], dct),
            # Add features containing the geometries
            dict(features=R.map(
                lambda geometry: dict(type='Feature', geometry=geometry),
                R.prop_or([], 'geometries', dct))
            )
        ),
    )(ast.literal_eval(R.prop(context.field_name, resource).json))
    # Identify the keys that are actually in resource[json_field_name]
    all_selections = R.filter(
        lambda key: key in json,
        selections
    )
    # Pick out the values that we want
    result = R.pick(all_selections, json)

    # Return in the standard Graphene DataTuple
    return namedtuple('DataTuple', R.keys(result))(*R.values(result))


def apply_type(v):
    # What filter arguments are allowed for this field type. Get them here
    allowed_arguments = allowed_filter_arguments(R.prop('fields', v), R.prop('graphene_type', v)) if \
        R.has('fields', v) else None

    # If we have allowed arguments make args a 2 element array. The first element is always the graphene type to
    # construct
    args = [R.prop('type', v)] + ([allowed_arguments] if allowed_arguments else [])
    t = R.prop_or(lambda typ: typ(), 'type_modifier', v)
    return t(*args)


def type_modify_fields(data_field_configs):
    """
        Converts json field configs based on if they have a type_modifier property. The type_modifier property
        allows us to make the type defined at graphene_type to be a Field or a List, depending on what we need
    :param data_field_configs: List of field configs that each might have type_modifier. Exmample:
    [
        # This is a field that points to a Django type User, so it resolves to Field(UserType)
        # with a resolver that handles Django models
        friend=dict(
            type=UserType,
            graphene_type=UserType,
            fields=merge_with_django_properties(UserType, dict(id=dict(create=REQUIRE))),
            type_modifier=lambda *type_and_args: Field(*type_and_args, resolver=model_resolver_for_dict_field(get_user_model()))
        ),
        # This is a field that points to a json dict modeled in graphene with ViewportDataType, so it
        resolves to Field(UserRegionDataType) with a resolver that handles a dict
        viewport=dict(
            type=ViewportDataType,
            graphene_type=ViewportDataType,
            fields=viewport_data_fields,
            type_modifier=lambda *type_and_args: Field(*type_and_args, resolver=resolver_for_dict_field),
        )
        # This is a field that points to a json list of dicts, each modeled in graphene with UserRegionDataType, so it
        resolves to List(UserRegionDataType) with a resolver that handles lists of dicts
        user_regions=dict(
            type=UserRegionDataType,
            graphene_type=UserRegionDataType,
            fields=user_region_data_fields,
            type_modifier=lambda typ: List(typ, resolver=resolver_for_dict_list)
        )
    ]
    :return: A list of Graphene Fields, created by mapping the field_configs. If the field_config has
    a type_modifier then it is called with field_config['type'] and its result is returned. Otherwise
    we simply call field_config['type']() to construct an instance of the type
    """
    return R.map_with_obj(
        # If we have a type_modifier function, pass the type to it, otherwise simply construct the type
        # This all translates to Graphene.Field|List(type, [fields that can be queried])
        lambda k, v: apply_type(v),
        data_field_configs
    )
