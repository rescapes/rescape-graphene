from django.db.models import Q
from rescape_python_helpers import ramda as R


def default_strategy(matches, prop_value, i):
    return '%s%s' % (prop_value, i + 1)

@R.curry
def increment_prop_until_unique(django_class, strategy, prop, django_instance_data):
    """
        Increments the given prop of the given django as given by data['prop'] until it matches nothing in
        the database
    :param django_class: Django class to query
    :param prop: The prop to ensure uniqueness
    :param strategy: function to try to make a value unique. Expects all potential matching values (all values
    that begin with the value of the property), the prop value, and the current index. It's called for each matching
    value to guarentee the strategy will eventually get a unique value. For instance, if prop is key and it equals
    'foo', and 'foo', 'foo1', 'foo2', and 'foo3' are in the db, strategy will be called with an array of 4 values 4
    times, with index 0 through 3. If strategy is None the default strategy is to append index+1 to the duplicate name
    :param django_instance_data: The data containing the prop
    :return: The data merged with the uniquely named prop
    """
    prop_value = R.prop(prop, django_instance_data)
    pk = R.prop_or(None, 'id', django_instance_data)

    strategy = strategy or default_strategy
    matching_values = django_class.objects.filter(
        # Ignore value matching the pk if this is an update operation.
        # In other words we can update the key to what it already is, aka do nothing
        *R.compact([
            ~Q(id=pk) if pk else None,
        ]),
        **{'%s__startswith' % prop: prop_value}
    ).values_list(prop, flat=True)

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
    :return: The modified django_instance_data for any property that needs to have a unique value
    """

    # If any prop needs to be unique then run its unique_with function, which updates it to a unique value
    # By querying the database for duplicate. This is mainly for non-pk fields like a key
    return R.reduce(
        lambda reduced, prop_value: prop_value['unique_with'](reduced) if
        R.prop_or(False, 'unique_with', prop_value) else
        reduced,
        django_instance_data,
        R.values(property_fields)
    )