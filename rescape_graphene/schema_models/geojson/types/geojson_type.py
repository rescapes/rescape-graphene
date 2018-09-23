import inspect
from collections import OrderedDict

import graphene
from graphene.types import resolver
from graphene.types.generic import GenericScalar
from graphene_django.types import DjangoObjectType, DjangoObjectTypeOptions
from rescape_python_helpers import ramda as R

__all__ = ['GeoJsonType']


class OrderedFields(OrderedDict):

    def update(self, other=None, **kwargs):
        if other is not None:
            global_id_field = other.pop('id', None)

            if global_id_field is not None:
                self['id'] = global_id_field

            properties_type = self['properties']._type
            Properties = type(properties_type.__name__, (
                properties_type,), other)

            self['properties'] = graphene.Field(Properties)
        else:
            super().update(**kwargs)


class GeoJSONTypeOptions(DjangoObjectTypeOptions):
    geojson_field = None

    def __setattr__(self, name, value):
        if name == 'xfields':
            geo_fields = R.filter_dict(
                R.compose(
                    lambda type: R.contains(type, ['GeometryType', 'GeometryCollectionType']),
                    lambda key_field: R.item_path_or(False, ['_type', '_of_type'], key_field[1]),
                ),
                value
            )

            primary_key = self.model._meta.pk.name
            primary_key_field = value[primary_key]
            properties = self.get_properties(value)

            fields = [
                ('type', graphene.Field(graphene.String)),
                (self.geojson_field, geometry_field),
                ('properties', graphene.Field(properties)),
            ]

            if primary_key_field is not None:
                fields.insert(1, (primary_key, primary_key_field))

            value = OrderedFields(fields)

        super().__setattr__(name, value)

    def get_properties(self, value):
        methods = inspect.getmembers(
            self.class_type(),
            predicate=inspect.ismethod)

        for method_name, method in methods:
            if method_name.startswith('resolve'):
                value[method_name] = method.__func__

        class_name = '{}Properties'.format(self.model.__name__)
        return type(class_name, (graphene.ObjectType,), value)


class GeoJsonType(DjangoObjectType):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, name=None, _meta=None,
                                    geojson_field=None, **options):
        if _meta is None:
            _meta = GeoJSONTypeOptions(cls)

        super().__init_subclass_with_meta__(name=name, _meta=_meta, **options)
