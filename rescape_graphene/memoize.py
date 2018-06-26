import functools


def memoize(map_args=lambda args: args, map_kwargs=lambda kwargs: kwargs):
    def _memoize(func):
        """
            # https://medium.com/@nkhaja/memoization-and-decorators-with-python-32f607439f84
            Creates a memoize wrapper
            # @memoize
            # def fibonacci(n):
            #     if n == 0:return 0
            #     if n == 1:return 1
            #     else: return fib(n-1) + fib(n-2)
        :param func:
        :param filter_args: Function to filter args. This lets us filter
        things our args that can't be reliable cached, like functions
        :param filter_kwargs: Function to filter kwargs. This lets us filter
        things our kwargs that can't be reliable cached, like functions
        :return:
        """
        cache = func.cache = {}
        @functools.wraps(func)
        def memoized_func(*base_args, **base_kwargs):
            args = map_args(base_args)
            kwargs = map_kwargs(base_kwargs)
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = func(*base_args, **base_kwargs)
            return cache[key]
        return memoized_func

    return _memoize


