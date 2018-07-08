from collections import namedtuple

from functional import ramda as R


def resolver(resource, context):
    """
        Resolver for the data field. This extracts the desired json fields from the context
        and creates a tuple of the field values. Graphene has no built in way for querying json types
    :param resource:
    :param context:
    :return:
    """
    selections = R.map(lambda sel: sel.name.value, context.field_asts[0].selection_set.selections)
    all_selections = R.filter(
        lambda key: key in resource.data, selections
    )
    dct = R.pick(all_selections, resource.data)
    return namedtuple('DataTuple', R.keys(dct))(*R.values(dct))
