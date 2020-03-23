import inspect
import json
import logging
import sys
from decimal import Decimal

from deepmerge import Merger
from graphql.language.printer import print_ast
import graphene
from django.contrib.gis.db.models import GeometryField, OneToOneField, ManyToManyField, ForeignKey, \
    GeometryCollectionField
from graphql import parse

from rescape_python_helpers import ramda as R
from django.contrib.postgres.fields import JSONField
from django.db.models import AutoField, CharField, BooleanField, BigAutoField, DecimalField, \
    DateTimeField, DateField, BinaryField, TimeField, FloatField, EmailField, UUIDField, TextField, IntegerField, \
    BigIntegerField, NullBooleanField, Q
from graphene import Scalar, InputObjectType, ObjectType
from graphql.language import ast
from inflection import camelize
from rescape_python_helpers.functional.ramda import to_dict_deep, flatten_dct, to_pairs, flatten_dct_until

from .graphene_helpers import dump_graphql_keys, dump_graphql_data_object
from .memoize import memoize

logger = logging.getLogger('rescape_graphene')
from django.conf import settings

DENY = 'deny'
# Indicates a CRUD operation is required to use this field
REQUIRE = 'require'
# Indicates a CRUD operation is required to use this field and it is used as a match on uniqueness
# with 0 more other fields.
# For instance, username and email are both marked update=[REQUIRE, UNIQUE], they are both used to check uniqueness
# when updating, using:
# User.objects.update_or_create(defaults=**kwargs, username='foo', email='foo@foo.foo')
# Then it would take an admin mutation to update the username and/or email, such as:
# User.objects.update_or_create(defaults={username: 'boo', email='boo@boo.boo'}, id=1234231)
# Similarly data_points fields like blockname can't be updated except by an admin mutation
# All fields that are REQUIRE_UNIQUE should probably always match a database constraint for those fields
UNIQUE = 'unique'
# Don't display the value for reads
IGNORE = 'ignore'
# UNIQUE primary key
PRIMARY = 'primary'

# Indicates a CRUD operation is can optionally use this field
ALLOW = 'allow'

CREATE = 'create'
READ = 'read'
UPDATE = 'update'
DELETE = 'delete'

# From django-filters. Whenever graphene supports filtering without Relay we can get rid of this here
# Educated guesss about what types for each to support. Django/Postgres might support fewer or more of these
# combinations than I'm aware of
# Skip if testing. These take forever
FILTER_FIELDS = R.compose(
    # Create not versions of each. This is a pseudo syntax not supported by Django. Django uses exclude() or ~Q(expr).
    # We can't create an equivalent here with keys, so we use _not and convert it to ~Q(expr) later
    lambda pairs: R.from_pairs(pairs),
    lambda pairs: R.chain(lambda key_value: [list(key_value), [f'{key_value[0]}_not', key_value[1]]], pairs),
    lambda dct: R.to_pairs(dct),

    R.if_else(
        lambda settings: settings.TESTING,
        # Minimum set for debugging speed
        lambda _: {
            'contains': dict(),
            'icontains': dict(),
            'in': dict(type_modifier=lambda typ: graphene.List(typ))
        },
        lambda _: {
            'year': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            'month': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            'day': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            'week_day': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            'hour': dict(allowed_types=[graphene.DateTime]),
            'minute': dict(allowed_types=[graphene.DateTime]),
            'second': dict(allowed_types=[graphene.DateTime]),

            # standard lookups
            'exact': dict(),  # this is the default, but keep so we can do negative queries, i.e. exact__not
            'iexact': dict(),
            'contains': dict(),
            'icontains': dict(),
            'in': dict(type_modifier=lambda typ: graphene.List(typ)),
            'gt': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'gte': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'lt': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'lte': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'startswith': dict(allowed_types=[graphene.String]),
            'istartswith': dict(allowed_types=[graphene.String]),
            'endswith': dict(allowed_types=[graphene.String]),
            'iendswith': dict(allowed_types=[graphene.String]),
            # Range expects a 2 item tuple, so give it a list
            'range': dict(type_modifier=lambda typ: graphene.List(typ)),
            'isnull': dict(),
            'regex': dict(allowed_types=[graphene.String]),
            'iregex': dict(allowed_types=[graphene.String]),
            'search': dict(allowed_types=[graphene.String]),

            # postgres lookups
            'contained_by': dict(),
            # Date overlap
            'overlap': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            # These are probably for json types so maybe useful
            'has_key': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            'has_keys': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            'has_any_keys': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            # groups of 3 characters for similarity recognition
            'trigram_similar': dict(allowed_types=[graphene.String])
        }
    )
)(settings)


