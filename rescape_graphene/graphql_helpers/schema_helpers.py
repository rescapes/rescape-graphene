import inspect
import logging
import sys
from decimal import Decimal

from graphql.language.printer import print_ast
import graphene
from django.contrib.gis.db.models import GeometryField, OneToOneField, ManyToManyField, ForeignKey, \
    GeometryCollectionField
from graphql import parse

from rescape_python_helpers import ramda as R
from django.contrib.postgres.fields import JSONField
from django.db.models import AutoField, CharField, BooleanField, BigAutoField, DecimalField, \
    DateTimeField, DateField, BinaryField, TimeField, FloatField, EmailField, UUIDField, TextField, IntegerField, \
    BigIntegerField, NullBooleanField
from graphene import Scalar, InputObjectType, ObjectType
from graphql.language import ast
from inflection import camelize

from rescape_graphene.schema_models.geojson.types import GrapheneGeometry, GrapheneGeometryCollection
from .graphene_helpers import dump_graphql_keys, dump_graphql_data_object
from .memoize import memoize
logger = logging.getLogger('rescape_graphene')

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
# UNIQUE primary key
PRIMARY = 'primary'

# Indicates a CRUD operation is can optionally use this field
ALLOW = 'allow'

CREATE = 'create'
READ = 'read'
UPDATE = 'update'
DELETE = 'delete'

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
def input_type_class(field_dict_value, crud, parent_type_classes=[]):
    """
    An InputObjectType subclass for use as nested query argument types and mutation argument types
    The subclass is dynamically created based on the field_dict_value['graphene_type'] and the crud type.
    The fields are based on field_dicta_values['fields'] and the underlying Django model of the graphene_type,
    as well as the rules for the crud type spceified in field_dict_vale.
    :param field_dict_value:
    :param crud: CREATE, UPDATE, or READ
    :param parent_type_classes: String or String array of parent graphene type classes. Unfortunately, Graphene doesn't
    let us reuse input types around the schema, even if they are identical, so we must give them unique names
    based on the parent ancestry
    :return: An InputObjectType subclass
    """
    # Get the Graphene type. This comes from graphene_type if the class containing the field is a Django Model,
    # It defaults to type, which is what we expect if we didn't have to use a graphene_type to distinguish
    # from the underlying Django type
    graphene_class = field_dict_value['graphene_type'] or field_dict_value['type']
    # Make it an array if not
    modified_parent_type_classes = parent_type_classes if R.isinstance((list, tuple), parent_type_classes) else [
        parent_type_classes]
    return type(
        '%s%sRelated%sInputType' % (
            graphene_class.__name__,
            # Use the ancestry for uniqueness of name
            R.join('of', R.concat([''], modified_parent_type_classes)),
            camelize(crud, True)),
        (InputObjectType,),
        # Create Graphene types for the InputType based on the field_dict_value.fields
        # This will typically just be an id field to reference an existing object.
        # If the graphene type is based on a Django model, the Django model fields are merged with it,
        # otherwise it's assumed that field_dict_value['fields'] are independent of a Django model and
        # each have their own type property
        # It could be used to create a dependent object, for instance creating a UserPreference instance
        # on a User instance
        input_type_fields(
            merge_with_django_properties(
                graphene_class,
                field_dict_value['fields']
            ) if hasattr(graphene_class._meta, 'model') else
            field_dict_value['fields'],
            crud,
            # Keep our naming unique by appending parent classes, ordered newest to oldest
            R.concat([graphene_class], modified_parent_type_classes)
        )
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
        GeometryField: GrapheneGeometry,
        GeometryCollectionField: GrapheneGeometryCollection
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
            model._meta.fields
        )
    ))


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
            parse_django_class(graphene_type._meta.model, field_dict, graphene_type))
    )


