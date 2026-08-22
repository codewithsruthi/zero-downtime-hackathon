from hydra.primitives.p1_escalate import EscalateAcquisition
from hydra.primitives.p2_resynthesize import ResynthesizeExtractor
from hydra.primitives.p3_schema import RelaxOrEvolveSchema
from hydra.primitives.p4_quarantine import QuarantineAndPartialCommit
from hydra.primitives.p5_replay import ReplayFromRaw
from hydra.primitives.p6_backoff import BackoffAndReschedule
from hydra.primitives.p7_failover import FailoverSource
from hydra.primitives.p8_escalate_human import OpenCircuitAndEscalate


def build_primitives() -> dict:
    items = [
        EscalateAcquisition(),
        ResynthesizeExtractor(),
        RelaxOrEvolveSchema(),
        QuarantineAndPartialCommit(),
        ReplayFromRaw(),
        BackoffAndReschedule(),
        FailoverSource(),
        OpenCircuitAndEscalate(),
    ]
    return {p.id: p for p in items}
