from inspect import isfunction
import itertools
from deepmerge import Merger
from pyramda import *
from json import dumps

@curry
def prop(key, dct_or_obj):
    """
        Implementation of prop (get_item) that also supports object attributes
    :param key:
    :param dct_or_obj:
    :return:
    """
    return (isinstance(dict, dct_or_obj) and has(key, dct_or_obj) and getitem(key, dct_or_obj) or
            (not isinstance(dict, dct_or_obj) and hasattr(dct_or_obj, key) and (getattr(key, dct_or_obj)))
            )

@curry
def filter_dict(f, dct):
    """
        Filter a dict
    :param f: lambda or function expecting a tuple (key, value)
    :param dict:
    :return: The filtered dict
    """
    return dict(filter(f, dct.items()))


def compact_dict(dct):
    """
        Compacts a dct by removing pairs with a None value
    :param dct:
    :return: The filtered dict
    """
    return dict(filter(lambda key_value: key_value[1], dct.items()))


@curry
def prop_or(default, key, dct_or_obj):
    """
        Ramda propOr implementation. This also resolves object attributes, so key
        can be a dict prop or an attribute of dct_or_obj
    :param default: Value if dct_or_obj doesn't have key_or_prop or the resolved value is null
    :param key:
    :param dct_or_obj:
    :return:
    """
    # Note that hasattr is a builtin and getattr is a ramda function, hence the different arg position
    return (isinstance(dict, dct_or_obj) and has(key, dct_or_obj) and dct_or_obj[key]) or \
           (not isinstance(dict, dct_or_obj) and hasattr(dct_or_obj, key) and (getattr(key, dct_or_obj))) or \
           default


@curry
def prop_eq(key, value, dct):
    """
        Ramda propEq implementation
    :param key:
    :param value:
    :param dct:
    :return: True if dct[key] is non null and equal to value
    """
    return prop_eq_or(False, key, value, dct)


@curry
def prop_eq_or(default, key, value, dct):
    """
        Ramda propEq plus propOr implementation
    :param default:
    :param key:
    :param value:
    :param dct:
    :return:
    """
    return dct[key] and dct[key] == value if key in dct else default


@curry
def prop_eq_or_in(key, value, dct):
    """
        Ramda propEq/propIn
    :param key:
    :param value:
    :param dct:
    :return:
    """
    return prop_eq_or_in_or(False, key, value, dct)


@curry
def prop_eq_or_in_or(default, key, value, dct):
    """
        Ramda propEq/propIn plus propOr
    :param default:
    :param key:
    :param value:
    :param dct:
    :return:
    """
    return has(key, dct) and \
           (dct[key] == value if key in dct else (
               dct[key] in value if isinstance((list, tuple), value) and not isinstance(str, value)
               else default
           ))


@curry
def default_to(default, value):
    """
    Ramda implementation of default_to
    :param default:
    :param value:
    :return:
    """
    return value or default


@curry
def item_path_or(default, keys, dict_or_obj):
    """
    Optional version of item_path with a default value. keys can be dict keys or object attributes, or a combination
    :param default:
    :param keys: List of keys or dot-separated string
    :param dict_or_obj: A dict or obj
    :return:
    """
    if not keys:
        raise ValueError("Expected at least one key, got {0}".format(keys))
    resolved_keys = keys.split('.') if isinstance(str, keys) else keys
    current_value = dict_or_obj
    for key in resolved_keys:
        current_value = prop_or(default, key, default_to({}, current_value))
    return current_value


def isint(value):
    try:
        int(value)
        return True
    except ValueError:
        return False


@curry
def item_str_path(keys, dct):
    """
        Given a string of path segments separated by ., splits them into an array. Int strings are converted
        to numbers to serve as an array index
    :param keys: e.g. 'foo.bar.1.goo'
    :param dct: e.g. dict(foo=dict(bar=[dict(goo='a'), dict(goo='b')])
    :return: The resolved value or an error. E.g. for above the result would be b
    """
    return item_path(map(lambda segment: int(segment) if isint(segment) else segment, keys.split('.')), dct)


@curry
def has(prop, object_or_dct):
    """
    Implementation of ramda has
    :param prop:
    :param object_or_dct:
    :return:
    """
    return prop in object_or_dct if isinstance(dict, object_or_dct) else hasattr(object_or_dct, prop)


@curry
def omit(omit_props, dct):
    """
    Implementation of omit
    :param omit_props:
    :param dct:
    :return:
    """
    return filter_dict(lambda key_value: key_value[0] not in omit_props, dct)


@curry
def omit_deep(omit_props, dct):
    """
    Implementation of omit that recurses. This tests the same keys at every level of dict and in lists
    :param omit_props:
    :param dct:
    :return:
    """

    omit_partial = omit_deep(omit_props)

    if isinstance(dict, dct):
        # Filter out keys and then recurse on each value that wasn't filtered out
        return map_dict(omit_partial, compact_dict(omit(omit_props, dct)))
    if isinstance((list, tuple), dct):
        # run omit_deep on each value
        return map(omit_partial, dct)
    # scalar
    return dct


