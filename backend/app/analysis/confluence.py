from __future__ import annotations

from datetime import datetime

from app.schemas.market import ConfirmationStage, DataStatus, TimeframeEvidence, TopDownValidation


def validate_top_down(evidence: list[TimeframeEvidence], *, observed_at: datetime, risk_clear: bool) -> TopDownValidation:
    """Separate required top-down evidence from optional timing; no probability or order authority."""
    by_frame = {item.timeframe: item for item in evidence}
    h4 = by_frame.get("H4")
    structure = h4.structure if h4 and h4.data_status == DataStatus.LIVE else "UNAVAILABLE"
    direction = {"UPWARD_STRUCTURE": "LONG_CONTEXT", "DOWNWARD_STRUCTURE": "SHORT_CONTEXT"}.get(structure, "NONE")
    stages: list[ConfirmationStage] = []
    for name, frames in (("BIAS", ["D1", "H4"]), ("INTRADAY", ["H1"]), ("SETUP", ["M15"]), ("TRIGGER", ["M5"]), ("TIMING", ["M1"])):
        items = [by_frame.get(frame) for frame in frames]
        available = all(item and item.data_status == DataStatus.LIVE and item.source_timestamp_utc and item.source_timestamp_utc <= observed_at for item in items)
        aligned = direction != "NONE" and all(item and item.structure == structure for item in items)
        setup_known = name not in {"SETUP", "TRIGGER"} or all(
            item and item.setup_kind and item.setup_known_at_utc and item.setup_known_at_utc <= observed_at for item in items
        )
        state = "UNAVAILABLE" if not available else "REJECTED" if not aligned else "CONFIRMED" if setup_known else "PENDING"
        stages.append(ConfirmationStage(
            stage=name, state=state, timeframes=frames, required=name != "TIMING",
            evidence_timestamps={item.timeframe: item.source_timestamp_utc for item in items if item and item.source_timestamp_utc},
            invalidation_price=items[0].invalidation_price if items[0] and name in {"SETUP", "TRIGGER"} else None,
            reason_codes=[
                "COMPLETED_CANDLES_ONLY",
                "TIMEFRAME_SOURCE_UNAVAILABLE" if not available else "DIRECTION_CONFLICT" if not aligned else "CONFIRMED_CLOSE_SETUP" if setup_known else "AWAITING_COMPLETED_SETUP",
                *(["OPTIONAL_TIMING_CANNOT_OVERRIDE_HIGHER_TIMEFRAMES"] if name == "TIMING" else []),
            ],
        ))
    stages.append(ConfirmationStage(stage="RISK", state="CONFIRMED" if risk_clear else "REJECTED", reason_codes=["EXISTING_SOURCE_AND_RISK_GATES"]))
    required = [stage for stage in stages if stage.required]
    state = next((value for value in ("UNAVAILABLE", "REJECTED", "PENDING") if any(stage.state == value for stage in required)), "CONFIRMED")
    return TopDownValidation(state=state, direction=direction, observed_at_utc=observed_at, stages=stages, timeframes=evidence)
