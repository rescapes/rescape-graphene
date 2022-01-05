from json import dumps

from django.db.models import ForeignKey
from django.utils.timezone import now
from rescape_python_helpers import ramda as R, compact


def find_scope_instances_by_id(model, scope_ids):
    return model.objects.all_with_deleted().filter(id__in=scope_ids)


def find_scope_instances(user_state_scope, new_data):
    """
        Retrieve the scope instances to verify the Ids.
        Scope instances must have ids unless they are allowed to be created/updated
        during the userState mutation (such as searchLocations)
    :param new_data: The data to search
    :param user_state_scope Dict with 'pick' in the shape of the instances we are looking for in new_data,
    e.g. dict(userRegions={region: True}) to search new_data.userRegions[] for all occurrences of {region:...}
     and 'key' which indicates the actually key of the instance (e.g. 'region' for regions)
    :return: dict(
        instances=Instances actually in the database,
    )
    """

    def until(key, value):
        return key != R.prop('key', user_state_scope)

    return R.compose(
        lambda scope_dict: dict(
            # See which instances with ids are actually in the database
            # If any are missing we have an invalid update or need to create those instances if permitted
            instances=list(
                find_scope_instances_by_id(R.prop('model', user_state_scope), scope_dict['scope_ids'])
            ),
            # The path from userRegions or userProjects to the scope instances, used to replace
            # a null update value with the existing values
            user_scope_path=list(R.keys(R.flatten_dct(user_state_scope, '.')))[0],
            **scope_dict
        ),
        lambda scope_objs: dict(
            # Unique by id or accept if there is no id, this loses data, but it's just for validation
            scope_objs=R.unique_by(lambda obj: R.prop_or(str(now()), 'id', obj['value']), scope_objs),
            scope_ids=R.unique_by(
                R.identity,
                compact(
                    R.map(
                        lambda scope_obj: R.prop_or(None, 'id', scope_obj['value']), scope_objs
                    )
                )
            )
        ),
        # Use the pick key property to find the scope instances in the data
        # If we don't match anything we can get null or an empty item. Filter/compact these out
        R.filter(
            lambda obj: obj['value'] and (not isinstance(obj['value'], list) or R.length(obj['value']) != 0)
        ),
        R.map(
            lambda pair: dict(key=pair[0], value=pair[1])
        ),
        lambda flattened_data: R.to_pairs(flattened_data),
        lambda data: R.flatten_dct_until(
            R.pick_deep_all_array_items(R.prop('pick', user_state_scope), data),
            until,
            '.'
        )
    )(new_data)


def validate_and_mutate_scope_instances(scope_instances_config, data):
    """
        Inspect the data and find all scope instances within data
        For UserState, for instance, this includes userRegions[*].region, userProject[*].project and within
        userRegions and userProjects userSearch.userSearchLocations[*].search_location and whatever the implementing
        libraries define in addition
    :param scope_instances_config: See user_state_schema.user_state_scope_instances_config for an example
    :param data: The instance data field containing the scope instances
    :return: The updated data with scope instances possibly created/updated if allowed. If creates occur
    then the scope instance will now have an id. Otherwise no changes are visible
    """

    validated_scope_objs_instances_and_ids_sets = R.map(
        lambda scope_instance_config: find_scope_instances(scope_instance_config, data),
        scope_instances_config
    )

    # Some scope instances can be created or modified when embedded in the data. This helps
    # make mutation of the instance, such as UserState,
    # a one step process, so that new Projects, SearchLocations, etc. can
    # be created without having to call mutation for them separately ahead of times, which would create
    # a series of mutations that weren't failure-protected as a single transaction
    for i, validated_scope_objs_instances_and_ids in enumerate(validated_scope_objs_instances_and_ids_sets):
        scope = R.merge(
            scope_instances_config[i],
            dict(model=scope_instances_config[i]['model'].__name__)
        )

        # If any scope instances with an id specified in new_data don't exist, throw an error
        if R.length(validated_scope_objs_instances_and_ids['scope_ids']) != R.length(
                validated_scope_objs_instances_and_ids['instances']):
            ids = R.join(', ', validated_scope_objs_instances_and_ids['scope_ids'])
            instances_string = R.join(', ', R.map(lambda instance: str(instance),
                                                  validated_scope_objs_instances_and_ids['instances']))
            raise Exception(
                f"For scope {dumps(scope)} Some scope ids among ids:[{ids}] being saved in user state do not exist. Found the following instances in the database: {instances_string or 'None'}. UserState.data is {dumps(data)}"
            )

        # Create/Update any scope instances that permit it
        model = scope_instances_config[i]['model']
        data = handle_can_mutate_related(
            model,
            scope,
            data,
            validated_scope_objs_instances_and_ids
        )
    return data



