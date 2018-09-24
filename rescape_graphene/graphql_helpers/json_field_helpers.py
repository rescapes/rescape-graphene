from collections import namedtuple
from rescape_python_helpers import ramda as R
from inflection import underscore

###
# Helpers for json fields. json fields are not a Django model,
# rather a json blob that is the field data of the Region and Resource models
###


def resolve_selections(context):
    """
        Returns the query fields for the current context.
        Take the camelized keys and underscore (slugify) to get them back to python form
    :param {ResolveInfo} context: The graphene resolution context
    :return: {[String]} The field names to that are in the query
    """
    return R.map(lambda sel: underscore(sel.name.value), context.field_asts[0].selection_set.selections)


def pick_selections(selections, data):
    """
        Pick the selections from the current data
    :param {[Sting]} selections: The field names to that are in the query
    :param {dict} data: Data to pick from
    :return: {DataTuple} data with limited to selections
    """
    dct = R.pick(selections, data)
    return namedtuple('DataTuple', R.keys(dct))(*R.values(dct))


def resolver_for_dict_field(resource, context):
    """
        Resolver for the data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for querying json types
    :param resource:
    :param context:
    :return:
    """
    selections = resolve_selections(context)
    field_name = underscore(context.field_name)
    return pick_selections(selections, getattr(resource, field_name))


def resolver_for_dict_list(resource, context):
    """
        Resolver for the data field that is a list. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for querying json types
    :param resource:
    :param context:
    :return:
    """
    # Take the camelized keys and underscore (slugify) to get them back to python form
    selections = resolve_selections(context)
    field_name = underscore(context.field_name)
    return R.map(lambda data: pick_selections(selections, data), getattr(resource, field_name))


@R.curry
def model_resolver_for_dict_field(model_class, resource, context):
    """
        Resolver for the data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for querying json types
        TODO this naively assumes that the 'id' property is among the query selections and uses that
        to resolve the instance
    :param model_class:
    :param resource:
    :param context:
    :return:
    """
    # selections = resolve_selections(context)
    field_name = underscore(context.field_name)
    # Assume for simplicity that id is among selections
    return model_class.objects.get(id=R.prop('id', getattr(resource, field_name)))


@R.curry
def resolver(json_field_name, resource, context):
    """
        Resolver for the data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for querying json types
    :param {string} json_field_name: Name of the field on the resource that is the json field (such as 'data')
    :param {string} resource: The instance whose json field data is being resolved
    :param {ResolveInfo} context: Graphene context which contains the fields queried in field_asts
    :return: {DataTuple} Standard resolver return value
    """

    # Take the camelized keys and underscore (slugify) to get them back to python form
    selections = R.map(lambda sel: underscore(sel.name.value), context.field_asts[0].selection_set.selections)
    # Identify the keys that are actually in resource[json_field_name]
    all_selections = R.filter(
        lambda key: key in R.prop(json_field_name, resource), selections
    )
    # Pick out the values that we want
    dct = R.pick(all_selections, resource.data)

    # Return in the standard Graphene DataTuple
    return namedtuple('DataTuple', R.keys(dct))(*R.values(dct))


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
            type_modifier=lambda typ: Field(typ, resolver=model_resolver_for_dict_field(get_user_model()))
        ),
        # This is a field that points to a json dict modeled in graphene with ViewportDataType, so it
        resolves to Field(UserRegionDataType) with a resolver that handles a dict
        viewport=dict(
            type=ViewportDataType,
            graphene_type=ViewportDataType,
            fields=viewport_data_fields,
            type_modifier=lambda typ: Field(typ, resolver=resolver_for_dict_field),
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
        lambda k, v: R.prop_or(lambda typ: typ(), 'type_modifier', v)(R.prop('type', v)),
        data_field_configs)
