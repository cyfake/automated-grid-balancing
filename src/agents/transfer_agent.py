"""
Transfer agent: defines fully connected 3-state topology with capacities.
"""
from typing import List

from ..schemas.models import TransferLink, TransferTopology


# Default transfer capacities (MW) — symmetric for MVP
DEFAULT_CAPACITIES = {
    ("CA", "TX"): 2000,
    ("CA", "NY"): 1500,
    ("TX", "NY"): 2500,
}


def build_topology(states: List[str], capacities: dict = None) -> TransferTopology:
    """
    Build a fully connected transfer topology for the given states.
    capacities: optional {(from, to): mw} overrides. Both directions created.
    """
    if capacities is None:
        capacities = DEFAULT_CAPACITIES

    links = []
    for (a, b), cap in capacities.items():
        links.append(TransferLink(from_state=a, to_state=b, capacity_mw=cap))
        links.append(TransferLink(from_state=b, to_state=a, capacity_mw=cap))

    return TransferTopology(links=links)