# https://github.com/graphql-python/graphene-django/issues/124


class ErrorMiddleware(object):
    def on_error(self, error):
        err = sys.exc_info()
        logging.error(error)
        return err[1]

    def resolve(self, next, root, args, context, info):
        return next(root, args, context, info).catch(self.on_error)


# https://github.com/graphql-python/graphene-django/issues/91
class Decimal(Scalar):
    """
    The `Decimal` scalar type represents a python Decimal.
    """

    @staticmethod
    def serialize(dec):
        assert isinstance(dec, Decimal), (
            'Received not compatible Decimal "{}"'.format(repr(dec))
        )
        return str(dec)

    @staticmethod
    def parse_value(value):
        return Decimal(value)

    @classmethod
    def parse_literal(cls, node):
        if isinstance(node, ast.StringValue):
            return cls.parse_value(node.value)


class DataPointRelatedCreateInputType(InputObjectType):
    id = graphene.String(required=True)


@memoize(map_args=lambda args: [
    # Only use graphene_type here. type is a function and can't be serialized
    args[0]['graphene_type'],
    args[1],
    # TODO We use the parent_type_class to make each type unique. I don't know why graphene won't let us reuse
    # input types within the schema. It seems like a UserInputType should be reusable whether it's the User
    # of a Region or the user of a Group.
    args[2] if R.isinstance((list, tuple), args[2]) else [args[2]]
])
def input_type_class(field_config, crud, parent_type_classes=[]):
    """
    An InputObjectType subclass for use as nested query argument types and mutation argument types
    The subclass is dynamically created based on the field_dict_value['graphene_type'] and the crud type.
    The fields are based on field_dicta_values['fields'] and the underlying Django model of the graphene_type,
    as well as the rules for the crud type spceified in field_dict_vale.
    :param field_config:
    :param crud: CREATE, UPDATE, or READ
    :param parent_type_classes: String or String array of parent graphene type classes. Unfortunately, Graphene doesn't
    let us reuse input types around the schema, even if they are identical, so we must give them unique names
    based on the parent ancestry
    :return: An InputObjectType subclass
    """
    # Get the Graphene type. This comes from graphene_type if the class containing the field is a Django Model,
    # It defaults to type, which is what we expect if we didn't have to use a graphene_type to distinguish
    # from the underlying Django type
    graphene_class = field_config['graphene_type'] or field_config['type']
    # Make it an array if not
    modified_parent_type_classes = parent_type_classes if R.isinstance((list, tuple), parent_type_classes) else [
        parent_type_classes]

    # Gather the field_configs for the type we are creating
    input_type_field_configs = merge_with_django_properties(
        graphene_class,
        R.compose(
            # Remove the update and create constraints,
            # which would normally disallow using id in create and require using it in update
            # We're not creating this model instance, we're just referencing it
            # TODO We could add some other field flag that specifies whether the container needs to reference it or not
            # such as referenced_in_create = REQUIRE, if the container has to have a reference when the
            # container is created
            R.map_with_obj(lambda key, value: R.omit(['create', 'update'], value)),
            # Only take the id
            R.pick(['id'])
        )(field_config['fields']) if crud in [CREATE, UPDATE] else field_config['fields']
    ) if django_model_of_graphene_type(graphene_class) else field_config['fields']

    input_fields = input_type_fields(
        input_type_field_configs,
        crud,
        # Keep our naming unique by appending parent classes, ordered newest to oldest
        R.concat([graphene_class], modified_parent_type_classes)
    )

    # These fields allow us to filter on InputTypes when we use them as query arguments
    # This doesn't apply to Update and Create input types, since we never filter during those operations
    filter_fields = allowed_filter_arguments(input_type_field_configs, graphene_class) if R.equals(READ, crud) else {}

    return type(
        '%s%sRelated%sInputType' % (
            graphene_class.__name__,
            # Use the ancestry for uniqueness of name
            R.join('of', R.concat([''], modified_parent_type_classes)),
            camelize(crud, True)),
        (InputObjectType,),
        # RECURSION
        # Create Graphene types for the InputType based on the field_dict_value.fields
        # This will typically just be an id field to reference an existing object.
        # If the graphene type is based on a Django model and this is and update/create crud construction,
        # we want to limit the fields to the id. We never want a mutation to be able to modify a Django object
        # referenced in json data. We only want the mutation to be allowed to specify the id to reference an existing
        # Django object.
        #
        # Otherwise field_dict_value['fields'] are independent of a Django model and each have their own type property
        R.merge(input_fields, filter_fields)
    )


