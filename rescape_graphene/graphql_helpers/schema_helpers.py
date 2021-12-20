import inspect
import json
import logging
import sys
from decimal import Decimal

import graphene
import reversion
from deepmerge import Merger
from django.contrib.gis.db.models import OneToOneField, ManyToManyField, ForeignKey, \
    GeometryCollectionField
from django.db.models import JSONField, AutoField, CharField, BooleanField, BigAutoField, DecimalField, \
    DateTimeField, DateField, BinaryField, TimeField, FloatField, EmailField, UUIDField, TextField, IntegerField, \
    BigIntegerField, NullBooleanField, Q
from graphene import Scalar, InputObjectType, ObjectType, String, Field
from graphql import parse
from graphql.language import ast
from graphql.language.printer import print_ast
from inflection import camelize
from rescape_python_helpers import ramda as R, memoize
from rescape_python_helpers.functional.ramda import to_dict_deep, flatten_dct_until, \
    to_array_if_not

from .graphene_helpers import dump_graphql_keys, dump_graphql_data_object, camelize_graphql_data_object, call_if_lambda, \
    resolve_field_type

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

# Block complex types from being filtered on
# TODO
NON_COMPLEX_TYPES = [graphene.Date, graphene.DateTime, graphene.Int, graphene.Boolean, graphene.String, graphene.List]

# From django-filters. Whenever graphene supports filtering without Relay we can get rid of this here
# Educated guesss about what types for each to support. Django/Postgres might support fewer or more of these
# combinations than I'm aware of
# Skip most if testing. These take forever
# Results in a dict keyed by the filter suffix and valued by a dict of the allowed types and possibly a type_modifier
# lambda to create a grapheene.List of the given type for the 'in' and 'range' suffixes
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
            # Contains can be used for javascript matching and string matching
            # I think anything can have a contains filter, even complex types, because we might want
            # to test if a complex type contains certain javascript
            # https://docs.djangoproject.com/en/4.0/topics/db/queries/#containment-and-key-lookups
            'contains': dict(type_modifier=lambda typ: graphene.List(typ), allowed_types=[graphene.String, graphene.ObjectType] ),
            'in': dict(type_modifier=lambda typ: graphene.List(typ), allowed_types=NON_COMPLEX_TYPES)
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
            'exact': dict(allowed_types=NON_COMPLEX_TYPES),
            # this is the default, but keep so we can do negative queries, i.e. exact__not
            # 'iexact': dict(allowed_types=NON_COMPLEX_TYPES),
            # I think anything can have a contains filter, even complex types, because we might want
            # to test if a complex type contains certain javascript
            'contains': dict(),
            # 'icontains': dict(),
            'in': dict(type_modifier=lambda typ: graphene.List(typ), allowed_types=NON_COMPLEX_TYPES),
            'gt': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'gte': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'lt': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'lte': dict(allowed_types=[graphene.Int, graphene.Float, graphene.DateTime, graphene.Date]),
            'startswith': dict(allowed_types=[graphene.String]),
            # 'istartswith': dict(allowed_types=[graphene.String]),
            'endswith': dict(allowed_types=[graphene.String]),
            # 'iendswith': dict(allowed_types=[graphene.String]),
            # Range expects a 2 item tuple, so give it a list
            'range': dict(type_modifier=lambda typ: graphene.List(typ), allowed_types=NON_COMPLEX_TYPES),
            'isnull': dict(allowed_types=NON_COMPLEX_TYPES),
            # 'regex': dict(allowed_types=[graphene.String]),
            # 'iregex': dict(allowed_types=[graphene.String]),
            'search': dict(allowed_types=[graphene.String]),

            # postgres lookups
            'contained_by': dict(allowed_types=NON_COMPLEX_TYPES),
            # Date overlap
            'overlap': dict(allowed_types=[graphene.Date, graphene.DateTime]),
            # These are probably for json types so maybe useful
            'has_key': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            'has_keys': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            'has_any_keys': dict(allowed_types=[graphene.JSONString, graphene.InputObjectType]),
            # groups of 3 characters for similarity recognition
            # 'trigram_similar': dict(allowed_types=[graphene.String])
        }
    )
)(settings)

# Exclude some common prop keys, like for revisioning, that should never get filters.
# For instance, we don't want to create revision_id_contains or revision_id_in,
# because we don't want to be able to search for revisions by an id range
EXCLUDED_PROP_KEYS_FROM_FILTERING = [
    'order_by', 'version_number', 'revision', 'revision_id', 'page', 'pages', 'page_size', 'has_next', 'has_prev'
]


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


def fullname(klass):
    module = klass.__module__
    if module == 'builtins':
        return klass.__qualname__  # avoid outputs like 'builtins.str'
    return module + '.' + klass.__qualname__


def _memoize(args):
    return [
        # Only use graphene_type here. type is a function and can't be serialized
        fullname(
            call_if_lambda(args[0]['graphene_type'])
        ),
        args[1],
        # TODO We use the parent_type_class to make each type unique. I don't know why graphene won't let us reuse
        # input types within the schema. It seems like a UserInputType should be reusable whether it's the User
        # of a Region or the user of a Group.
        R.map(
            lambda cls: cls if isinstance(cls, str) else fullname(cls),
            args[2] if R.length(args) > 2 and R.isinstance((list, tuple), args[2]) else [args[2]]
        )
    ]


