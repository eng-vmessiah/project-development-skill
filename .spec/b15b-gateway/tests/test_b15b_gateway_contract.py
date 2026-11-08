"""Live contract guard for b15b-gateway.

The live seam was removed by a host update, so the feature's honest status is
NOT_READY_HERMES_SEAM. This test protects the artifacts that still define the
slice: the replayable patch series and the four gateway public surfaces.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from pd_fleet import gateway_auth, gateway_deny, gateway_redaction, gateway_subscription  # noqa: E402


def test_gateway_public_surfaces_are_importable_and_present():
    assert hasattr(gateway_auth, "GatewayAuth")
    assert hasattr(gateway_auth, "SingleWriterTicketStore")
    assert hasattr(gateway_deny, "evaluate_gates")
    assert hasattr(gateway_redaction, "validate_event")
    assert hasattr(gateway_subscription, "GatewaySubscriptionStore")


def test_replayable_seam_series_is_kept_and_status_stays_honest():
    series = REPO / "patches" / "b15b-seam"
    readme = series / "README.md"
    assert readme.is_file()
    assert sorted(series.glob("*.patch")), "B15b.1 replayable series is missing"
    assert "dc50153faf" in readme.read_text(encoding="utf-8")

    verification = (REPO / ".spec/b15b-gateway/VERIFICATION.md").read_text(encoding="utf-8")
    assert "NOT_READY_HERMES_SEAM" in verification
    assert "seam removida pelo update do host" in verification
