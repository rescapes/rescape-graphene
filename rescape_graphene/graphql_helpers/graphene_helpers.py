from inflection import camelize
from graphene import ObjectType, Scalar
import inspect
from rescape_python_helpers import ramda as R
import numbers


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

    typ = R.prop('type', value)
    return handleGrapheneTypes(key, value) if \
        R.isfunction(typ) or (inspect.isclass(typ) and issubclass(typ, (ObjectType))) else \
        camelize(key, False)


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
            lambda key_value: R.join(': ', [camelize(key_value[0], False), quote(key_value[1])]),
            dct.items()
        )
    )


def full_stack():
    import traceback, sys
    exc = sys.exc_info()[0]
    stack = traceback.extract_stack()[:-1]  # last one would be full_stack()
    if not exc is None:  # i.e. if an exception is present
        del stack[-1]  # remove call of full_stack, the printed exception
        # will contain the caught exception caller instead
    trc = 'Traceback (most recent call last):\n'
    stackstr = trc + ''.join(traceback.format_list(stack))
    if not exc is None:
        stackstr += '  ' + traceback.format_exc().lstrip(trc)
    return stackstr


def quote(value, tab=-1):
    """
        Puts strings in quotes and but not numbers.
        If value is a dict it is represented as as
        key: value,
        key: value
        etc, where each value is recursively processed
    :param value:
    :return:
    """
    if isinstance(value, (numbers.Number)):
        return value
    elif isinstance(value, (dict)):
        return quote_dict(value, tab + 1)
    elif isinstance(value, (list, tuple)):
        return quote_list(value, tab + 1)
    else:
        return quote_str(value)


def quote_dict(dct, tab):
    """
        Recursively quotes dict values
    :param dct:
    :return:
    """
    t = '\t' * tab

    # The middle arg here is a newline if value is another dict, otherwise it's a space
    dct_sring = '\n{0}'.format(t).join(
        [
            '%s:%s%s' % (
                camelize(key, False),
                '\n{0}'.format(t) if isinstance(value, (dict)) else ' ',
                str(quote(value, tab))
            ) for key, value in dct.items()
        ])
    return '{0}{{\n{1}{2}\n{3}}}'.format(t, t, dct_sring, t)


def quote_list(lst, tab):
    """
        Recursively quotes list values
    :param lst
    :return:
    """
    t = '\t' * tab

    return '[\n{0}{1}\n]'.format(
        t,
        '\n{0}'.format(t).join(
            R.map(lambda item: str(quote(item, tab)), lst)
        )
    )


def quote_str(str):
    return '"{0}"'.format(str)
