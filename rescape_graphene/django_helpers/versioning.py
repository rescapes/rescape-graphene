from operator import itemgetter
from rescape_python_helpers import ramda as R

import graphene
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from graphene import Int, Boolean, ObjectType, List, Field
from graphene_django import DjangoObjectType
from reversion.models import Version, Revision

from rescape_graphene import DENY, merge_with_django_properties


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
        objects=versions,
        **kwargs
    )


class RevisionType(DjangoObjectType):
    id = graphene.Int(source='pk')

    class Meta:
        model = Revision


class VersionType(DjangoObjectType):
    id = graphene.Int(source='pk')

    class Meta:
        model = Version


def create_revision_type_mixin(model_object_type, model_object_type_fields):
    """
        Constructs a RevisionedTypeMixin class and the fields object (for use in allowed filtering).
        The revision is for the given model_object_type and operates on one model instance at a time,
        showing all the versions of that instance
    :param model_object_type: E.g. LocationType
    :param model_object_type_fields: The fields of the model_object_type, e.g. location_fields
    :return: An object containing {type: The class, fields: The field}
    """

    # Subclass RevisionType for this Model
    revisioned_type_mixin = type(
        f'RevisionedTypeMixinFor{model_object_type.__name__}',
        (RevisionType,)
    )

    # Merge the Revision Django properties with our field config
    revisioned_fields = merge_with_django_properties(RevisionType, dict(
        date_created=dict(),
        user=dict(),
        comment=dict(),
    ))

    return dict(type=revisioned_type_mixin, fields=revisioned_fields)


def create_version_type(model_object_type, model_object_type_fields):
    # Subclass VersionType for this Model
    versioned_type_mixin = type(
        f'VersionedTypeMixinFor{model_object_type.__name__}',
        (VersionType,)
    )

    (revision_type, revision_type_fields) = itemgetter('type', 'fields')(
        create_revision_type_mixin(model_object_type, model_object_type_fields)
    )

    # Merge the Revision Django properties with our field config
    versioned_fields = merge_with_django_properties(VersionType, dict(
        # Revision
        revision=dict(
            type=revision_type,
            graphene_type=revision_type,
            fields=revision_type_fields,
            type_modifier=lambda *type_and_args: Field(*type_and_args)
        ),
        **model_object_type_fields
    ))
    return dict(type=versioned_type_mixin, fields=versioned_fields)


def create_versions_type(model_object_type, model_object_type_fields):
    """
        DjangObjectType and fields to hold all the versions of one instance
    :param model_object_type:
    :param model_object_type_fields:
    :return:
    """

    versions_type_mixin = type(
        f'VersionsTypeMixinFor{model_object_type.__name__}',
        (ObjectType,)
    )

    (version_type, version_type_fields) = itemgetter('type', 'fields')(
        create_version_type(model_object_type, model_object_type_fields)
    )

    # Merge the Revision Django properties with our field config
    versions_fields = merge_with_django_properties(VersionType, dict(
        # Versions
        objects=dict(
            type=version_type,
            graphene_type=version_type,
            fields=version_type_fields,
            type_modifier=lambda *type_and_args: List(*type_and_args)
        ),
        **model_object_type_fields
    ))
    return dict(type=versions_type_mixin, fields=versions_fields)
