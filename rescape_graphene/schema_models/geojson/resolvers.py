import json


# https://raw.githubusercontent.com/flavors/django-graphql-geojson/master/graphql_geojson/resolver.py
def geometry_resolver(attname, default_value, root, info, **args):
    """
    This seems to resolve a geometry object into json
    :param attname:
    :param default_value:
    :param root:
    :param info:
    :param args:
    :return:
    """
    if default_value is not None:
        root = root or default_value
    return json.loads(root.geojson)[attname]


def geometry_collection_resolver(attname, default_value, root, info, **args):
    """
    This seems to resolve a geometry collection object into json
    :param attname:
    :param default_value:
    :param root:
    :param info:
    :param args:
    :return:
    """
    if default_value is not None:
        root = root or default_value
    return json.loads(root.geojson)[attname]