@curry
def map_deep(map_props, dct):
    """
    Implementation of omit that recurses. This tests the same keys at every level of dict and in lists
    :param map_props: prop to unary function to map the value of a prop. The props are evaluated at every level
    of dct
    :param dct: Dict for deep processing
    :return: Modified dct with matching props mapped
    """

    map_deep_partial = map_deep(map_props)

    def test(key, value):
        return prop_or(always(value), key, map_props)(value)

    if isinstance(dict, dct):
        # Filter out keys and then recurse on each value that wasn't filtered out
        return map_dict(map_deep_partial, compact_dict(
            map_with_obj(
                # Lambda calls map_props[key](value) if map_props[key] exists, else returns value
                lambda key, value: test(key, value),
                dct
            )
        ))
    if isinstance((list, tuple), dct):
        # run map_deep on each value
        return map(map_deep_partial, dct)
    # scalar
    return dct


@curry
def join(strin, items):
    """
        Ramda implementation of join
    :param strin:
    :param items:
    :return:
    """
    return strin.join(map(lambda item: str(item), items))


def dump_json(json):
    """
        Returns pretty-printed json
    :param json
    :return:
    """
    return dumps(json, sort_keys=True, indent=4, separators=(',', ': '))


def head(lst):
    """
        Implementation of Ramda's head
    :param lst:
    :return:
    """
    return lst[0]


@curry
def map_with_obj(f, dct):
    """
        Implementation of Ramda's mapObjIndexed without the final argument.
        This returns the original key with the mapped value. Use map_key_values to modify the keys too
    :param f: Called with a key and value
    :param dct:
    :return {dict}: Keyed by the original key, valued by the mapped value
    """
    f_dict = {}
    for k, v in dct.items():
        f_dict[k] = f(k, v)
    return f_dict


def map_with_obj_to_values(f, dct):
    """
        Like map_with_obj but just returns the mapped values an array and disgards the keys
    :param f: Called wiht a key and value
    :param dct:
    :return {list}: values are the mapped value
    """
    return list(values(map_with_obj(f, dct)))

@curry
def map_key_values(f, dct):
    """
        Like map_with_obj but expects a key value pair returned from f and uses it to form a new dict
    :param f: Called with a key and value
    :param dct:
    :return:
    """
    return from_pairs(values(map_with_obj(f, dct)))


@curry
def map_keys(f, dct):
    """
        Calls f with each key of dct, possibly returning a modified key. Values are unchanged
    :param f: Called with each key and returns the same key or a modified key
    :param dct:
    :return: A dct with keys possibly modifed but values unchanged
    """
    f_dict = {}
    for k, v in dct.items():
        f_dict[f(k)] = v
    return f_dict


def merge_dicts(*dict_args):
    """
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    https://stackoverflow.com/questions/38987/how-to-merge-two-dictionaries-in-a-single-expression
    """
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result


def merge_deep(dct1, dct2):
    """
        Deep merge by this spec below
    :param dct1:
    :param dct2:
    :return:
    """
    my_merger = Merger(
        # pass in a list of tuples,with the
        # strategies you are looking to apply
        # to each type.
        [
            (list, ["append"]),
            (dict, ["merge"])
        ],
        # next, choose the fallback strategies,
        # applied to all other types:
        ["override"],
        # finally, choose the strategies in
        # the case where the types conflict:
        ["override"]
    )
    return my_merger.merge(dct1, dct2)


def merge_deep_all(dcts):
    """
        Merge deep all dicts using merge_deep
    :param dcts: 
    :return: 
    """""
    
    return reduce(
        lambda accum, dct: merge_deep(accum, dct),
        dict(),
        dcts
    )

@curry
def merge(dct1, dct2):
    """
        Ramda implmentation of merge
    :param dct1:
    :param dct2:
    :return:
    """
    return merge_dicts(dct1, dct2)


def compact(lst):
    """
        Ramda implmentation of compact. Removes Nones from lst (not 0, etc)
    :param lst:
    :return:
    """
    return filter(lambda x: x is not None, lst)


def from_pairs(pairs):
    """
        Implementation of ramda from_paris Converts a list of pairs or tuples of pairs to a dict
    :param pairs:
    :return:
    """
    return {k: v for k, v in pairs}


def flatten(lst):
    """
        Impemenation of ramda flatten
    :param lst:
    :return:
    """
    return list(itertools.chain.from_iterable(lst))


def concat(lst1, lst2):
    """
        Implmentation of ramda cancat
    :param lst1:
    :param lst2:
    :return:
    """
    return lst1 + lst2


def from_pairs_to_array_values(pairs):
    """
        Like from pairs but combines duplicate key values into arrays
    :param pairs:
    :return:
    """
    result = {}
    for pair in pairs:
        result[pair[0]] = concat(prop_or([], pair[0], result), [pair[1]])
    return result


def fullname(o):
    """
    https://stackoverflow.com/questions/2020014/get-fully-qualified-class-name-of-an-object-in-python
    Return the full name of a class
    :param o:
    :return:
    """
    return o.__module__ + "." + o.__class__.__name__


def length(lst):
    """
    Implementation of Ramda length
    :param lst:
    :return:
    """
    return len(lst)


def isalambda(v):
    """
    Detects if something is a lambda
    :param v:
    :return:
    """
    return isfunction(v) and v.__name__ == '<lambda>'


def map_prop_value_as_index(prp, lst):
    """
        Returns the given prop of each item in the list
    :param prp:
    :param lst:
    :return:
    """
    return from_pairs(map(lambda item: (prop(prp, item), item), lst))
