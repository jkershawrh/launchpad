"""Namespace identity for event-reserved seats, separate from ordinary workshops."""

from collections.abc import Mapping

_PREFIX = "launchpad.redhat.com/"


def event_namespace_labels(metadata: Mapping[str, object]) -> dict[str, str]:
    """Return the complete event label triplet, or none for a non-event request.

    A reservation without its exact workshop and seat cannot be accounted for
    safely. Reject it before any namespace is created.
    """

    reservation = metadata.get("event_reservation_id")
    if reservation is None:
        return {}
    values = {
        "event-reservation-id": reservation,
        "workshop-id": metadata.get("workshop_id"),
        "seat-id": metadata.get("seat_id"),
    }
    if any(
        not isinstance(value, str) or not value or value.strip() != value
        for value in values.values()
    ):
        raise ValueError("event namespace identity requires reservation, workshop, and seat IDs")
    return {_PREFIX + key: value for key, value in values.items()}