@memoize(
    map_args=_memoize,
    # Only fields_only can vary for the same input class
    map_kwargs=lambda kwargs: [R.prop_or(False, 'fields_only', kwargs)]
)
def input_type_class(field_config, crud, parent_type_classes, fields_only=False, with_filter_fields=True,
                     create_filter_fields_for_search_type=False):
    """
    An InputObjectType subclass for use as nested query argument types and mutation argument types
    The subclass is dynamically created based on the field_dict_value['graphene_type'] and the crud type.
    The fields are based on field_dicta_values['fields'] and the underlying Django model of the graphene_type,
    as well as the rules for the crud type spcecified in field_dict_vale.
    :param field_config:
    :param crud: CREATE, UPDATE, or READ, or None (for top-level search types with fields_only=True)
    :param parent_type_classes: String or String array of parent graphene type classes. Unfortunately, Graphene doesn't
    let us reuse input types around the schema, even if they are identical, so we must give them unique names
    based on the parent ancestry
    :param fields_only Default False. Don't create the inpub class, just return the fields that are created,
    including filter fields. This is like calling fields_with_filter_fields with a bit of prep
    :param with_filter_fields Default True. If False don't create filter fields. Only needed for things like
    pagination and version types where we don't want filters on the top level properties like page number, but
    do want it recursively on the objects property
    You can also use and array of field names here to just add filter fields at the top level for those fields
    :param create_filter_fields_for_search_type Default False, Usually we only add filter fields for READ crud types. This
    overrides that so that Search types can add filters
    :return: An InputObjectType subclass
    """
    # Get the Graphene type. This comes from graphene_type if the class containing the field is a Django Model,
    # It defaults to type, which is what we expect if we didn't have to use a graphene_type to distinguish
    # from the underlying Django type
    graphene_class = call_if_lambda(field_config['graphene_type'] or field_config['type'])
    fields = call_if_lambda(field_config['fields'])

    # Make it an array if not
    modified_parent_type_classes = to_array_if_not(parent_type_classes)

    combined_fields = fields_with_filter_fields(
        fields,
        graphene_class,
        parent_type_classes=modified_parent_type_classes,
        crud=crud,
        # Only continue with fields_only for search types. Otherwise we need types for the sub fields
        fields_only=create_filter_fields_for_search_type,
        with_filter_fields=with_filter_fields,
        create_filter_fields_for_search_type=create_filter_fields_for_search_type
    )
    if fields_only:
        return combined_fields

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
        combined_fields
    )


