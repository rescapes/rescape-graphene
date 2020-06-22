import graphene
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from graphene import InputObjectType
from graphene_django.types import DjangoObjectType
from rescape_python_helpers import ramda as R

from rescape_graphene.django_helpers.write_helpers import increment_prop_until_unique
from rescape_graphene.graphql_helpers.schema_helpers import input_type_fields, REQUIRE, DENY, CREATE, \
    merge_with_django_properties, input_type_parameters_for_update_or_create, UPDATE, \
    guess_update_or_create, graphql_update_or_create, graphql_query, update_or_create_with_revision
from rescape_graphene.schema_models.django_object_type_revisioned_mixin import reversion_types, \
    DjangoObjectTypeRevisionedMixin


class GroupType(DjangoObjectType, DjangoObjectTypeRevisionedMixin):
    class Meta:
        model = Group


group_fields = merge_with_django_properties(GroupType, dict(
    id=dict(create=DENY, update=[REQUIRE]),
    name=dict(create=[REQUIRE], unique_with=increment_prop_until_unique(Group, None, 'name', {})),
    **reversion_types
))

group_mutation_config = dict(
    class_name='Group',
    crud={
        CREATE: 'createGroup',
        UPDATE: 'updateGroup'
    },
    resolve=guess_update_or_create
)


class UpsertGroup(graphene.Mutation):
    """
        Abstract base class for mutation
    """
    group = graphene.Field(GroupType)

    def mutate(self, info, group_data=None):
        group_model = Group()
        data = R.merge(group_data, dict(password=make_password(R.prop('password', group_data), salt='not_random')) if
        R.prop_or(False, 'password', group_data) else
        {})
        update_or_create_values = input_type_parameters_for_update_or_create(group_fields, data)
        group, created = update_or_create_with_revision(group_model, update_or_create_values)
        return UpsertGroup(group=group)


class CreateGroup(UpsertGroup):
    """
        Create Group mutation class
    """

    class Arguments:
        group_data = type('CreateGroupInputType', (InputObjectType,),
                          input_type_fields(group_fields, CREATE, GroupType))(
            required=True)


class UpdateGroup(UpsertGroup):
    """
        Update Group mutation class
    """

    class Arguments:
        group_data = type('UpdateGroupInputType', (InputObjectType,),
                          input_type_fields(group_fields, UPDATE, GroupType))(
            required=True)


graphql_update_or_create_group = graphql_update_or_create(group_mutation_config, group_fields)
graphql_query_groups = graphql_query(GroupType, group_fields, 'groups')
