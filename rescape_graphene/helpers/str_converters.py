#https://gist.githubusercontent.com/smmoosavi/033deffe834e6417ed6bb55188a05c88/raw/3393e415f9654f849a89d7e33cfcacaff0372cdd/str_converters.py
# TODO replace with inspect library
from graphene.utils.str_converters import to_snake_case, to_camel_case


def to_kebab_case(s):
    return to_snake_case(s).replace('_', '-')


def encode_key(k):
    return to_camel_case(k)


def dict_key_to_camel_case(d: dict):
    return dict((encode_key(k), v) for k, v in d.items())