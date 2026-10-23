class DomainError(Exception):
    pass

class ConflictError(DomainError):
    pass

class NotFoundError(DomainError):
    pass
