from inflection import camelize
from . import ramda as R


def handleGrapheneTypes(key, value):
    """
        Handle related Graphene types. This is recursive since it calls dump_grpahql_keys
    :param key:
    :param value:
    :return:
    """
    return '''%s {
        %s
    }''' % (camelize(key, False), dump_graphql_keys(R.prop('fields', value)))


def dump_graphql_keys(dct):
    """
        Convert a dict to a graphql input parameter keys in the form
        Also camelizes keys if the are slugs and handles complex types
        key1
        key2
        key3
        key4 {
            subkey1
            ...
        }
        ...
    :param dct: keyed by field 
    :return:
    """
    return R.join('\n', R.values(R.map_with_obj(
        dump_graphene_type,
        dct)
    ))

def dump_graphene_type(key, value):
    """
        Dumps the graphql query representation of a scalar Graphene type or a complex time, in the latter case
        recursing
    :param key:
    :param value:
    :return:
    """
    return handleGrapheneTypes(key, value) if R.isfunction(R.prop('type', value)) else camelize(key, False)

def dump_graphql_data_object(dct):
    """
        Convert a dict to a graphql input parameter key values in the form
        Also camelizes keys if the are slugs
        {key1: "string value1", key2: number2, ...}
    :param dct:
    :return:
    """
    return '{%s}' % R.join(
        ', ',
        R.map(
            lambda key_value: R.join(': ', [camelize(key_value[0], False), R.quote_unless_number(key_value[1])]),
            dct.items()
        )
    )

def full_stack():
    import traceback, sys
    exc = sys.exc_info()[0]
    stack = traceback.extract_stack()[:-1]  # last one would be full_stack()
    if not exc is None:  # i.e. if an exception is present
        del stack[-1]       # remove call of full_stack, the printed exception
                            # will contain the caught exception caller instead
    trc = 'Traceback (most recent call last):\n'
    stackstr = trc + ''.join(traceback.format_list(stack))
    if not exc is None:
         stackstr += '  ' + traceback.format_exc().lstrip(trc)
    return stackstr