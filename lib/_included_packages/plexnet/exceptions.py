class BadRequest(Exception):
    pass


class RateLimited(BadRequest):
    def __init__(self, retry_after=60, from_cooldown=False):
        self.retry_after = retry_after
        self.from_cooldown = from_cooldown
        super(RateLimited, self).__init__('(429) too_many_requests; retry after {0}s'.format(retry_after))


class NotFound(Exception):
    pass


class UnknownType(Exception):
    pass


class Unsupported(Exception):
    pass


class Unauthorized(Exception):
    pass


class ServerNotOwned(Exception):
    pass


class UserSwitchForbiddenException(Exception):
    pass
