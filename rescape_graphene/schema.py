from graphene import Schema
from rescape_python_helpers import ramda as R

from rescape_graphene.schema_models.token_schema import RescapeTokenMutation, RescapeTokenQuery
from rescape_graphene.schema_models.user_schema import UserQuery, UserMutation


def create_query_mutation_schema(class_config):
    """
        Creates a schema from defaults or allows overrides of any of these schemas
        Each arg if overridden must provide a dict with a query and mutation key, each pointing to the
        override query and mutation graphene.ObjectType
        :param class_config
        :param class_config.user_group: Handles User and Group queries and mutations (defined in rescape_graphene)
        :param class_config.user_group_state: Handles UserState and GroupState queries and mutations. See the default UserState
        and GroupState for an example
        :param class_config.region: Handles Region queries and mutations. See the default Region for an example
        :param class_config.project: Handles Project queries and mutations. See the default Project for an example
        :param class_config.location: Handles Location queries and mutations. See the default Location for an example
        :return:
    """

    obj = create_query_and_mutation_classes(class_config)
    schema = Schema(query=R.prop('query', obj), mutation=R.prop('mutation', obj))
    return dict(query=R.prop('query', obj), mutation=R.prop('mutation', obj), schema=schema)


def create_schema(class_config):
    return R.prop('schema', create_query_mutation_schema(class_config))

def create_query_and_mutation_classes(query_and_mutation_class_lookups):
    """
        Creates a Query class and Mutation classs from defaults or allows overrides of any of these schemas
        Each arg if overriden must provide a dict with a query and mutation key, each pointing to the
        override query and mutation graphene.ObjectType
    :param class_config: Handles User and Group queries and mutations (defined in rescape_graphene)
    :param class_config.region: Handles Region queries and mutations. See the default Region for an example
    :param class_config.project: Handles Project queries and mutations. See the default Project for an example
    :param class_config.location: Handles Location queries and mutations. See the default Location for an example
    :return: A dict with query and mutation for the two dynamic classes
    """

    class Query(
        UserQuery,
        RescapeTokenQuery,
        *R.map_with_obj_to_values(
            lambda k, v: R.prop('query', v), query_and_mutation_class_lookups
        )
    ):
        pass

    class Mutation(
        UserMutation,
        RescapeTokenMutation,
        *R.map_with_obj_to_values(
            lambda k, v: R.prop('mutation', v), query_and_mutation_class_lookups
        )
    ):
        pass

    return dict(query=Query, mutation=Mutation)