def related_input_field(field_dict_value, parent_type_classes, *args, **kwargs):
    """
        Make an InputType subclass based on a Graphene type
    :param field_dict_value: The field dict value for a graphene field. This must exist and have a graphene_type
    that matches the Django model and it must have a fields property that is a field_dict for that relation
    Example. If The relation is data_point, the model is DataPoint and the graphene_type is DataPointType
    and fields could be dict(
        id=dict(create=REQUIRE, update=DENY),
    )
    meaning that only the id can be specified for the DataPoint relationship to resolve an existing DataPoint
    :param parent_type_classes: String or String array of parent graphene type classes. Unfortunately, Graphene doesn't
    :param args:
    :param kwargs:
    :return: A lambda for A Graphene Field to create the InputType subclass. The lambda needs a crud type
    """
    return lambda crud: graphene.InputField(input_type_class(field_dict_value, crud, parent_type_classes), *args,
                                            **kwargs)


@R.curry
def related_input_field_for_crud_type(field_dict_value, parent_type_classes, crud):
    """
        Resolved the foreign key input field for the given crud type
    :param field_dict_value: The corresponding field dict value. This must exist and have a graphene_type
    that matches the Django model and it must have a fields property that is a field_dict for that relation
    :param crud: CREATE or UPDATE
    :param parent_type_classes: String or String array of parent graphene type classes. Unfortunately, Graphene doesn't
    :return:
    """
    return lambda *args, **kwargs: related_input_field(field_dict_value, parent_type_classes, *args, **kwargs)(crud)


def django_to_graphene_type(field, field_dict_value, parent_type_classes):
    """
        Resolve the actual Graphene Field type. I can't find a good way to do this automatically.
    :param field: The Django Field
    :param field_dict_value: The corresponding field_dict value if it exists. This required for related fields.
    For related fields it must contain field_dict_value.graphene_type, which is the graphene type for that field
    as well as a fields property which is the fields_dict for that field
    :param parent_type_classes: String array of parent graphene types for dynamic class naming. This is needed
    because Graphene doesn't allow duplicate class names (even if they represent the same class type relationship
    in different parts of the schema)
    :return: The resolved or generated Graphene type
    """
    if R.prop_or(False, 'graphene_type', field_dict_value or {}):
        # This is detected as a lambda and called first with crud to establish what fields are needed in the
        # dynamic InputField subclass. Then another lambda is returned expecting args and kwargs, just like
        # the other graphene types above
        return related_input_field_for_crud_type(field_dict_value, parent_type_classes)

    from rescape_graphene.schema_models.geojson.types import GrapheneFeatureCollection
    types = {
        AutoField: graphene.Int,
        IntegerField: graphene.Int,
        BigAutoField: graphene.Int,
        CharField: graphene.String,
        BigIntegerField: graphene.Int,
        BinaryField: graphene.Int,
        BooleanField: graphene.Boolean,
        NullBooleanField: graphene.Boolean,
        DateField: graphene.Date,
        DateTimeField: graphene.DateTime,
        TimeField: graphene.Time,
        DecimalField: Decimal,
        FloatField: graphene.Float,
        EmailField: graphene.String,
        UUIDField: graphene.UUID,
        TextField: graphene.String,
        JSONField: graphene.JSONString,
        # I'm not sure if this is works still. We are storing geojson as a json blob, not a GeosGeometryCollection.
        # If we do use a GeosGeometryCollection I'm not sure if this mapping works
        GeometryCollectionField: GrapheneFeatureCollection
    }
    cls = field.__class__
    match = R.prop_or(None, cls, types)
    # Find the type that matches. If not match we assume that the class only has one base class,
    # such as GeometryField subclasses
    while not match:
        cls = cls.__bases__[0]
        match = R.prop_or(None, cls, types)
    return match


def process_field(field_to_unique_field_groups, field, field_dict_value, parent_type_classes):
    """
        Process Django field for important properties like type and uniqueness
    :param field_to_unique_field_groups:
    :param field: The Django Field
    :param field_dict_value: The matching field_dict_value if it exists. This is only used for related fields
    That need fields for making an InputType subclass. When used the field_dict_value
    must have a graphene_type property that is a graphene type and fields property that is a field_dict for that relation
    or a type property that resolves to a graphene type whose fields are the same no matter the crud operation
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :return: A dict with the unique property and anything else we need
    """
    unique = R.compact([
        PRIMARY if field.primary_key else None,
        UNIQUE if field.unique else None,
        R.prop_or(None, field.attname, field_to_unique_field_groups)
    ])
    # Normally the field_dict_value will delegate the type to the underlying Django model
    # In cases where we need an explicit type, because the field represents something modeled outside django,
    # like json blobs, we specify the type property on field_dict_value.graphene_type, which takes precedence
    return dict(
        # Resolves to a lambda that expects a crud value and then returns a lambda that expects args
        type=django_to_graphene_type(field, field_dict_value, parent_type_classes),
        # This tells that the relation is based on a Django class
        django_type=R.item_path_or(None, ['graphene_type', '_meta', 'model'], field_dict_value),
        unique=unique
    )


