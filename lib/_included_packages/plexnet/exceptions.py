class BadRequest(Exception):
    pass


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