def allowed_query_arguments(fields_dict, graphene_type):
    """
        Returns fields that can be queried
    :param fields_dict: The fields_dict for the Django model
    :param graphen_type: Type used for emboded input class naming
    :return:
    """

    def resolve_type(value):
        # If the type is a scalar, just instantiate
        # Otherwise created a related field InputType subclass. In order to query a nested object, it has to
        # be an input field. Example: If A User has a Group, we can query for users named 'Peter' who are admins:
        # graphql: users: (name: "Peter", group: {role: "admin"})
        # https://github.com/graphql-python/graphene/issues/431
        return R.prop('type', value)() if \
            inspect.isclass(R.prop('type', value)) and issubclass(R.prop('type', value), Scalar) else \
            input_type_class(value, READ, graphene_type)()

    return R.compose(
        R.map_dict(resolve_type),
        R.filter_dict(
            lambda key_value:
            # Only; accept Scalars. We don't need Relations because they are done automatically by graphene
            # Correction, do include Relations. Graphene does not add these in for us. It's up to us to allow
            # all relations as query variables.
            # Don't allow DENYed READs
            R.and_func(
                # not R.prop_or(False, 'django_type', key_value[1]),
                True,
                R.not_func(R.prop_eq_or_in(READ, DENY, key_value[1]))
            )
        )
    )(fields_dict)


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


def instantiate_graphene_type(value, parent_type_classes, crud):
    """
        Instantiates the Graphene type at value.type. Most of the time the type is a primitive and
        doesn't need to be mapped to an input type. If the type is an ObjectType, we need to dynamically
        construct an InputObjectType
    :param value: Dict containing type and possible crud fields like value['create'] and value['update']
    These optional values indicate if a field is required
    :param crud:
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :return:
    """
    graphene_type = R.prop_or(None, 'type', value)
    if not graphene_type:
        raise Exception("No type parameter found on the field value. This usually means that a field was defined in the"
                        " field_dict that has no corresponding django field. To define a field with no corresponding"
                        " Django field, you must give the field a type parameter that is set to a GraphneType subclass")
    graphene_type_modifier = R.prop_or(None, 'type_modifier', value)
    if inspect.isclass(graphene_type) and issubclass(graphene_type, (ObjectType)):
        # Geometry and ObjectTypes must be converted to a dynamic InputTypeVersion
        fields = R.prop('fields', value)
        resolved_graphene_type = input_type_class(dict(graphene_type=graphene_type, fields=fields), crud,
                                                  parent_type_classes)
    else:
        # If a lambda is returned we have an InputType subclass that needs to know the crud type
        resolved_graphene_type = graphene_type(crud) if R.isfunction(graphene_type) else graphene_type

    # Instantiate using the type_modifier function if we need to wrap this in a List,
    # Otherwise instantiate and pass the required flat
    return graphene_type_modifier(resolved_graphene_type) if \
        graphene_type_modifier else \
        resolved_graphene_type(
            # Add required depending on whether this is an insert or update
            # This means if a user omits these fields an error will occur
            required=R.prop_eq_or_in_or(False, crud, REQUIRE, value)
        )


def input_type_fields(fields_dict, crud, parent_type_classes=[]):
    """
    :param fields_dict: The fields_dict for the Django model
    :param crud: INSERT, UPDATE, or DELETE. If None the type is guessed
    :param parent_type_classes: String array of parent graphene types for dynamic class naming
    :return:
    """
    crud = crud or guess_update_or_create(fields_dict)
    return R.map_dict(
        lambda value: instantiate_graphene_type(value, parent_type_classes, crud),
        # Filter out values that are deny
        # This means that if the user tries to pass these fields to graphql an error will occur
        R.filter_dict(
            lambda key_value: R.not_func(R.prop_eq_or(False, crud, DENY, key_value[1])),
            fields_dict
        )
    )


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
    # Example region = {id: 5} becomes region_id = 5
    # This assumes id is the pk
    key_to_modified_key_and_value = R.map_with_obj(
        lambda key, value: {'%s_id' % key: R.prop('id', value)} if
        R.prop_or(False, 'django_type', fields_dict[key]) else
        # No Change
        {key: value},
        field_name_to_value
    )

    def key_value_based_on_unique_or_foreign(key):
        """
            Returns either a simple dict(key=value) for keys that must have unique values (e.g. id, key, OneToOne rel)
            Returns dict(default=dict(key=value)) for keys that need not have unique values
        :param {String} key:
        :return {dict}:
        """
        modified_key_value = key_to_modified_key_and_value[key]
        # non-defaults are for checking uniqueness and then using for update/insert
        # defaults are for updating/inserting
        # this matches Django Query's update_or_create
        return modified_key_value \
            if R.length(R.item_path_or([], [key, 'unique'], fields_dict)) \
            else dict(defaults=modified_key_value)

    # Forms a dict(
    #   unique_key1=value, unique_key2=value, ...,
    #   defaults=(non_unique_key1=value, non_unique_key2=value, ...)
    # )
    return R.merge_deep_all(R.map_with_obj_to_values(
        lambda key, value: key_value_based_on_unique_or_foreign(key),
        field_name_to_value
    ))