def parse_django_class(model, field_dict, parent_type_classes=[]):
    """
        Parse the fields of a Django model to merge important properties with
        a graphene field_dict
    :param model: The Django model
    :param field_dict: The field_dict, which is only needed to supplies the fields to related fields. Related
    fields are made into InputType subclasses for mutations, so field_dict[field]['fields'] supplies the fields
    for the InputType. The fields are in the same format as field_dict
    :return:
    """
    # This mess just maps each attr to all "unique together" tuples it's in
    field_to_unique_field_groups = R.from_pairs_to_array_values(
        R.flatten(
            R.map(
                lambda uniq_field_group:
                R.map(
                    lambda attrname: [attrname, R.join(',', uniq_field_group)],
                    uniq_field_group
                ),
                model._meta.unique_together
            )
        )
    )
    return R.from_pairs(R.map(
        lambda field: [
            # Key by file.name
            field.name,
            # Process each field
            process_field(field_to_unique_field_groups, field, R.prop(field.name, field_dict), parent_type_classes)
        ],
        # Only accept model fields that are defined in field_dict
        R.filter(
            lambda field: field.name in field_dict,
            R.concat(model._meta.fields, model._meta.many_to_many)
        )
    ))


def django_model_of_graphene_type(graphene_type):
    """
        Returns the Django model underlying the Graphene type, if any
    :param graphene_type: Graphene ObjectType subclass
    :return: The Django model type or None
    """
    return R.item_str_path_or(None, '_meta.model', graphene_type)


def merge_with_django_properties(graphene_type, field_dict):
    """
        Merges a field_dict with Graphene fields and other options with relevant Django model properties.
        Only Django properties in the field_dict are merged
        This results in a dict keyed by field that can be used for generating graphql queries and resolvers
    :param graphene_type:
    :param field_dict:
    :return:
    """
    return R.merge_deep(
        field_dict,
        R.pick(
            R.keys(field_dict),
            parse_django_class(django_model_of_graphene_type(graphene_type), field_dict, graphene_type))
    )


@R.curry
def resolve_type(graphene_type, field_config):
    # If the type is a scalar, just instantiate
    # Otherwise created a related field InputType subclass. In order to query a nested object, it has to
    # be an input field. Example: If A User has a Group, we can query for users named 'Peter' who are admins:
    # graphql: users: (name: "Peter", group: {role: "admin"})
    # https://github.com/graphql-python/graphene/issues/431
    return R.prop('type', field_config)() if \
        inspect.isclass(R.prop('type', field_config)) and issubclass(R.prop('type', field_config), Scalar) else \
        input_type_class(field_config, READ, graphene_type)()


def allowed_read_fields(fields_dict, graphene_type):
    """
        Returns fields that can be returned.
        allowed_filter_arguments below is similar but for arguments
    :param fields_dict: The fields_dict for the Django model
    :param graphen_type: Type used for emboded input class naming
    :return: dict of field keys and there graphene type, either a primitive or input type
    """
    return R.compose(
        R.map_dict(resolve_type(graphene_type)),
        R.filter_dict(
            lambda key_value:
            # Don't allow DENYed READ fields to be used for querying
            R.and_func(
                True,
                R.not_func(R.prop_eq_or_in(READ, DENY, key_value[1]))
            )
        )
    )(fields_dict)


def allowed_filter_pairs(field_name, graphene_type):
    """
        Creates pairs of filter_field, graphene_type such as [id_contains, Int(), id_in, List(Int())] for
        filter fields that are allowed for the field_name's graphene_type
    :param field_name: Field being given filters
    :param graphene_type: Graphene type of the field
    :return: List of pairs
    """
    return R.map_with_obj_to_values(
        # Make all the filter pairs for each key id: id_contains, id: id_in, etc
        lambda filter_str, config: [
            '%s_%s' % (field_name, filter_str),
            # If a type_modifier is needed for the filter type, such as a List constructor call it
            # with the field's type as an argument
            (config['type_modifier'] if R.has('type_modifier', config) else lambda t: t())(graphene_type)
        ],
        # Only allow filters compliant with the type of pair[1]
        R.filter_dict(
            lambda keyvalue: not R.has('allowed_types', keyvalue[1]) or R.any_satisfy(
                lambda typ: issubclass(graphene_type, typ), keyvalue[1]['allowed_types']
            ),
            FILTER_FIELDS
        )
    )