def handle_can_mutate_related(model, related_model_scope_config, data, validated_scope_objs_instances_and_ids):
    """
        Mutates the given related models of an instance if permitted
        See rescape-region's UserState for a working usage
    :param model: The related model
    :param related_model_scope_config: Configuration of the related model relative to the referencing instance
    :param data: The data containing thphee related models dicts to possibly mutate with
    :param validated_scope_objs_instances_and_ids: Config of the related objects that have been validated as
    existing in the database for objects not being created
    :return: Possibly mutates instances, returns data with newly created ids set
    """

    def make_fields_unique_if_needed(scope_obj):
        # If a field needs to be unique, like a key, call it's unique_with method
        R.map_with_obj(
            lambda key, value: R.item_str_path_or(R.identity, f'field_config.{key}.unique_with', related_model_scope_config)(scope_obj),
            scope_obj
        )

    def convert_foreign_key_to_id(scope_obj):
        # Find ForeignKey attributes and map the class field name to the foreign key id field
        # E.g. region to region_id, user to user_id, etc
        converters = R.compose(
            R.from_pairs,
            R.map(
                lambda field: [field.name, field.attname]
            ),
            R.filter(
                lambda field: R.isinstance(ForeignKey, field)
            )
        )(model._meta.fields)
        # Convert scopo_obj[related_field] = {id: x} to scope_obj[related_field_id] = x
        return R.from_pairs(
            R.map_with_obj_to_values(
                lambda key, value: [converters[key], R.prop('id', value)] if
                R.has(key, converters) else [key, value],
                scope_obj
            )
        )

    def omit_to_many(scope_obj):
        return R.omit(R.map(R.prop('attname'), model._meta.many_to_many), scope_obj)

    # This indicates that scope_objs were submitted that didn't have ids
    # This is allowed if those scope_objs can be created/updated when the userState is mutated
    if R.prop_or(False, 'can_mutate_related', related_model_scope_config):
        for scope_obj_key_value in validated_scope_objs_instances_and_ids['scope_objs']:

            scope_obj = scope_obj_key_value['value']
            scope_obj_path = scope_obj_key_value['key']
            if R.length(R.keys(R.omit(['id'], scope_obj))):
                modified_scope_obj = R.compose(
                    convert_foreign_key_to_id,
                    omit_to_many,
                    make_fields_unique_if_needed
                )(scope_obj)
                if R.prop_or(False, 'id', scope_obj):
                    # Update, we don't need the result since it's already in user_state.data
                    instance, created = model.objects.update_or_create(
                        defaults=R.omit(['id'], modified_scope_obj),
                        **R.pick(['id'], scope_obj)
                    )
                else:
                    # Create
                    instance = model(**modified_scope_obj)
                    instance.save()
                    # We need to replace the object
                    # passed in with an object containing the id of the instance
                    data = R.fake_lens_path_set(
                        scope_obj_path.split('.'),
                        R.pick(['id'], instance),
                        data
                    )

                for to_many in model._meta.many_to_many:
                    if to_many.attname in R.keys(scope_obj):
                        # Set existing related values to the created/updated instances
                        getattr(instance, to_many.attname).set(R.map(R.prop('id'), scope_obj[to_many.attname]))
    return data
