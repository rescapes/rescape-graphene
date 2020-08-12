import inspect
import uuid

from django.db.models import Q
from rescape_python_helpers import ramda as R


def default_strategy(matches, prop_value, i):
    return '%s%s' % (prop_value, str(uuid.uuid1())[0:10])


@R.curry
def increment_prop_until_unique(django_class, strategy, prop, additional_filter_props, django_instance_data):
    """
        Increments the given prop of the given django as given by data['prop'] until it matches nothing in
        the database. Note that this includes checks against soft deleted instances where the deleted prop is non-null
        (assumes the use of SafeDeleteModel on the model class)
    :param django_class: Django class to query
    :param prop: The prop to ensure uniqueness
    :param additional_filter_props: Other props, such as user id, to filter by. This allows incrementing a name
    dependent on the current user, for instance. This can be a dict or a function expecting the django_instance_data
    and returning a dict
    :param strategy: function to try to make a value unique. Expects all potential matching values--all values
    that begin with the value of the property--the prop value, and the current index. It's called for each matching
    value to guarentee the strategy will eventually get a unique value. For instance, if prop is key and it equals
    'foo', and 'foo', 'foo1', 'foo2', and 'foo3' are in the db, strategy will be called with an array of 4 values 4
    times, with index 0 through 3. If strategy is None the default strategy is to append index+1 to the duplicate name
    :param django_instance_data: The data containing the prop
    :return: The data merged with the uniquely named prop
    """
    prop_value = R.prop(prop, django_instance_data)
    pk = R.prop_or(None, 'id', django_instance_data)

    strategy = strategy or default_strategy
    # Include deleted objects here. It's up to additional_filter_props to deal with the deleted=date|None property
    all_objects = django_class.all_objects if R.has('all_objects', django_class) else django_class.objects
    matching_values = all_objects.filter(
        # Ignore value matching the pk if this is an update operation.
        # In other words we can update the key to what it already is, aka do nothing
        *R.compact([
            ~Q(id=pk) if pk else None,
        ]),
        **R.merge(
            {'%s__startswith' % prop: prop_value},
            # Give the filter props the instance f they are a function
            R.when(
                lambda f: inspect.isfunction(f),
                lambda f: f(django_instance_data)
            )(additional_filter_props or {})
        )
    ).values_list(prop, flat=True).order_by(prop)

    success = prop_value
    for i, matching_key in enumerate(matching_values):
        success = None
        attempt = strategy(matching_values, prop_value, i)
        if attempt not in matching_values:
            success = attempt
            break
    if not success:
        raise Exception("Could not generate unique prop value %s. The following matching ones exist %s" % (
            prop_value, matching_values))
    return R.merge(django_instance_data, {prop: success})


def enforce_unique_props(property_fields, django_instance_data):
    """
        Called in the mutate function of the Graphene Type class. Ensures that all properties marked
        as unique_with
    :param property_fields: The Graphene Type property fields dict. This is checked for unique_with,
    which when present points at a function that expects the django_instance_data and returns the django_instance_data
    modified so that the property in question has a unique value.
    :param django_instance_data: dict of an instance to be created or updated
    :param for_update if True this is for an update mutation so props are not required
    :return: The modified django_instance_data for any property that needs to have a unique value
    """

    # If any prop needs to be unique then run its unique_with function, which updates it to a unique value
    # By querying the database for duplicate. This is mainly for non-pk fields like a key
    return R.reduce(
        lambda reduced, prop_field_tup: prop_field_tup[1]['unique_with'](reduced) if
        R.has(prop_field_tup[0], reduced) and R.prop_or(False, 'unique_with', prop_field_tup[1]) else
        reduced,
        django_instance_data,
        property_fields.items()
    )
