class EKGError(Exception):
    """Base error for the EKG client."""


class EKGConnectionError(EKGError):
    """The kettle could not be reached or returned an HTTP error."""


class EKGCommandError(EKGError):
    """The kettle rejected a CLI command (e.g. 'cannot find command')."""
