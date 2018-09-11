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
