import graphene
from graphene_django import DjangoObjectType
from graphene import DateTime, Int

from rescape_graphene.graphql_helpers.schema_helpers import DENY


class DjangoObjectTypeRevisionedMixin(object):
    """
        Mixin for graphene classes so our Graphene class knows about the RevisionModelMixin properties
    """
    created_at = graphene.DateTime(source='created_at')
    updated_at = graphene.DateTime(source='updated_at')
    version_number = graphene.Int(source='version_number')
    revision_id = graphene.Int(source='revision_id')


# RevisionModelMixin properties with restrictions on CREATE and UPDATE
# These prevent letting us create mutations that process any of these properties
reversion_types = dict(
    created_at=dict(create=DENY, update=DENY, type=DateTime),
    updated_at=dict(create=DENY, update=DENY, type=DateTime),
    version_number=dict(create=DENY, update=DENY, type=Int),
    revision_id=dict(create=DENY, update=DENY, type=Int)
)

# Deleted is for the SafeDeleteModel mixin and the others correspond to the RevisionModelMixin properties
# Note that deleted is a model field so doesn't need a type. The properties do
reversion_and_safe_delete_types = dict(
    deleted={},
    **reversion_types
)