def make_filters(pair):
    """
        Add the needed filters to the standard 'eq' value
        This compensates for django-filter not being implemented to work in graphene without Relay
    :param pair:
    :return:
    """
    return R.from_pairs(
        R.concat(
            [pair],
            allowed_filter_pairs(pair[0], pair[1].__class__)
        )
    )


def add_filters(argument_dict):
    """
        Adds filter arguments to 'eq' arguments.
    :param argument_dict:
    :return: dict of the 'eq' arguments and the filter args e.g. {id: Int(), id_contains: List(Int), ...}
    """
    return R.compose(
        R.merge_all,
        R.map(make_filters),
        R.to_pairs
    )(argument_dict)


def allowed_filter_arguments(fields_dict, graphene_type):
    """
        Like allowed_query_and_read_arguments but only used for arguments and adds filter variables like id_contains.
        Note that django needs __ so these are converted for resolvers. The graphql interface converts them to
        camel case
    :param fields_dict: The fields_dict for the Django model
    :param graphen_type: Type used for embedded input class naming
    :return: dict of field keys and there graphene type, either a primitive or input type
    """
    return R.compose(
        lambda argument_dict: add_filters(argument_dict),
        R.map_dict(resolve_type(graphene_type)),
        R.filter_dict(
            lambda key_value:
            # Don't allow DENYed READ fields to be used for querying
            R.and_func(
                True,
                R.not_func(R.prop_eq_or_in(READ, DENY, key_value[1]))
            )
        )
    )(fields_dict)


def process_filter_kwargs(model, kwargs):
    """
        Converts filter names for resolvers. They come in with an _ but need __ to match django's query language
    :param model: The django model--used to flatten the objects properly
    :param kwargs:
    :return: list of Q expressions representing each kwarg
    """
    return R.compose(
        lambda kwrgs: flatten_query_kwargs(model, kwrgs),

        # Convert filters from _ to __
        R.map_keys_deep(
            lambda k, v: k.replace('_', '__')
            if R.any_satisfy(lambda string: '_%s' % string in str(k), R.keys(FILTER_FIELDS))
            else k
        )
    )(kwargs)


def guess_update_or_create(fields_dict):
    """
    Determines if the query is intended to be a create or update
    :param fields:
    :return:
    """
    if R.has('id', fields_dict):
        return UPDATE
    # Guessing create. This might still be an update if unique fields are used
    return CREATE


def instantiate_graphene_type(field_config, parent_type_classes, crud):
    """
        Instantiates the Graphene type at value.type. Most of the time the type is a primitive and
        doesn't need to be mapped to an input type. If the type is an ObjectType, we need to dynamically
        construct an InputObjectType
    :param field_config: Dict containing type and possible crud fields like value['create'] and value['update']
    These optional values indicate if a field is required
    :param crud:
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :return:
    """

    # Always favor the graphene_type that we specify in the field config. If it's not present use the django type
    graphene_type = R.prop_or(R.prop_or(None, 'type', field_config), 'graphene_type', field_config)

    if not graphene_type:
        raise Exception("No graphene_type nor type parameter found on the field value."
                        " This usually means that a field was defined in the"
                        " field_dict that has no corresponding django field. To define a field with no corresponding"
                        " Django field, you must give the field a type parameter that is set to a GraphneType subclass")
    graphene_type_modifier = R.prop_or(None, 'type_modifier', field_config)
    if inspect.isclass(graphene_type) and issubclass(graphene_type, (ObjectType)):
        # ObjectTypes must be converted to a dynamic InputTypeVersion
        fields = R.prop('fields', field_config)
        resolved_graphene_type = input_type_class(dict(graphene_type=graphene_type, fields=fields), crud,
                                                  parent_type_classes)
    elif R.isfunction(graphene_type):
        # If a lambda is returned we have an InputType subclass that needs to know the crud type
        resolved_graphene_type = graphene_type(crud)
    else:
        # Otherwise we have a simple type
        resolved_graphene_type = graphene_type

    # Instantiate using the type_modifier function if we need to wrap this in a List and/or give it a resolver,
    # Otherwise instantiate and pass the required flag
    return graphene_type_modifier(resolved_graphene_type) if \
        graphene_type_modifier else \
        resolved_graphene_type(
            # Add required depending on whether this is an insert or update
            # This means if a user omits these fields an error will occur
            required=R.prop_eq_or_in_or(False, crud, REQUIRE, field_config)
        )