def fields_with_filter_fields(fields, graphene_class, parent_type_classes=[], crud=None, with_filter_fields=True,
                              fields_only=False,
                              create_filter_fields_for_search_type=False):
    """
        Adds filter fields to the given fields, so that for field name we add nameContains etc.
        This is used for search arguments as well as search class instances which can store searches
    :param fields:
    :param graphene_class: Needed for top level classes that correspond with a Django model and for uniquely
    naming the internal fields. You can also use the class name to avoid self-referencing problems
    :param parent_type_classes: Optional array of parent types when building embedded classes
    :param crud: Optional crud value 'create' or 'update' that remove update and create constraints
    :param with_filter_fields Default True. If False don't create filter fields. Only needed for things like
    pagination and version types where we don't want filters on the top level properties like page number, but
    do want it recursively on the objects property
    You can also use and array of field names here to just add filter fields at the top level for those fields
    :param fields_only If true don't create input type classes when recursing (used by search types)
    :param create_filter_fields_for_search_type Default False, Usually we only add filter fields for READ crud types. This
    overrides that so that Search types can add filters
    :return: The combined fields
    """
    _fields_only = fields_only or create_filter_fields_for_search_type

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
            # Only take the id, unless related_input=true for a field
            lambda fields: R.merge(
                R.pick(['id'], fields),
                R.filter_dict(
                    lambda name_field: R.compose(R.equals(ALLOW), R.prop_or(False, 'related_input'))(name_field[1]),
                    fields
                )
            )
        )(fields) if crud in [CREATE, UPDATE] else fields
    ) if django_model_of_graphene_type(graphene_class) else fields

    # These fields allow us to filter on InputTypes when we use them as query arguments
    # This doesn't apply to Update and Create input types, since we never filter during those operations
    filter_fields = allowed_filter_arguments(
        # If with_filter_fields is an array of field names only allow those field names through
        R.filter_dict(lambda kv: kv[0] in with_filter_fields if isinstance(with_filter_fields, list) else True,
                      input_type_field_configs),
        graphene_class,
        fields_only=_fields_only
    ) if with_filter_fields and (
            R.equals(READ, crud) or create_filter_fields_for_search_type
    ) else {}

    # If fields_only, quit now without creating input fields
    if _fields_only:
        return filter_fields

    # Add 'order_by_field' so the call can specify order by values that match django's syntax or similar
    order_by_field = dict(order_by=String())

    input_fields = input_type_fields(
        input_type_field_configs,
        crud,
        # Keep our naming unique by appending parent classes, ordered newest to oldest
        R.concat([graphene_class], to_array_if_not(parent_type_classes)),
        fields_only=_fields_only,
        with_filter_fields=with_filter_fields,
        create_filter_fields_for_search_type=create_filter_fields_for_search_type
    )

    return R.merge_all([order_by_field, filter_fields, input_fields])


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
        PRIMARY if R.prop_or(False, 'primary_key', field) else None,
        UNIQUE if R.prop_or(False, 'unique', field) else None,
        R.prop_or(None, R.has('attname', field), field_to_unique_field_groups)
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
    :param parent_type_classes Single class or array of parent classes of this graphene class
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
            process_field(
                field_to_unique_field_groups,
                field,
                R.prop(field.name, field_dict),
                R.to_array_if_not(parent_type_classes)
            )
        ],
        # Only accept model fields that are defined in field_dict
        R.filter(
            lambda field: field.name in field_dict,
            R.concat(model._meta.fields, R.concat(model._meta.many_to_many, model._meta.related_objects))
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
def resolve_type(graphene_type, field_config, fields_only=False, with_filter_fields=True):
    """
     Resolves the field type, instantiating scalars and recursing on input types (complex types)
     If fields_only is true (default Fasle), just return the field_config for scalars without instantiating
     and for complex types pass fields_only to the recursion
     If the type is a scalar, just instantiate
     Otherwise created a related field InputType subclass. In order to query a nested object, it has to
     be an input field. Example: If A User has a Group, we can query for users named 'Peter' who are admins:
     graphql: users: (name: "Peter", group: {role: "admin"})
     https://github.com/graphql-python/graphene/issues/431
     When fields_only=False, meaning we have an input_type_class, instantiate it with ()

    :param graphene_type: The graphene type of the class containing the field_config. Used only for naming
    the parent class in recursion
    :param field_config: Contains either type (coming from a Django model type definition) or graphene type
    (coming from a non-Django model type definition). This is the type that is optionally instnatiated or
    recursed upon
    :param fields_only: Default False, only get the field config for scalars and recurse with this flag for
    complex types
    :return: The input type of the field config or the one of those as the result of recursion
    """

    field_type = resolve_field_type(field_config)
    if inspect.isclass(field_type) and issubclass(field_type, Scalar):
        # Return the type instantiated
        return field_type() if not fields_only else field_config
    else:
        # Resolve with recursion
        input_type_class_instance = input_type_class(field_config, READ, graphene_type, fields_only=fields_only,
                                                     with_filter_fields=with_filter_fields)
        return R.when(callable, lambda l: l())(input_type_class_instance)


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


def allowed_filter_pairs(field_name, graphene_instance, field_config, fields_only=False, with_filter_fields=True):
    """
        Creates pairs of filter_field, graphene_type such as [id_contains, Int(), id_in, List(Int())] for
        filter fields that are allowed for the field_name's graphene_type
    :param field_name: Field being given filters
    :param field_config: Field config
    :return: List of pairs

    """

    def filter_field_config_or_type(config):
        type_modifier = config['type_modifier'] if R.has('type_modifier', config) else lambda *type_and_args: \
            type_and_args[0]()
        return R.merge(field_config, dict(type_modifier=type_modifier)) if fields_only else (
            # If a type_modifier is needed for the filter type, such as a List constructor call it
            # with the field's type as an argument
            type_modifier(graphene_instance.__class__)
        )

    return R.map_with_obj_to_values(
        # Make all the filter pairs for each key id: id_contains, id: id_in, etc
        lambda filter_str, config: [
            '%s_%s' % (field_name, filter_str),
            filter_field_config_or_type(config)
        ],
        # Only allow filters compliant with the type of pair[1]
        R.filter_dict(
            lambda keyvalue: field_name not in EXCLUDED_PROP_KEYS_FROM_FILTERING and (
                    not R.has('allowed_types', keyvalue[1]) or
                    R.any_satisfy(
                        lambda typ: issubclass(
                            graphene_instance['type'] if \
                                isinstance(graphene_instance, dict) else \
                                graphene_instance.__class__,
                            typ
                        ),
                        keyvalue[1]['allowed_types']
                    )
            ),
            FILTER_FIELDS if with_filter_fields else dict()
        )
    )


def make_filters(field_name, graphene_instance, field_config, fields_only=False, with_filter_fields=True):
    """
        Add the needed filters to the standard 'eq' value
        This compensates for django-filter not being implemented to work in graphene without Relay
    :param pair:
    :return:
    """
    return R.from_pairs(
        R.concat(
            [[field_name, field_config if fields_only else graphene_instance]],
            allowed_filter_pairs(field_name, graphene_instance, field_config, fields_only=fields_only,
                                 with_filter_fields=with_filter_fields)
        )
    )


def add_filters(field_and_instance_and_config, fields_only=False, with_filter_fields=True):
    """
        Adds filter arguments to 'eq' arguments.
    :param field_and_instance_and_config: list of dict(field_name, graphene_type, field_config)
    :return: dict of the 'eq' arguments and the filter args e.g. {id: Int(), id_contains: List(Int), ...}
    """
    return R.compose(
        R.merge_all,
        lambda field_and_instance_and_config: R.map(
            lambda field_and_type_and_config: make_filters(
                *R.props(['field_name', 'graphene_instance', 'field_config'], field_and_type_and_config),
                fields_only=fields_only,
                with_filter_fields=with_filter_fields
            ),
            field_and_instance_and_config
        ),
    )(field_and_instance_and_config)


def top_level_allowed_filter_arguments(fields, graphene_type, with_filter_fields=True,
                                       create_filter_fields_for_search_type=False):
    """
        For top-level read calls.
        Like allowed_filter_arguments but only used for arguments and adds filter variables like id_contains.
        Note that django needs __ so these are converted for resolvers. The graphql interface converts them to
        camel case
    :param fields: The fields for the graphene type
    :param graphen_type: The graphene type
    :param with_filter_fields Default True. If False don't create filter fields. Only needed for things like
    pagination and version types where we don't want filters on the top level properties like page number, but
    do want it recursively on the objects property
    You can also use and array of field names here to just add filter fields at the top level for those fields
    :return: dict of field keys and there graphene type, either a primitive or input type
    """
    return input_type_class(
        dict(fields=fields, graphene_type=graphene_type),
        'read', [], fields_only=True, with_filter_fields=with_filter_fields,
        create_filter_fields_for_search_type=create_filter_fields_for_search_type,
    )


def allowed_filter_arguments(fields_dict, graphene_type, fields_only=False, with_filter_fields=True):
    """
        Used internally by calls started by top_level_allowed_filter_arguments
    :param fields_dict: The fields_dict for the Django model
    :param graphen_type: Type used for embedded input class naming
    :param fields_only: Default false, Return fields only not types
    :return: dict of field keys and there graphene type, either a primitive or input type
    """

    def _x(field_name, field_config):
        return dict(
            field_name=field_name,
            field_config=field_config,
            graphene_instance=resolve_type(graphene_type, field_config, fields_only=fields_only,
                                           with_filter_fields=with_filter_fields)
        )

    def _y(field_and_instance_and_config):
        return add_filters(field_and_instance_and_config, fields_only=fields_only,
                           with_filter_fields=with_filter_fields)

    return R.compose(
        _y,
        lambda dct: R.map_with_obj_to_values(
            _x,
            dct
        ),
        lambda dct: R.filter_dict(
            # Don't allow DENYed READ fields to be used for querying
            lambda key_value: R.and_func(
                True,
                R.not_func(R.prop_eq_or_in(READ, DENY, key_value[1]))
            ),
            dct
        )
    )(call_if_lambda(fields_dict))


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


def instantiate_graphene_type_or_fields(field_config, parent_type_classes, crud,
                                        field_name,
                                        fields_only=False,
                                        with_filter_fields=True,
                                        create_filter_fields_for_search_type=False):
    """
        Instantiates the Graphene type at value.type. Most of the time the type is a primitive and
        doesn't need to be mapped to an input type. If the type is an ObjectType, we need to dynamically
        construct an InputObjectType
    :param field_config: Dict containing type and possible crud fields like value['create'] and value['update']
    These optional values indicate if a field is required
    :param fields_only Only create fields, not the type
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :param crud: READ, WRITE, UPDATE, DELETE or None if create_filter_fields_for_search_type is true
    :param field_name The field name, just for debugging
    :param create_filter_fields_for_search_type Default False, Usually we only add filter fields for READ crud types. This
    overrides that so that Search types can add filters
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
        resolved_graphene_type_or_fields = input_type_class(
            dict(graphene_type=graphene_type, fields=fields),
            crud,
            parent_type_classes,
            fields_only=fields_only,
            with_filter_fields=with_filter_fields,
            create_filter_fields_for_search_type=create_filter_fields_for_search_type
        )
    elif R.isfunction(graphene_type) and \
            R.compose(R.equals(0), R.length, R.prop('parameters'), inspect.signature)(graphene_type):
        # If out graphene_type is a no arg lambda it means it needs lazy evaluation to avoid circular imports
        # This is only true for representing reverse relationships on django models
        _graphene_type = graphene_type()
        _fields = R.compose(call_if_lambda, R.prop('fields'))(field_config)
        resolved_graphene_type_or_fields = input_type_class(
            dict(graphene_type=_graphene_type, fields=_fields), crud,
            parent_type_classes, fields_only=fields_only
        )
    elif R.isfunction(graphene_type):
        # If a lambda is returned with params we have an InputType subclass that needs to know the crud type
        resolved_graphene_type_or_fields = graphene_type(crud)

    else:
        # Otherwise we have a simple type
        resolved_graphene_type_or_fields = graphene_type

    # If we only want fields we can return now
    if fields_only:
        return resolved_graphene_type_or_fields

    # Instantiate using the type_modifier function if we need to wrap this in a List and/or give it a resolver,
    # Otherwise instantiate and pass the required flag
    return graphene_type_modifier(resolved_graphene_type_or_fields) if \
        graphene_type_modifier else \
        resolved_graphene_type_or_fields(
            # Add required depending on whether this is an insert or update
            # This means if a user omits these fields an error will occur
            required=R.prop_eq_or_in_or(False, crud, REQUIRE, field_config)
        )


def input_type_fields(fields_dict, crud, parent_type_classes=[], fields_only=False,
                      with_filter_fields=True,
                      create_filter_fields_for_search_type=False):
    """
    :param fields_dict: The fields_dict for the Django model or json data
    :param crud: INSERT, UPDATE, or DELETE. If None the type is guessed
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :param fields_only
    :param with_filter_fields Default True, indicates to add filter fields for queries. create_filter_fields_for_search_type
    is used only for SearchTypes that have filter fields as type fields
    :param create_filter_fields_for_search_type: Default false. Only used by Search types to add filter versions of their fields
    :return:
    """
    # Don't guess the crud type if create_filter_fields_for_search_type is true. We want it null in that case
    crud = crud or (guess_update_or_create(fields_dict) if not create_filter_fields_for_search_type else crud)
    return R.map_with_obj(
        lambda field_name, field_config: instantiate_graphene_type_or_fields(
            # field_name is just passed for debugging
            field_config, parent_type_classes, crud, field_name,
            fields_only=fields_only,
            with_filter_fields=with_filter_fields,
            create_filter_fields_for_search_type=create_filter_fields_for_search_type,
        ),
        # Filter out values that are deny
        # This means that if the user tries to pass these fields to graphql an error will occur
        R.filter_dict(
            lambda key_value: R.not_func(R.prop_eq_or(False, crud, DENY, key_value[1])),
            call_if_lambda(fields_dict)
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
        to_insert = R.merge_deep_all(R.map_with_obj_to_values(
            lambda key, value: key_value_based_on_unique_or_foreign(
                key_to_modified_key_and_value,
                fields_dict,
                key
            ),
            field_name_to_value
        ))
        # If there are only defaults, which is true if no property must be globally unique, such as a key,
        # then extract everything from defaults. This prevents a defaults only dict that makes Django
        # return all model instances when it's testing to do an update or an insert
        return R.when(R.compose(R.equals(1), R.length, R.keys), R.prop('defaults'))(to_insert)


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
    :param query_name: The name of the query
    :returns A lambda that expects a Graphene client and **kwargs that contain kwargs for the client.execute call.
    The only key allowed is variables, which contains param key values. Example: variables={'user': 'Peter'}
    This results in query whatever(id: String!) { query_name(id: id) ... }
    """

    # If we already have a search class, it has filters as fields, so don't add them here
    field_type_lookup = top_level_allowed_filter_arguments(
        fields,
        graphene_type,
        with_filter_fields='Search' not in graphene_type.__name__
    )

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
            lambda k, v: [
                camelize(k, False),
                R.if_else(
                    lambda lookup: R.has('_meta', lookup),
                    # Field Case
                    lambda lookup: lookup._meta.name,
                    # List Case
                    lambda lookup: f'[{lookup._of_type._meta.name}]'
                )(field_type_lookup[k])
            ],
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
        query = print_ast(parse('''query %s%s { 
                %s%s {
                    %s
                }
            }''' % (
            query_name,
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
            dump_graphql_keys(field_overrides or call_if_lambda(fields))
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
        logger.debug(f'Query: {query}\nKwargs: {R.dump_json(R.prop("variables", camelized_kwargs))}')
        return client.execute(
            query,
            **camelized_kwargs
        )

    return form_query


def capitalize_first_letter(str):
    """
    Capitalize the first letter since str.capitalize() lowercases everything first (yes Python sucks)
    :param str:
    :return:
    """
    return str[:1].upper() + str[1:]


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
        mutation %sMutation($data: %sInputType!) {
            %s(%sData: $data) {
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
        capitalize_first_letter(R.item_path(['crud', update_or_create], mutation_config)),
        R.item_path(['crud', update_or_create], mutation_config),
        # The name of the InputDataType that is defined for this function, e.g. FooInputDataType
        name,
        # Again the name, this time used for the structure of the return query e.g. foo { ...return value ...}
        name,
        # The return query dump, which are all the fields available that aren't marked read=IGNORE.
        # One catch is we need to add the id,
        # which isn't part of field_configs because Graphene handles ids automatically
        dump_graphql_keys(R.merge(dict(id=dict(type=graphene.Int)), fields)),
    )))
    # Key values for what is being created or updated. This is dumped recursively and matches the structure
    # of the InputDataType subclass
    variables = dump_graphql_data_object(dict(data=values))
    logger.debug(f'Mutation: {mutation}\nVariables: {variables}')
    return client.execute(mutation, variables=camelize_graphql_data_object(dict(data=values)))


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


def _flatten_until(key, value):
    return R.isinstance(str, key) and not R.isinstance(list, value)


def _key_matches_filter_field(key):
    """
        Returns true if the key string ends with a FILTER_FIELD like contains or range or in
    :param key:
    :return:
    """
    last_key = R.last(key.split('__'))
    return R.has(last_key, FILTER_FIELDS)


def _related_model_expressions(related_model, value, key):
    # Convert the values to array if not and chain to flatten
    if R.equals('in', R.last(key.split('__'))):
        # If we have an __in suffix we expect an array of related objects.
        # We do OR queries for these and return a single Q expression related_model_key__in=sub query
        qs = R.map(lambda obj: Q(**obj), value)
        q_expression = related_model.objects.filter(R.reduce(
            lambda q1, q2: q1 | q2,
            R.head(qs),
            R.tail(qs)
        ))
        return [Q(**{key: q_expression})]
    else:
        # Process each value to 1 or more result and chain to flatten
        q_expressions = R.chain(
            lambda v: process_query_value(related_model, v),
            to_array_if_not(value)
        )
        # Map each to a Q expression to be ANDed
        return R.map(
            # TODO we assume simple Q expressions with ony one child at children[0]
            lambda q_expression: Q(**{f'{key}__{q_expression.children[0][0]}': q_expression.children[0][1]}),
            q_expressions
        )


def process_query_kwarg(model, key, value):
    """
        Process a query kwarg. The key is always a string and the value can be a scalar or a dict representing the
        given model. E.g. model: User, key: 'user', value: {id: 1, username: 'jo'} or
        model User, key: 'user', value: {id: 1, group: {id: 2}}
        This works in a limited capacity with ManyToMany. You can pass id__in=[{id: x1, id: x2, ...}]
        model User, key: 'user', value: {id: 1, groups: [{id: 2}, {name: 'fellas'}]}. This requires using __in
        for the django key and other fancy stuff
    :param model:
    :param {String} key: Key compatible with django filtering, except special case {key}__not which is converted
    to ~Q({key}={value}
    :param value: The value, can be a scalar or dict
    :return: A list of Q expressions like Q(x__y=1) and ~Q(x__contains='adf')
    """

    if False and key.endswith('__contains'):
        # Don't modify json contains searches
        # TODO this doesn't make sense because condition below is supposed to handle it
        return [Q(**{key: value})]
    elif key.endswith('__not'):
        # If the key ends in not it tells us to convert to a ~Q(key) expression
        k = key.replace('__not', '')
        return [~Q(**{k: value})]
    if isinstance(R.prop_or(None, key, model._meta._forward_fields_map), (JSONField,)):
        return R.compose(
            lambda dct: R.map_with_obj_to_values(
                lambda key, value: Q(**{key: value}),
                dct
            ),
            # Small correction here to change the data filter to data... to data...__contains to handle any json
            # https://docs.djangoproject.com/en/2.0/ref/contrib/postgres/fields/#std:fieldlookup-hstorefield.contains
            # If the value is an object or array,
            # add __contains to the end there isn't already a filter suffix
            # __contains allows matching an object or array without the array orders having to match
            lambda dct: R.map_keys_with_obj(
                lambda key, value: R.when(
                    lambda key: isinstance(value, (dict, list)) and not _key_matches_filter_field(key),
                    lambda key: R.join('__', [key, 'contains'])
                )(key),
                dct
            ),
            lambda dct: flatten_dct_until(
                dct,
                _flatten_until,
                '__'
            )
        )({key: value})
    elif R.has(key, model._meta._forward_fields_map):
        # If it's a model key
        if isinstance(model._meta._forward_fields_map[key], (ForeignKey, OneToOneField, ManyToManyField)):
            # Recurse on these, so foo: {bar: 1, car: 2} resolves to [['foo__bar' 1], ['foo__car', 2]]
            related_model = model._meta._forward_fields_map[key].related_model
            return _related_model_expressions(related_model, value, key)
        elif isinstance(model._meta._forward_fields_map[key], (ManyToManyField)):
            raise NotImplementedError(f'Unrecognized field type for {model._meta._forward_fields_map[key]}')
    elif R.contains(R.head(key.split('__')), R.map(R.prop('name'), model._meta.related_objects)):
        # Recurse on these, so foo: {bar: {id: 1}, car: {id: 2}} resolves to [['foo__bar__id' 1], ['foo__car__id', 2]]
        many_to_many_rel = R.find(
            lambda obj: R.compose(
                R.equals(R.head(key.split('__'))),
                R.prop('name')
            )(obj),
            model._meta.related_objects)
        related_model = many_to_many_rel.related_model
        return _related_model_expressions(related_model, value, key)

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
            R.pick(R.concat(['id'], data_fields), existing_instance.__dict__),
            # Strip out the Graphene objects so we can merge correctly
            R.compose(R.map_with_obj(lambda k, v: to_dict_deep(v)), R.pick(data_fields))(data),
            Merger([
                (list, ["override"]),
                (dict, ["merge"])
            ], ["override"], ["override"])
        )
    )


def delete_if_marked_for_delete(model_cls, grapene_upsert_class, upsert_field_name, model_data):
    """
    Delete functionality for graphene models whose django_model mixes in  safe-delete
    This looks for a deleted=datetime field and calles manage.delete on the instance
    matching model_data.id if deleted is not null
    :param model_cls: The Django model class
    :param grapene_upsert_class: The Graphene upsert class
    :param upsert_field_name: The named argument to pass when instantiating the upsert class, e.g. 'region' for Region
    :param model_data:  The model data. Must have non-null id and deleted fields to cause a deletion
    :return:
    """

    if R.all_satisfy(lambda prop: R.prop_or(False, prop, model_data), ['id', 'deleted']):
        # Existing objects with a nonnull deleted datetime are deleted
        instances = model_cls.objects.filter(
            id=R.prop('id', model_data)
        )
        instances.delete()
        instance = model_cls.objects.deleted_only().get(**R.pick(['id'], model_data))
        if not instance:
            raise Exception(f"Failed to delete {R.prop('id', instance)}")
        return grapene_upsert_class(**{upsert_field_name: instance})
    return None


def update_or_create_with_revision(model_class, update_or_create_values):
    """
        Perform update or create with the given model_class and update_or_create_values
        where the model_class must be registered with django-reversion. The update or create
        saves a new revision
    :param model_class:
    :param update_or_create_values:
    :return: The tuple from update_or_create
    """

    # Declare a revision block.
    with reversion.create_revision():
        if not R.prop_or(
                False,
                'id',
                update_or_create_values
        ) and not R.prop_or(
            False,
            'defaults',
            update_or_create_values):
            # If there is no id and no defaults, we have to do a straight save.
            # update_or_create could match multiple existing instances
            instance = model_class(**update_or_create_values)
            instance.save()
            return instance, True
        else:
            return model_class.objects.update_or_create(**update_or_create_values)


def deep_merge_existing_json(django_model, json_prop, data):
    """
        When mutating data, given a django model and a json prop with new data,
        see if a version of the instance is already in the database and if so deep merge
        what is in the database with data[json_prop], favoring the values in the latter
        The existing instance is searched using id=data['id']
        Note that in the deep merge we replace any old list with any new list. We have
        to do this because it's impossible to know the caller's intention if they provide a new list of items,
        so it's up to the caller to preserver the old list values. If the user doesn't provide a replacing
        array the old one is maintained (I think)
    :param django_model:
    :param json_prop: The model prop that is a json field
    :param data: The data of the entire model instance, optionally with id and json_prop. If json_prop is None
    then nothing changes
    :return: The merged dict of json_field
    """

    if R.has('id', data) and R.has(json_prop, data):
        # New data gets priority, but this is a deep merge.
        # List
        return R.merge_deep(
            django_model.objects.get(id=data['id']).data,
            data[json_prop],
            merger=Merger(
                [
                    (list, ["override"]),
                    (dict, ["merge"])
                ],
                ["override"],
                ["override"]
            )
        )
    # Otherwise just return the new value if any
    return R.prop_or(None, json_prop, data)


def invert_q_expressions_sets(q_expressions):
    """
        Index q_expressions by their key (children[0][0]) into sets, then
        inverts the matrix of q_expressions into 1 or 2 sets. The first set is most and the 2nd set
        ist the second many-to-many expression many_to_many_intersection_streets_to_and_statement
        that must be run as a second filter
    :param q_expressions: list q_expressions. Only supports simple Q expressions with one clause
    :return: 1 or 2 sets of q_expressions that can be used by sequential filters
    """

    return R.compose(
        # Sort by set index and return the values
        lambda index_dicts: R.map(
            lambda key: R.compose(
                lambda values: R.map(R.prop('q_expression'), values),
                lambda key: R.prop(key, index_dicts)
            )(key),
            sorted(R.keys(index_dicts))
        ),
        # Group by index within each set. Most will be 0. Only then second many-to-many can be 1
        lambda dcts: R.index_by(R.prop('index'), dcts),
        lambda q_expression_sets: R.chain(
            lambda q_expression_set: R.map(
                lambda i_q_expression: dict(index=i_q_expression[0], q_expression=i_q_expression[1]),
                enumerate(q_expression_set)
            ),
            q_expression_sets
        ),
        # One special case we need to handle multiple 'intersections_data_streets'
        # We need to sequentially filter
        # We do this by grouping them together into an array here, then we invert the 2D array
        lambda q_expressions: R.values(
            R.index_by(lambda q_expression: q_expression.children[0][0], q_expressions)
        )
    )(q_expressions)


def process_filter_kwargs(model, **kwargs):
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
            # Make sure __ or _ become __
            lambda k, v: k.replace('__', '_').replace('_', '__')
            if R.any_satisfy(lambda string: '_%s' % string in str(k), R.keys(FILTER_FIELDS))
            else k
        )
    )(kwargs)


