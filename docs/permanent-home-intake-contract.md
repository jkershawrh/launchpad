# Permanent-home intake gate (LP-T182)

This is the **offline prerequisite contract** for a candidate Launchpad control-plane home. It is not a cluster probe, clean-install certification, restore drill, migration approval, or authorization to switch writers. No retained pilot lab is touched by running it.

Place a candidate `intake.json` beside an `evidence/` directory, then run:

```bash
.venv/bin/python scripts/validate_permanent_home_intake.py /path/to/candidate/intake.json
```

The command exits nonzero and emits only failed check identifiers if any prerequisite is missing, failed, lacks an owner or a local evidence artifact, uses a mutable release reference, or lacks sign-off. Submitted values are not echoed, so secret-bearing input cannot leak into its report. Evidence paths must stay inside the candidate directory and start with `evidence/`; do not put secret values in the intake or evidence.

The versioned input has this shape:

```json
{
  "schema": "launchpad.redhat.com/permanent-home-intake/v1",
  "target_id": "candidate-home",
  "release_digest": "sha256:<64 lowercase hex characters>",
  "checks": {
    "hardware": {"status": "pass", "owner": "platform-team", "evidence": ["evidence/hardware.json"]}
  },
  "decision": {"approved_by": "named-reviewer", "accepted_gaps": []}
}
```

The single illustrated check must be repeated for all 13 categories: `hardware`, `failure_domains`, `openshift`, `storage`, `registry`, `dns_tls`, `ingress_egress`, `identity`, `secrets`, `backup_restore`, `observability`, `ownership_support`, and `execution_connectivity`. Each category needs evidence appropriate to its claim. For example, backup evidence must show a successful restore, not merely a backup configuration. An accepted gap is recorded for human review but **never makes this gate green**.

`ready_for_bootstrap: true` means the intake is complete and signed for a **separate, controlled bootstrap decision**. The output always has `authorizes_cutover: false`. The later LP-T109–LP-T113 gates still require immutable deployment, recovery of database/identity/catalog/policy/evidence and cluster registry, in-flight reconciliation with stable `cluster_ref`, fencing of the old writer, edge cutover and rollback proof, and complete reclaim. Their live evidence, rather than this document or check, determines staging readiness.