def input_type_fields(fields_dict, crud, parent_type_classes=[]):
    """
    :param fields_dict: The fields_dict for the Django model or json data
    :param crud: INSERT, UPDATE, or DELETE. If None the type is guessed
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :return:
    """
    crud = crud or guess_update_or_create(fields_dict)
    return R.map_dict(
        lambda field_config: instantiate_graphene_type(field_config, parent_type_classes, crud),
        # Filter out values that are deny
        # This means that if the user tries to pass these fields to graphql an error will occur
        R.filter_dict(
            lambda key_value: R.not_func(R.prop_eq_or(False, crud, DENY, key_value[1])),
            fields_dict
        )
    )


def key_value_based_on_unique_or_foreign(key_to_modified_key_and_value, fields_dict, key):
    """
        Returns either a simple dict(key=value) for keys that must have unique values (e.g. id, key, OneToOne rel)
        Returns dict(default=dict(key=value)) for keys that need not have unique values
    :param {String} key: The key to test
    :return {dict}:
    """
    modified_key_value = key_to_modified_key_and_value[key]
    # non-defaults are for checking uniqueness and then using for update/insert
    # defaults are for updating/inserting
    # this matches Django Query's update_or_create
    # We don't bother with unique_together--it should be handled by the model's mutation handler
    return modified_key_value if \
        R.contains('unique', R.item_path_or([None], [key, 'unique'], fields_dict)) else \
        dict(defaults=modified_key_value)


def input_type_parameters_for_update_or_create(fields_dict, field_name_to_value):
    """
        Returns the input_type fields for a mutation class in the form
        {
            defaults: {...}
            unique_fields
        }
        where the default fields are any fields that can be updated or inserted if the object is new
        and unique_fields are any fields are used for uniqueness check by Django's update_or_create.
        if nothing matches all unique_fields then update_or_create combines all fields and does an insert
    :param fields_dict: The fields_dict for the Django model
    :param field_name_to_value: field name and value dict
    :return:
    """

    # Convert foreign key dicts to their id, since Django expects the foreign key as an saved instance or id
    _related_object_id_if_django_type = related_object_id_if_django_type(fields_dict)
    key_to_modified_key_and_value = R.map_with_obj(
        _related_object_id_if_django_type,
        R.omit(['id'], field_name_to_value)
    )
    if R.has('id', field_name_to_value):
        # If we are doing an update with an id then the only value that doesn't go in defaults is id
        return dict(
            id=R.getitem('id', field_name_to_value),
            defaults=R.merge_all(R.values(key_to_modified_key_and_value))
        )
    else:
        # Otherwise if we are creating or might be updating because we match a unique group of fields
        # TODO we really shouldn't allow updating without an id.
        # Matching a unique group of fields without an id should be an error
        # Forms a dict(
        #   unique_key1=value, unique_key2=value, ...,
        #   defaults=(non_unique_key1=value, non_unique_key2=value, ...)
        # )
        return R.merge_deep_all(R.map_with_obj_to_values(
            lambda key, value: key_value_based_on_unique_or_foreign(
                key_to_modified_key_and_value,
                fields_dict,
                key
            ),
            field_name_to_value
        ))


@R.curry
def related_object_id_if_django_type(fields_dict, key, value):
    """
        Determines if the key represents a property that is a djnago type and returns the id of the value if so
        Convert foreign key dicts to their id, since Django expects the foreign key as an saved instance or id
        Example region = {id: 5} becomes region_id = 5
    :param fields_dict: Contains keys that might have a value with a 'django_type' property
    :param key:  They current key
    :param value:  They current value
    :return:  {{key}_id, value.id} if the key represents a django type
    """
    try:
        return {f'{key}_id': R.prop('id', value)} \
            if R.prop_or(False, 'django_type', fields_dict[key]) \
            else {key: value}

    except Exception as e:
        logging.error(
            f'Problem with related types for key {key}, value {json.dumps(value)}'
        )
        raise e