def query_with_filter_and_order_kwargs(model, **kwargs):
    """
        Calls process_filter_kwargs without the order_by kwarg, which if present is split by common and
        used with query.order_by(*order by clauses)
    :param model:
    :param kwargs:
    :return:
    """
    q_expressions = process_filter_kwargs(model, **R.omit(['order_by'], kwargs))
    query = model.objects.filter(*q_expressions)
    if not R.has('order_by', kwargs):
        return query
    else:
        return query.order_by(*kwargs['order_by'].split(','))


def process_filter_kwargs_with_to_manys(model, process_filter_kwargs=process_filter_kwargs, **kwargs):
    """
        Calls process_filter_kwargs and then invert_q_expressions_sets so that
        the filtering can correctly handle to-many relations. This works
        by grouping the same keys together so that a search for two values of a to-many
        property must both be present (most often one is present in each of two to-mnay instances)
    :param model: The django model
    :param process_filter_kwargs Defaults to process_filter_kwargs, can be overridden for special cases
    :param kwargs: The kwargs to filter by
    :return: Sets of q_expressions that are run sequentially
    """
    return R.compose(
        lambda q_expressions: invert_q_expressions_sets(q_expressions),
        lambda kwargs: process_filter_kwargs(model, **kwargs)
    )(kwargs)


