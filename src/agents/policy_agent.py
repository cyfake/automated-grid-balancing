"""
Policy agent: returns hard constraints and optimization weights.
"""
from ..schemas.models import PolicyConfig


def default_policy() -> PolicyConfig:
    return PolicyConfig(
        unserved_penalty=1000.0,
        curtailment_penalty=1.0,
        fuel_penalty=10.0,
        min_soc_fraction=0.10,
        soc_reserve_evening_fraction=0.40,
        evening_peak_start=17,
        evening_peak_end=21,
    )
