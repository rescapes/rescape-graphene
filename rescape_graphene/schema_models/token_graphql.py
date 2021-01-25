
# The following are just for testing. There is not backing class for authentication
# so we just for mutations manually

def graphql_token_auth_mutation(client, variables):
    """
        Executes an authentication with a username and password as variables
    :param client:
    :param variables:
    :return:
    """
    return client.execute('''
mutation tokenAuthMutation($username: String!, $password: String!) {
  tokenAuth(username: $username, password: $password) {
    token
  }
}''', variables=variables)

def graphql_verify_token_mutation(client, variables):
    """
        Verifies an authentication with token
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation verifyTokenMutation($token: String!) {
  verifyToken(token: $token) {
    payload
  }
}''', variables=variables)

def graphql_refresh_token_mutation(client, variables):
    """
        Refreshes an auth token
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation refreshTokenMutation($token: String!) {
        refreshToken(token: $token) {
        token
    payload
    }
}''', variables=variables)

def graphql_delete_token_cookie_mutation(client, variables):
    """
        Deletes the user's cooke
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation deleteTokenCookieMutation {
        deleteTokenCookie {
            deleted
        }
    }''', variables=variables)

def graphql_delete_refresh_token_cookie_mutation(client, variables):
    """
        Deletes the user's cookie
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation deleteRefreshTokenCookieMutation {
        deleteRefreshTokenCookie {
            deleted
        }
    }''', variables=variables)
