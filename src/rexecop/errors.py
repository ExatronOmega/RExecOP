class RExecOpError(Exception):
    """Base error for RExecOp runtime failures."""


class RExecOpStateError(RExecOpError):
    """Invalid or disallowed operation state transition."""


class RExecOpValidationError(RExecOpError):
    """Contract or input validation failure."""


class RExecOpConcurrencyConflict(RExecOpError):
    """A compare-and-swap write lost a race with another runtime process."""

    code = "concurrency_conflict"
