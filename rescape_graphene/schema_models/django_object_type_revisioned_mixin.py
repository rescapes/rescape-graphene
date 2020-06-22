import graphene
from graphene_django import DjangoObjectType
from graphene import DateTime, Int

# RevisionModelMixin properties
reversion_types = dict(
    deleted={},
    created_at=dict(type=DateTime),
    updated_at=dict(type=DateTime),
    version_number=dict(type=Int),
    revision_id=dict(type=Int)
)

# Deleted is for the SafeDeleteModel mixin and the others correspond to the RevisionModelMixin properties
# Note that deleted is a model field so doesn't need a type. The properties do
reversion_and_safe_delete_types = dict(
    deleted={},
    **reversion_types
)