def query_sequentially(manager, manager_method, q_expressions_sets):
    """
        Sequentially queries the q_expression_sets formed by  process_filter_kwargs_with_to_manys/invert_q_expressions_sets
        Sequentially querying allows toMany values to be sought when multiple matching toMany instances are sought
    :param manager: The django model manager
    :param manager_method: The django model manager method. Normally 'filter', but could be 'count' or 'get'
    For sequential queries only the last query can be anything other than filter
    :param q_expressions_sets: List of lists of q expressions, where common query paths are separated into
    different sets so they can be run sequentially (see invert_q_expressions_sets)
    :return: The query response
    """

    if not R.length(q_expressions_sets):
        return getattr(manager, manager_method)()

    def _reduce(last, mgr_or_queryset, q_expressions_set):
        # We need distinct because the intersections__data__streets can generate duplicates of the same location
        return getattr(mgr_or_queryset, manager_method if last else 'filter')(*q_expressions_set).distinct()

    last = R.last(q_expressions_sets)
    return R.reduce(
        lambda manager_or_query, q_expressions: _reduce(
            R.equals(q_expressions, last),
            manager_or_query,
            q_expressions
        ),
        manager,
        q_expressions_sets
    )


def apply_type(v, with_filter_fields=True):
    # What filter arguments are allowed for this field type. Get them here
    allowed_arguments = allowed_filter_arguments(R.prop('fields', v), R.prop('graphene_type', v),
                                                 with_filter_fields=with_filter_fields) if \
        R.has('fields', v) else None

    # If we have allowed arguments make args a 2 element array. The first element is always the graphene type to
    # construct
    args = [R.if_else(
        R.has('type'),
        R.prop('type'),
        R.prop('graphene_type')
    )(v)] + ([allowed_arguments] if allowed_arguments else [])

    def x(typ, allowed_args):
        # TODO there seems to be a case where using v['type'] on fields of DjangoTypes doesn't make sense.
        # v['type'] is actually an input type, so it doesn't make sense for top-level declarations.
        # In this case just construct the graphene type with allow args
        return Field(R.prop_or(R.prop_or(None, 'graphen_type', v), 'type', v), allowed_args)

    def y(typ):
        return typ()

    t = R.prop_or(
        x if R.length(args) == 2 else y,
        'type_modifier',
        v
    )

    return t(*args)


