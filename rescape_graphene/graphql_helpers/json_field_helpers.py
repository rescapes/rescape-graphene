import ast
from safedelete.models import SafeDeleteModel
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
    # Get the value, even if non truthy if the attribute exists
    data = R.prop(field_name, resource) if R.has(field_name, resource) else {}
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
    # Value defaults to None. Empty is not the same as None
    value = R.prop(field_name, resource) if R.has(field_name, resource) else None

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
    ) if value else value


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
        # Don't underscore the field_name. field_name points at a Django model, but the object holding field name
        # is by definition json, or we wouldn't be using this resolver
        field_name = context.field_name
        try:
            # resource is either a DataTuple or dict, not sure why
            id = R.prop_or(None, 'id', R.prop_or(dict(), field_name, resource) if\
                isinstance(resource, dict) else\
                getattr(resource, field_name))
        except Exception as e:
            raise e
        # If no instance id is assigned to this data, we can't resolve it
        if not id:
            return None

        # Now filter based on any query arguments beyond id. If it doesn't match we also return None
        found =  first(model_class.objects.filter(
            **dict(
                # These are Q expressions
                *flatten_query_kwargs(model_class, kwargs),
                id=id
            )
        ), None)

        def no_instance_error(_):
            raise Exception(f'For model {model_class.__name__} and id {id}, no instances were found, either deleted or not')

        # If we didn't find the instances search for delete instances if safedelete is implemented
        return found or (issubclass(model_class, SafeDeleteModel) and R.if_else(lambda q: q.count(), first, no_instance_error)(model_class.objects.all(force_visibility=True).filter(
            **dict(
                # These are Q expressions
                *flatten_query_kwargs(model_class, kwargs),
                id=id
            )
        )))


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