@R.curry
def graphql_query(graphene_type, fields, query_name):
    """
        Creates a query based on the name and given fields
    :param graphene_type: The graphene type. This is used to know the type of the input fields
    :param fields: The fields of the type. This is a dict key by field name and valued by a dict. See sample_schema.py
    for examples
    :param query_name:
    :returns A lambda that expects a Graphene client and **kwargs that contain kwargs for the client.execute call.
    The only key allowed is variables, which contains param key values. Example: variables={'user': 'Peter'}
    This results in query whatever(id: String!) { query_name(id: id) ... }
    """
    field_type_lookup = allowed_filter_arguments(fields, graphene_type)

    def form_query(client, field_overrides={}, **kwargs):
        """
        # Make definitions in the form id: String!, foo: Int!, etc
        :param client:
        :param field_overrides: Override the fields argument with limited fields in the same format as fields above
        :return:
        """

        # Map the field_type_lookup to the right graphene type, either a primitive like 'String' or a complex
        # read input type like 'FeatureCollectionDataTypeofFooTypeRelatedReadInputType'
        variable_definitions = R.map_key_values(
            lambda k, v: [camelize(k, False), field_type_lookup[k]._meta.name],
            kwargs['variables']
        ) if R.has('variables', kwargs) else {}

        # Form the key values, camelizing the keys to match what graphql expects
        formatted_definitions = R.join(
            ', ',
            R.values(
                R.map_with_obj(
                    lambda key, value: f'${camelize(key, False)}: {value}!',
                    variable_definitions
                )
            )
        )
        query = print_ast(parse('''query someMadeUpString%s { 
                %s%s {
                    %s
                }
            }''' % (
            '(%s)' % formatted_definitions if formatted_definitions else '',
            query_name,
            '(%s)' %
            R.join(
                ', ',
                # Put the variable definitions in (x: $x, y: $y, etc) if variable definitions exist
                R.map(
                    lambda key: '%s: $%s' % (key, key),
                    R.keys(variable_definitions))
            ) if variable_definitions else '',
            dump_graphql_keys(field_overrides or fields)
        )))

        # Update the variable names to have camel case instead of pythonic slugs
        camelized_kwargs = R.fake_lens_path_set(
            ['variables'],
            R.map_keys(
                lambda key: camelize(key, False),
                R.prop_or({}, 'variables', kwargs)
            ),
            kwargs
        )
        logger.debug(f'Query: {query}\nKwargs: {R.dump_json(camelized_kwargs)}')
        return client.execute(
            query,
            **camelized_kwargs
        )

    return form_query


def grapqhl_authorization_mutation(client, values):
    """
    Generates an authorization mutation
    TODO this won't work unless we have a client with a request that can interact with JWT
    :param client: Apollo client
    :param values: username and password key values
    :return:
    """
    mutation = print_ast(parse(
        '''mutation
        TokenAuth($username: String!, $password: String!) {
            tokenAuth(username: $username, password: $password) {
            token
        }
        }'''))
    client.execute(mutation, variables=values)


@R.curry
def graphql_update_or_create(mutation_config, fields, client, values):
    """
        Update or create by creating a graphql mutation
    :param mutation_config: A config in the form
        class_name='User'|'DataPoint'|etc
        crud={
            CREATE: 'create*',
            UPDATE: 'update*'
        },
        resolve=guess_update_or_create
        where * is the name of the model, such as User. The resolve function returns CREATE or UPDATE
        based on what is in values. For instance, it guesses that passing an id means the user wants to update
    :param fields: A dict of field names field definitions, such as that in user_schema. The keys can be
    Django/python style slugged or graphql camel case. They will be converted to graphql style
    :param client: Graphene client
    :param values: key values of what to update. keys can be slugs or camel case. They will be converted to camel
    :return:
    """

    # 'update' or 'create'. The default way of guessing is looking for presence of the 'id' property
    # and guessing 'create' if id is missing
    update_or_create = guess_update_or_create(values)
    # We name the mutation classNameMutation and the parameter classNameData
    # where className is the camel-case version of the given class name in mutation_config.class_name
    name = camelize(R.prop('class_name', mutation_config), False)
    mutation = print_ast(parse(''' 
        mutation %sMutation {
            %s(%sData: %s) {
                %s {
                    %s 
                }
            }
        }''' % (
        # The arbitrary(?) name for the mutation e.g. 'foo' makes 'fooMutation'. Consistant naming might be important
        # for caching
        name,
        # Actual schema function which matches something in the schema
        # This will be createClass or updateClass where class is the class name e.g. createFoo or updateFoo
        # Keep in mind that in python in the schema it will be defined create_foo or update_foo
        R.item_path(['crud', update_or_create], mutation_config),
        # The name of the InputDataType that is defined for this function, e.g. FooInputDataType
        name,
        # Key values for what is being created or updated. This is dumped recursively and matches the structure
        # of the InputDataType subclass
        dump_graphql_data_object(values),
        # Again the name, this time used for the structure of the return query e.g. foo { ...return value ...}
        name,
        # The return query dump, which are all the fields available that aren't marked read=IGNORE.
        # One catch is we need to add the id,
        # which isn't part of field_configs because Graphene handles ids automatically
        dump_graphql_keys(R.merge(dict(id=dict(type=graphene.Int)), fields)),
    )))
    logger.debug('Mutation: %s' % mutation)
    return client.execute(mutation)


