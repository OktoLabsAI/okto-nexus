"""One coherent operational observation envelope; not a fixed R3 criterion.

All four retained requests are still read: CLOSED does not prove immutable
journal snapshots. No polling interval guarantees a hard billed-token ceiling.
"""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ObservationLimits:
    max_requests:int=4
    snapshot_seconds:float=1.0
    initialization_seconds:float=2.0
    persistence_margin_seconds:float=1.0
    target_start_seconds:float=.2

    def __post_init__(self):
        if type(self.max_requests) is not int or not 1<=self.max_requests<=4:
            raise ValueError('FINITE_REQUEST_LIMIT_REQUIRED')
        if not all(type(value) in (int,float) and math.isfinite(value) and value>0 for value in
                   (self.snapshot_seconds,self.initialization_seconds,self.persistence_margin_seconds,self.target_start_seconds)):
            raise ValueError('POSITIVE_FINITE_BOUNDS_REQUIRED')

    @property
    def poll_seconds(self):
        # Canonical + Core per request, one new Core connection in a serial
        # admission, and a shared margin for accounting/persistence.
        return self.max_requests*2*self.snapshot_seconds+self.initialization_seconds+self.persistence_margin_seconds

    @property
    def freshness_seconds(self):return self.poll_seconds+1.0

    @property
    def cadence_seconds(self):return self.poll_seconds+5.0

LIMITS=ObservationLimits()