@R.curry
def graphql_query(query_name, fields):
    """
        Creates a query based on the name and given fields
    :param query_name:
    :param fields:
    :returns A lambda that expects a Graphene client, optional variable_definitions, and **kwargs that contain kwargs
    for the client.execute call, such as any of
        context_value={'user': 'Peter'},  root_value={'user': 'Peter'}, variable_value={'user': 'Peter'}
        variable_definitions, if specified should match the query form: e.g. dict(id='String') where the key
        is the field and the value is the type. This results in query whatever(id: String!) { query_name(id: id) ... }
    """

    def form_query(client, variable_definitions={}, field_overrides={}, **kwargs):
        """
        # Make definitions in the form id: String!, foo: Int!, etc
        :param client:
        :param variable_definitions:
        :param field_overrides: Override the fields argument with limited fields in the same format as fields above
        :return:
        """
        formatted_definitions = R.join(
            ', ',
            R.values(
                R.map_with_obj(
                    lambda key, value: '$%s: %s!' % (key, value),
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

        logger.debug('Query: %s\nKwargs: %s' % (query, kwargs))
        return client.execute(query, **kwargs)

    return form_query


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
        # The return query dump, which are all the fields available. One catch is we need to add the id,
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
    :return: A flat list of key values representing the value dict, including resolved deep values
    """
    return R.chain(R.identity, R.map_with_obj_to_values(lambda key, inner_value: process_query_kwarg(model, key, inner_value), value_dict))


def process_query_kwarg(model, key, value):
    """
        Process a query kwarg. The key is always a string and the value can be a scalar or a dict representing the
        model given by model. E.g. model: User, key: 'user', value: {id: 1, username: 'jo'} or
        model User, key: 'user', value: {id: 1, group: {id: 2}}
        TODO I haven't made this work with ManyToMany yet, such as
        model User, key: 'user', value: {id: 1, groups: [{id: 2}, {name: 'fellas'}]}. This requires using __in
        for the django key and other fancy stuff
    :param model:
    :param key:
    :param value:
    :return: Flat list of pairs, where first value of pairs is a django query string like 'foo__car' or 'foo__contains'
     and second is value like 2
    """
    if isinstance(model._meta._forward_fields_map[key], (JSONField)):
        # JSONField's need to change the key to __contains
        return [['%s__contains' % key, value]]
    elif isinstance(model._meta._forward_fields_map[key], (ForeignKey, OneToOneField)):
        # Recurse on these, so foo: {bar: 1, car: 2} resolves to [['foo__bar' 1], ['foo__car', 2]]
        related_model = model._meta._forward_fields_map[key].related_model
        key_values = process_query_value(related_model, value)
        return R.map(lambda inner_key_value: ['%s__%s' % (key, inner_key_value[0]), inner_key_value[1]], key_values)
    elif isinstance(model._meta._forward_fields_map[key], (ManyToManyField)):
        raise NotImplementedError("TODO need to implement stringify for ManyToMany")


    return [[key, value]]


def stringify_query_kwargs(model, kwargs):
    """
        Small correction here to change the data filter to data__contains to handle any json
        https://docs.djangoproject.com/en/2.0/ref/contrib/postgres/fields/#std:fieldlookup-hstorefield.contains
        This also handles resovling relationships like {user: {id: 1, group: {id: 2}}} in the kwargs by converting them
        to user__id==1 and user__group__id==2
        TODO it doesn't handle many-to-many yet. I need to write that
    :param data_field_name: The name of the data field, e.g. 'data'
    :param kwargs: The query kargs
    :return: {dict} The corrected kwargs
    """
    # Since each process-query_kwargs returns an array of one or more pairs (due to potential recursion), we have
    # to take the values of R.map_with_obj and then flatten those values together and finally convert them from pairs to a dict
    return R.from_pairs(R.flatten(R.values(R.map_with_obj(lambda key, value: process_query_kwarg(model, key, value), kwargs))))