def process_query_value(model, value_dict):
    """
        Process the query value for a related model dict
    :param model:
    :param {dict} value: Dict of key values querying the related model. This could have embedded types as well.
    E.g. model User value {username: 'foo'} or model Group value {name: 'goo', user: {username: 'foo'}}
    :return: A list of Q expressions
    """
    return R.chain(
        R.identity,
        # Creates a 2-D array of Q expressions
        R.map_with_obj_to_values(
            lambda key, inner_value: process_query_kwarg(model, key, inner_value),
            value_dict
        )
    )


def process_query_kwarg(model, key, value):
    """
        Process a query kwarg. The key is always a string and the value can be a scalar or a dict representing the
        model given by model. E.g. model: User, key: 'user', value: {id: 1, username: 'jo'} or
        model User, key: 'user', value: {id: 1, group: {id: 2}}
        TODO I haven't made this work with ManyToMany yet, such as
        model User, key: 'user', value: {id: 1, groups: [{id: 2}, {name: 'fellas'}]}. This requires using __in
        for the django key and other fancy stuff
    :param model:
    :param {String} key: Key compatible with django filtering, except special case {key}__not which is converted
    to ~Q({key}={value}
    :param value: The value, can be a scalar or dict
    :return: A list of Q expressions like Q(x__y=1) and ~Q(x__contains='adf')
    """

    if key.endswith('__contains'):
        # Don't modify json contains searches
        # TODO this doesn't make sense because condition below is supposed to handle it
        return [Q(**{key: value})]
    elif key.endswith('__not'):
        # If the key ends in not it tells us to convert to a ~Q(key) expression
        k = key.replace('__not', '')
        return [~Q(**{k: value})]
    if isinstance(R.prop_or(None, key, model._meta._forward_fields_map), (JSONField,)):
        # Small correction here to change the data filter to data__contains to handle any json
        # https://docs.djangoproject.com/en/2.0/ref/contrib/postgres/fields/#std:fieldlookup-hstorefield.contains
        # This is just one way of filtering json. We can also do it with the argument structure
        return R.compose(
            lambda dct: R.map_with_obj_to_values(lambda key, value: Q(**{key: value}), dct),
            lambda dct: flatten_dct_until(dct, lambda key: not key.endswith('contains'), '__')
        )({key: value})
    elif R.has(key, model._meta._forward_fields_map):
        # If it's a model key
        if isinstance(model._meta._forward_fields_map[key], (ForeignKey, OneToOneField)):
            # Recurse on these, so foo: {bar: 1, car: 2} resolves to [['foo__bar' 1], ['foo__car', 2]]
            related_model = model._meta._forward_fields_map[key].related_model
            q_expressions = process_query_value(related_model, value)
            return R.map(
                # TODO we assume simple Q expressions with ony one child at children[0]
                lambda q_expression: Q(**{f'{key}__{q_expression.children[0][0]}': q_expression.children[0][1]}),
                q_expressions
            )
        elif isinstance(model._meta._forward_fields_map[key], (ManyToManyField)):
            raise NotImplementedError("TODO need to implement stringify for ManyToMany")

    return [Q(**{key: value})]


@R.curry
def flatten_query_kwargs(model, kwargs):
    """
        This handles resolving relationships like {user: {id: 1, group: {id: 2}}} in the kwargs by converting them
        to user__id==1 and user__group__id==2. It also adds contains to the end of json objects so that arrays
        are searched
        TODO it doesn't handle many-to-many yet. I need to write that
    :param data_field_name: The name of the data field, e.g. 'data'
    :param kwargs: The query kargs
    :return: A list of Django filter Q expressions
    """
    return R.chain(
        R.identity,
        R.values(
            R.map_with_obj(
                lambda key, value: process_query_kwarg(model, key, value),
                kwargs
            )
        )
    )


def merge_data_fields_on_update(data_fields, existing_instance, data):
    """
    Merges the given data fields with the existing values in the database
    New data gets priority, but this is a deep merge. Lists are not merged, the new data overrides
    :param {[String]} data_fields: E.g. ['data']
    :param {Object} existing_instance: Instance with data_fields that are dicts
    :param {Object} data: Graphene input object from mutation
    :return: {Object} The entire data dict with the merged values
    """
    return R.merge(
        # Merge regular fields
        R.omit(data_fields, data),
        # with a deep merge of the new data's data fields and the existing instance's data fields
        R.merge_deep(
            R.pick(data_fields, existing_instance.__dict__),
            # Strip out the Graphene objects so we can merge correctly
            R.compose(R.map_with_obj(lambda k, v: to_dict_deep(v)), R.pick(data_fields))(data),
            Merger([
                (list, ["override"]),
                (dict, ["merge"])
            ], ["override"], ["override"])
        )
    )
