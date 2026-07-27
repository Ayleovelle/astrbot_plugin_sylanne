"""Global-workspace competition and broadcast (design section 10)."""

from .competition import (
    ProposalArbiterV1,
    arbitrate,
    build_proposals,
    proposal_salience,
    run_workspace,
)
from .models import WorkspaceBroadcast, WorkspaceProposal

__all__ = [
    "ProposalArbiterV1",
    "WorkspaceBroadcast",
    "WorkspaceProposal",
    "arbitrate",
    "build_proposals",
    "proposal_salience",
    "run_workspace",
]