def type_modify_fields(data_field_configs, with_filter_fields=True):
    """
        Converts json field configs based on if they have a type_modifier property. The type_modifier property
        allows us to make the type defined at graphene_type to be a Field or a List, depending on what we need
    :param data_field_configs: List of field configs that each might have type_modifier. Exmample:
    [
        # This is a field that points to a Django type User, so it resolves to Field(UserType)
        # with a resolver that handles Django models
        friend=dict(
            type=UserType,
            graphene_type=UserType,
            fields=merge_with_django_properties(UserType, dict(id=dict(create=REQUIRE))),
            type_modifier=lambda *type_and_args: Field(*type_and_args, resolver=model_resolver_for_dict_field(get_user_model()))
        ),
        # This is a field that points to a json dict modeled in graphene with ViewportDataType, so it
        resolves to Field(UserRegionDataType) with a resolver that handles a dict
        viewport=dict(
            type=ViewportDataType,
            graphene_type=ViewportDataType,
            fields=viewport_data_fields,
            type_modifier=lambda *type_and_args: Field(*type_and_args, resolver=resolver_for_dict_field),
        )
        # This is a field that points to a json list of dicts, each modeled in graphene with UserRegionDataType, so it
        resolves to List(UserRegionDataType) with a resolver that handles lists of dicts
        user_regions=dict(
            type=UserRegionDataType,
            graphene_type=UserRegionDataType,
            fields=user_region_data_fields,
            type_modifier=lambda typ: List(typ, resolver=resolver_for_dict_list)
        )
    ]
    :return: A list of Graphene Fields, created by mapping the field_configs. If the field_config has
    a type_modifier then it is called with field_config['type'] and its result is returned. Otherwise
    we simply call field_config['type']() to construct an instance of the type
    """

    def _x(k, v):
        return apply_type(v, with_filter_fields=with_filter_fields)

    return R.map_with_obj(
        # If we have a type_modifier function, pass the type to it, otherwise simply construct the type
        # This all translates to Graphene.Field|List(type, [fields that can be queried])
        _x,
        data_field_configs
    )
