from operator import itemgetter

import graphene
from graphene import Int, ObjectType, List, Field
from graphene_django import DjangoObjectType
from rescape_python_helpers import ramda as R
from reversion.models import Version, Revision

from rescape_graphene.graphql_helpers.schema_helpers import DENY, merge_with_django_properties, \
    top_level_allowed_filter_arguments
from rescape_graphene.schema_models.user_schema import UserType, user_fields


def get_versioner(single_object_qs, versions_type, **kwargs):
    """

    Cre
    First we create a little helper function, becase we will potentially have many PaginatedTypes
    and we will potentially want to turn many querysets into paginated results:
    :param single_object_qs: The queryset that must return exactly one instance
    :param versions_type Class created by create_versions_type to hold all the versions of one model instance
    :param kwargs: Addition kwargs to versioned_type, usually not needed
    :return:
    """

    instance = R.head(single_object_qs)
    versions = Version.objects.get_for_object(instance)

    return versions_type(
        objects=list(versions),  # R.map(lambda version: version._object_version.object, list(versions)),
        **kwargs
    )


class RevisionType(DjangoObjectType):
    id = graphene.Int(source='pk')

    class Meta:
        model = Revision


# Merge the Revision Django properties with our field config
# Revision is managed by django-reversion and can never be updated from the API
revision_fields = merge_with_django_properties(RevisionType, dict(
    id=dict(create=DENY, update=DENY),
    date_created=dict(create=DENY, update=DENY),
    # This is a Foreign Key. Graphene generates these relationships for us, but we need it here to
    # support our Mutation subclasses and query_argument generation
    user=dict(graphene_type=UserType, fields=user_fields, create=DENY, update=DENY),
    comment=dict(create=DENY, update=DENY)
))


class VersionType(DjangoObjectType):
    id = graphene.Int(source='pk')

    class Meta:
        model = Version


def create_version_type(model_object_type, model_object_type_fields):
    # We can't assign Version as the Meta model because multiple classes would point at the same model,
    # which probably isn't allowed

    def resolve_instance(parent, info, **kwargs):
        instance = parent._object_version.object
        # Inject the version so RevisionModelMixin knows how to handle
        instance._version = parent
        return instance

    version_type_model = type(
        f'VersionTypeModelFor{model_object_type.__name__}',
        (ObjectType,),
        dict(
            id=Int(),
            revision=Field(RevisionType),
            instance=Field(model_object_type, resolver=resolve_instance)
        )
    )

    # Merge the Revision Django properties with our field config
    versioned_fields = merge_with_django_properties(VersionType, dict(
        # Revision
        revision=dict(
            type=RevisionType,
            graphene_type=RevisionType,
            fields=revision_fields,
            type_modifier=lambda *type_and_args: Field(*type_and_args)
        ),
        instance=dict(
            type=model_object_type,
            graphene_type=model_object_type,
            fields=model_object_type_fields,
            type_modifier=lambda *type_and_args: Field(*type_and_args)
        )
    ))
    return dict(type=version_type_model, fields=versioned_fields)


def create_version_container_type(model_object_type, model_object_type_fields):
    """
        DjangObjectType and fields to hold all the versions of one instance
    :param model_object_type:
    :param model_object_type_fields:
    :return:
    """

    (version_type, version_type_fields) = itemgetter('type', 'fields')(
        create_version_type(model_object_type, model_object_type_fields)
    )

    versions_type_model = type(
        f'VersionContainerTypeModelFor{model_object_type.__name__}',
        (ObjectType,),
        dict(
            objects=List(version_type)
        )
    )

    # Merge the Revision Django properties with our field config
    versions_fields = merge_with_django_properties(VersionType, dict(
        # Versions
        objects=dict(
            type=version_type,
            graphene_type=version_type,
            fields=version_type_fields,
            type_modifier=lambda *type_and_args: List(*type_and_args)
        )
    ))
    return dict(type=versions_type_model, fields=versions_fields)


def resolve_version_instance(model_versioned_type, resolver, **kwargs):
    """
        Queries for the version instance by for the given model type using the given resolver
        The kwargs must contain objects: [{id: the id}]
    :param model_versioned_type: Graphene model class created by create_version_container_type
    :param resolver: Resolver for the model
    :param kwargs: Must contain objects: [{id: the id}] to resolve the versions of the instance given by id
    :return:
    """
    # We technically receive an array but never accept more than the first item
    obj = R.head(R.prop('objects', kwargs))
    if not R.item_str_path_or(None, 'instance.id', obj):
        raise Exception(
            f"id required in kwargs.objects.instance for revisions query, but got: {kwargs}")

    # Create the filter that only returns 1 location
    objs = resolver('filter', **R.prop_or({}, 'instance', obj)).order_by('id')
    return get_versioner(
        objs,
        model_versioned_type,
    )

def versioning_allowed_filter_arguments(fields, graphene_type):
    """
        TODO no longer needed. version props filter props are filtered out in schema_helpers
       top_level_allowed_filter_arguments for versioned types so we don't add filters to the top-level
       props like revisionContains. We don't (currenlty) want a filter like revisionContains
    :param fields:
    :param graphene_type:
    :return:
    """
    return top_level_allowed_filter_arguments(fields, graphene_type)
