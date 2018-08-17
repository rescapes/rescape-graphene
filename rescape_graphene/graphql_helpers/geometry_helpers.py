from json import dumps
from django.contrib.gis.geos import GeometryCollection, GEOSGeometry, Polygon
from rescape_graphene import ramda as R

def geometry_from_geojson(geojson):
    """
    Converts gejson to GEOSGeometry
    :param geojson:
    :return:
    """
    str = dumps(geojson)
    return GEOSGeometry(str)

def geometry_from_feature(feature):
    """
        Extracts the geometry property from the feature
    :param feature:
    :return:
    """
    return geometry_from_geojson(feature['geometry'])

def ewkt_from_feature(feature):
    return geometry_from_feature(feature).ewkt


# https://gis.stackexchange.com/questions/177254/create-a-geosgeometry-from-a-featurecollection-in-geodango
def geometrycollection_from_featurecollection(feature_collection):
    return GeometryCollection(tuple(R.map(geometry_from_feature, feature_collection['features'])))
