from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import copy
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from uuid import uuid4

from ops.testing.lifecycle_lot215.protocol import (
    ADMISSION_LIMIT,
    Closed,
    Conflict,
    Coordinator,
    FailurePoint,
    InjectedFailure,
    LabGuardError,
    LabContext,
    create_snapshot,
    initialize_lab,
    open_existing_lab,
    restore_snapshot,
    tamper_for_test,
)


def digest(label: str) -> str:
    import hashlib

    return hashlib.sha256(label.encode("ascii")).hexdigest()


class Lot215ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self._temporary.name).resolve()
        self.addCleanup(self._temporary.cleanup)
        self._previous_guard = os.environ.get("PHASE154L215_LAB")
        os.environ["PHASE154L215_LAB"] = "isolated"
        self.addCleanup(self._restore_guard)
        self.root = self.parent / "lab"
        self.witness_path = self.root / "witness" / "w.sqlite"
        self.primary_path = self.root / "primary" / "p.sqlite"
        self.context = initialize_lab(self.root, self.witness_path, self.primary_path)
        self.coordinator = Coordinator(self.context)
        self.addCleanup(self.coordinator.primary.close)
        self.addCleanup(self.coordinator.witness.close)

    def _restore_guard(self) -> None:
        if self._previous_guard is None:
            os.environ.pop("PHASE154L215_LAB", None)
        else:
            os.environ["PHASE154L215_LAB"] = self._previous_guard

    def new_id(self) -> str:
        return str(uuid4())

    def reserve(self, index: int) -> dict[str, object]:
        operation_id = self.new_id()
        state = self.coordinator.witness.state()
        return self.coordinator.reserve_admission(
            operation_id, digest(f"{operation_id}-{index}"), state["generation"]
        )

    def fill(self, count: int) -> list[dict[str, object]]:
        return [self.reserve(index) for index in range(count)]

    def test_requires_explicit_guard_and_marked_new_root(self) -> None:
        self.context.root.joinpath(".phase154-lot215-synthetic").unlink()
        with self.assertRaises(LabGuardError):
            open_existing_lab(self.root, self.witness_path, self.primary_path)
        os.environ.pop("PHASE154L215_LAB")
        with self.assertRaises(LabGuardError):
            initialize_lab(
                self.parent / "blocked",
                self.parent / "blocked" / "w.sqlite",
                self.parent / "blocked" / "p.sqlite",
            )

    def test_paths_must_be_distinct_explicit_and_below_root(self) -> None:
        with self.assertRaises(LabGuardError):
            initialize_lab(
                self.parent / "outside-root",
                self.parent / "outside-root" / "same.sqlite",
                self.parent / "outside-root" / "same.sqlite",
            )
        with self.assertRaises(LabGuardError):
            initialize_lab(
                self.parent / "outside-root-2",
                self.parent / "outside-root-2" / "w.sqlite",
                self.parent / "outside.sqlite",
            )
        with self.assertRaises(LabGuardError):
            initialize_lab(
                self.parent / "relative-root",
                Path("relative.sqlite"),
                self.parent / "relative-root" / "p.sqlite",
            )

    def test_existing_lab_open_requires_both_explicit_database_files(self) -> None:
        root = self.parent / "incomplete"
        root.mkdir()
        from ops.testing.lifecycle_lot215.protocol import LAB_MARKER, LAB_MARKER_CONTENT

        (root / LAB_MARKER).write_bytes(LAB_MARKER_CONTENT)
        with self.assertRaises(LabGuardError):
            open_existing_lab(root, root / "w.sqlite", root / "missing-p.sqlite")

    def test_w_and_p_are_distinct_and_start_at_genesis(self) -> None:
        self.assertNotEqual(self.context.witness_path, self.context.primary_path)
        witness = self.coordinator.witness.verify_integrity()
        primary = self.coordinator.primary.verify_integrity()
        self.assertEqual(witness["generation"], 0)
        self.assertIn("total_consumed", witness)
        self.assertNotIn("total_consumed", primary)
        self.assertEqual(witness["head_digest"], primary["head_digest"])
        self.assertTrue(self.coordinator.inspect().coherent)

    def test_admissions_are_cumulative_idempotent_and_capped(self) -> None:
        results = self.fill(ADMISSION_LIMIT)
        self.assertEqual([item["reservation_no"] for item in results], [1, 2, 3, 4, 5])
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], 5)
        with self.assertRaises(Conflict):
            self.reserve(99)
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], 5)

    def test_exact_reservation_retry_returns_existing_and_content_change_conflicts(self) -> None:
        op = self.new_id()
        identity = digest("same-identity")
        generation = self.coordinator.witness.state()["generation"]
        result = self.coordinator.reserve_admission(op, identity, generation)
        repeated, committed = self.coordinator.witness.reserve(op, identity, 0)
        self.assertFalse(committed)
        self.assertEqual(result["reservation_no"], repeated["reservation_no"])
        with self.assertRaises(Conflict):
            self.coordinator.witness.reserve(op, digest("different-identity"), 0)

    def test_duplicate_identity_and_reused_cross_domain_operation_id_fail(self) -> None:
        op = self.new_id()
        identity = digest("one-person")
        first = self.coordinator.reserve_admission(
            op, identity, self.coordinator.witness.state()["generation"]
        )
        second_op = self.new_id()
        with self.assertRaises(Conflict):
            self.coordinator.reserve_admission(
                second_op, identity, self.coordinator.witness.state()["generation"]
            )
        with self.assertRaises(Conflict):
            self.coordinator.run_critical(
                op, digest("operation"), digest("receipt"), digest("hold"),
                self.coordinator.witness.state()["generation"], confirmed=True, hold_clear=True,
            )
        self.assertEqual(first["reservation_no"], 1)

    def test_32_concurrent_witness_requests_cannot_overallocate_last_place(self) -> None:
        self.fill(ADMISSION_LIMIT - 1)
        generation = self.coordinator.witness.state()["generation"]

        def attempt(index: int) -> str:
            try:
                self.coordinator.witness.reserve(
                    self.new_id(), digest(f"concurrent-{index}"), generation
                )
                return "committed"
            except Conflict:
                return "refused"

        with ThreadPoolExecutor(max_workers=32) as pool:
            outcomes = list(pool.map(attempt, range(32)))
        self.assertEqual(outcomes.count("committed"), 1)
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], ADMISSION_LIMIT)

    def test_admission_fault_before_w_commit_rolls_back_and_same_id_can_resume(self) -> None:
        op = self.new_id()
        identity = digest("before-commit")
        generation = self.coordinator.witness.state()["generation"]
        with self.assertRaises(InjectedFailure):
            self.coordinator.reserve_admission(
                op, identity, generation, fail_at=FailurePoint.ADMISSION_BEFORE_W_COMMIT
            )
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], 0)
        resumed = self.coordinator.resume_operation(op, identity_digest=identity)
        self.assertEqual(resumed["reservation_no"], 1)

    def test_admission_fault_after_w_commit_keeps_place_and_resumes_same_id(self) -> None:
        op = self.new_id()
        identity = digest("after-w-commit")
        generation = self.coordinator.witness.state()["generation"]
        with self.assertRaises(InjectedFailure):
            self.coordinator.reserve_admission(
                op, identity, generation, fail_at=FailurePoint.ADMISSION_AFTER_W_COMMIT
            )
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], 1)
        with self.assertRaises(Closed):
            self.coordinator.reserve_admission(
                self.new_id(), digest("another"), self.coordinator.witness.state()["generation"]
            )
        resumed = self.coordinator.resume_operation(op, identity_digest=identity)
        self.assertEqual(resumed["reservation_no"], 1)
        self.assertTrue(self.coordinator.inspect().coherent)

    def test_admission_fault_after_p_commit_is_idempotently_resumable(self) -> None:
        op = self.new_id()
        identity = digest("after-p-commit")
        with self.assertRaises(InjectedFailure):
            self.coordinator.reserve_admission(
                op, identity, 0, fail_at=FailurePoint.ADMISSION_AFTER_P_COMMIT
            )
        result = self.coordinator.resume_operation(op, identity_digest=identity)
        self.assertEqual(result["reservation_no"], 1)
        self.assertEqual(self.coordinator.primary.reservation(op)["reservation_no"], 1)

    def test_all_admission_failure_boundaries_require_same_id_resume(self) -> None:
        points = [
            FailurePoint.ADMISSION_BEFORE_W_COMMIT,
            FailurePoint.ADMISSION_AFTER_W_COMMIT,
            FailurePoint.ADMISSION_BEFORE_P_APPLY,
            FailurePoint.ADMISSION_BEFORE_P_COMMIT,
            FailurePoint.ADMISSION_AFTER_P_COMMIT,
            FailurePoint.ADMISSION_FINAL_RECONCILIATION,
        ]
        for index, point in enumerate(points):
            with self.subTest(point=point.value):
                root = self.parent / f"admission-fault-{index}"
                context = initialize_lab(root, root / "w.sqlite", root / "p.sqlite")
                coordinator = Coordinator(context)
                op = self.new_id()
                identity = digest(f"admission-fault-{index}")
                with self.assertRaises(InjectedFailure):
                    coordinator.reserve_admission(op, identity, 0, fail_at=point)
                result = coordinator.resume_operation(op, identity_digest=identity)
                self.assertEqual(result["reservation_no"], 1)
                self.assertTrue(coordinator.inspect().coherent)

    def test_critical_operation_and_effect_are_idempotent(self) -> None:
        op = self.new_id()
        operation = digest("operation-content")
        result = self.coordinator.run_critical(
            op, operation, digest("receipt"), digest("hold"), 0, confirmed=True, hold_clear=True
        )
        repeated = self.coordinator.run_critical(
            op, operation, digest("receipt"), digest("hold"), 0, confirmed=True, hold_clear=True
        )
        self.assertEqual(result["state"], "result_recorded")
        self.assertEqual(repeated["result_digest"], result["result_digest"])
        self.assertEqual(result["effect_count"], 1)
        self.assertEqual(self.coordinator.primary.effect(op)["result_digest"], result["result_digest"])

    def test_synthetic_preconditions_are_required_before_any_critical_commit(self) -> None:
        op = self.new_id()
        with self.assertRaises(Closed):
            self.coordinator.run_critical(
                op, digest("operation"), digest("receipt"), digest("hold"), 0,
            )
        self.assertEqual(self.coordinator.witness.state()["generation"], 0)

    def test_quarantined_critical_operation_is_durable_and_not_reauthorizable(self) -> None:
        op = self.new_id()
        _, event = self.coordinator.witness.prepare(
            op, digest("operation"), digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        result = self.coordinator.quarantine_operation(op, digest("evidence"))
        self.assertEqual(result["state"], "quarantined")
        self.assertEqual(self.coordinator.witness.operation(op)["state"], "quarantined")
        self.assertEqual(self.coordinator.primary.operation(op)["state"], "quarantined")
        repeated, event = self.coordinator.witness.quarantine(
            op, digest("evidence"), self.coordinator.witness.state()["generation"]
        )
        self.assertIsNone(event)
        self.assertEqual(repeated["state"], "quarantined")
        with self.assertRaises(Conflict):
            self.coordinator.witness.quarantine(
                op, digest("different-evidence"), self.coordinator.witness.state()["generation"]
            )
        with self.assertRaises(Closed):
            self.coordinator.run_critical(
                op, digest("operation"), digest("receipt"), digest("hold"), 2,
                confirmed=True, hold_clear=True,
            )

    def test_uncertain_critical_operation_closes_both_domains(self) -> None:
        op = self.new_id()
        _, event = self.coordinator.witness.prepare(
            op, digest("operation"), digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        result = self.coordinator.mark_uncertain(op, digest("uncertainty-evidence"))
        self.assertEqual(result["state"], "uncertain")
        self.assertEqual(self.coordinator.witness.operation(op)["state"], "uncertain")
        self.assertEqual(self.coordinator.primary.operation(op)["state"], "uncertain")
        self.coordinator.witness.mark_uncertain(
            op, digest("uncertainty-evidence"), self.coordinator.witness.state()["generation"]
        )
        with self.assertRaises(Conflict):
            self.coordinator.witness.mark_uncertain(
                op, digest("different-evidence"), self.coordinator.witness.state()["generation"]
            )
        with self.assertRaises(Closed):
            self.coordinator.run_critical(
                op, digest("operation"), digest("receipt"), digest("hold"), 2,
                confirmed=True, hold_clear=True,
            )

    def test_critical_id_reuse_with_different_content_is_rejected(self) -> None:
        op = self.new_id()
        self.coordinator.run_critical(
            op, digest("first"), digest("r"), digest("h"), 0, confirmed=True, hold_clear=True
        )
        with self.assertRaises(Conflict):
            self.coordinator.run_critical(
                op, digest("second"), digest("r"), digest("h"), 0, confirmed=True, hold_clear=True
            )

    def test_critical_fault_after_effect_reuses_proof_without_repeating_effect(self) -> None:
        op = self.new_id()
        operation = digest("effect-lost-reply")
        with self.assertRaises(InjectedFailure):
            self.coordinator.run_critical(
                op, operation, digest("receipt"), digest("hold"), 0,
                confirmed=True, hold_clear=True, fail_at=FailurePoint.EFFECT_AFTER,
            )
        proof = self.coordinator.primary.effect(op)
        resumed = self.coordinator.resume_operation(
            op, operation_digest=operation, receipt_digest=digest("receipt"),
            hold_digest=digest("hold"), expected_generation=0,
            confirmed=True, hold_clear=True,
        )
        self.assertEqual(resumed["result_digest"], proof["result_digest"])
        self.assertEqual(resumed["effect_count"], 1)

    def _authorized_before_effect(self, operation: str) -> str:
        op = self.new_id()
        with self.assertRaises(InjectedFailure):
            self.coordinator.run_critical(
                op, operation, digest("receipt"), digest("hold"), 0,
                confirmed=True, hold_clear=True, fail_at=FailurePoint.EFFECT_BEFORE,
            )
        return op

    def _directly_authorize(self, operation: str) -> str:
        op = self.new_id()
        _, event = self.coordinator.witness.prepare(
            op, operation, digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        _, event = self.coordinator.witness.authorize(
            op, self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)
        return op

    def test_direct_effect_fails_after_witness_rollback_with_stale_primary(self) -> None:
        snapshot = self.root / "snapshots" / "w-genesis.sqlite"
        create_snapshot(self.context, self.witness_path, snapshot)
        operation = digest("rolled-back-effect")
        op = self._authorized_before_effect(operation)
        self.assertEqual(self.coordinator.primary.operation(op)["state"], "authorized")
        restore_snapshot(self.context, snapshot, self.witness_path, domain="W")
        self.context._set_recovery_required(False)
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_fails_when_recovery_is_required(self) -> None:
        operation = digest("recovery-effect")
        op = self._authorized_before_effect(operation)
        self.assertTrue(self.context.recovery_required)
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_fails_after_quarantine(self) -> None:
        operation = digest("quarantined-effect")
        op = self._authorized_before_effect(operation)
        self.context._set_recovery_required(False)
        self.coordinator.quarantine_operation(op, digest("evidence"))
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_fails_when_witness_authorization_is_missing(self) -> None:
        operation = digest("unauthorized-effect")
        op = self.new_id()
        with self.assertRaises(InjectedFailure):
            self.coordinator.run_critical(
                op, operation, digest("receipt"), digest("hold"), 0,
                confirmed=True, hold_clear=True, fail_at=FailurePoint.AUTHORIZE_BEFORE_W_COMMIT,
            )
        self.context._set_recovery_required(False)
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)

    def test_direct_effect_fails_when_witness_is_closed(self) -> None:
        operation = digest("closed-witness-effect")
        op = self._directly_authorize(operation)
        self.coordinator.witness.close()
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_fails_after_primary_rollback(self) -> None:
        op = self.new_id()
        operation = digest("rolled-back-primary-effect")
        _, event = self.coordinator.witness.prepare(
            op, operation, digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        prepared_snapshot = self.root / "snapshots" / "p-prepared.sqlite"
        create_snapshot(self.context, self.primary_path, prepared_snapshot)
        _, event = self.coordinator.witness.authorize(
            op, self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)
        restore_snapshot(self.context, prepared_snapshot, self.primary_path, domain="P")
        self.context._set_recovery_required(False)
        with self.assertRaises(Closed):
            self.coordinator.primary.execute_effect_once(op, operation)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_rejects_divergent_digest(self) -> None:
        operation = digest("authorized-effect-digest")
        op = self._directly_authorize(operation)
        with self.assertRaises(Conflict):
            self.coordinator.primary.execute_effect_once(op, digest("different-effect-digest"))
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_direct_effect_normal_and_idempotent_when_current(self) -> None:
        operation = digest("current-effect")
        op = self.new_id()
        prepared, event = self.coordinator.witness.prepare(
            op, operation, digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        authorized, event = self.coordinator.witness.authorize(
            op, self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)
        first = self.coordinator.primary.execute_effect_once(op, operation)
        self.assertEqual(self.coordinator.primary.execute_effect_once(op, operation), first)

    def test_direct_effect_and_w_uncertainty_are_serialized(self) -> None:
        operation = digest("serialized-effect")
        op = self.new_id()
        _, event = self.coordinator.witness.prepare(
            op, operation, digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        _, event = self.coordinator.witness.authorize(
            op, self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)

        checked = threading.Event()
        release_effect = threading.Event()
        original_check = self.coordinator.primary._require_current_witness_authorization

        def pause_after_authorization(
            row: sqlite3.Row, operation_id: str, operation_digest: str,
        ) -> None:
            original_check(row, operation_id, operation_digest)
            checked.set()
            if not release_effect.wait(timeout=5):
                raise AssertionError("Timed out waiting to release synthetic effect")

        self.coordinator.primary._require_current_witness_authorization = pause_after_authorization
        with ThreadPoolExecutor(max_workers=2) as pool:
            effect = pool.submit(self.coordinator.primary.execute_effect_once, op, operation)
            self.assertTrue(checked.wait(timeout=5))
            uncertain = pool.submit(
                self.coordinator.witness.mark_uncertain,
                op,
                digest("uncertainty-evidence"),
                self.coordinator.witness.state()["generation"],
            )
            self.assertFalse(uncertain.done())
            release_effect.set()
            effect.result(timeout=5)
            uncertain.result(timeout=5)

        self.assertEqual(self.coordinator.witness.operation(op)["state"], "uncertain")
        self.assertIsNotNone(self.coordinator.primary.effect(op))

    def test_direct_effect_and_snapshot_restore_are_serialized(self) -> None:
        operation = digest("serialized-restore-effect")
        snapshot = self.root / "snapshots" / "w-before-authorization.sqlite"
        create_snapshot(self.context, self.witness_path, snapshot)
        op = self._directly_authorize(operation)
        checked = threading.Event()
        release_effect = threading.Event()
        original_check = self.coordinator.primary._require_current_witness_authorization

        def pause_after_authorization(
            row: sqlite3.Row, operation_id: str, operation_digest: str,
        ) -> None:
            original_check(row, operation_id, operation_digest)
            checked.set()
            if not release_effect.wait(timeout=5):
                raise AssertionError("Timed out waiting to release synthetic effect")

        self.coordinator.primary._require_current_witness_authorization = pause_after_authorization
        with ThreadPoolExecutor(max_workers=2) as pool:
            effect = pool.submit(self.coordinator.primary.execute_effect_once, op, operation)
            self.assertTrue(checked.wait(timeout=5))
            restore = pool.submit(
                restore_snapshot, self.context, snapshot, self.witness_path, domain="W"
            )
            self.assertFalse(restore.done())
            release_effect.set()
            effect.result(timeout=5)
            restore.result(timeout=5)

        self.assertTrue(self.context.recovery_required)
        self.assertIsNotNone(self.coordinator.primary.effect(op))

    def test_opening_same_database_paths_reuses_the_lab_lock(self) -> None:
        reopened = open_existing_lab(self.root, self.witness_path, self.primary_path)
        self.assertIs(reopened._lock, self.context._lock)
        with self.assertRaises(AttributeError):
            reopened.recovery_required = False
        with self.assertRaises(Closed):
            Coordinator(reopened).witness.reserve(
                self.new_id(), digest("reopened-lab-write"), 0
            )
        with self.assertRaises(LabGuardError):
            LabContext(self.root, self.witness_path, self.primary_path, _recovery_required=False)

    def test_simultaneous_restore_closes_preexisting_contexts_for_same_paths(self) -> None:
        op = self.new_id()
        operation_digest = digest("restored-authorized-effect")
        _, event = self.coordinator.witness.prepare(
            op, operation_digest, digest("receipt"), digest("hold"), 0
        )
        self.coordinator.primary.apply(event)
        _, event = self.coordinator.witness.authorize(
            op, self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)
        w_authorized = self.root / "snapshots" / "w-authorized.sqlite"
        p_authorized = self.root / "snapshots" / "p-authorized.sqlite"
        create_snapshot(self.context, self.witness_path, w_authorized)
        create_snapshot(self.context, self.primary_path, p_authorized)
        _, event = self.coordinator.witness.record_result(
            op, digest("result"), self.coordinator.witness.state()["generation"]
        )
        self.coordinator.primary.apply(event)
        other_context = copy(self.context)

        restore_snapshot(self.context, w_authorized, self.witness_path, domain="W")
        restore_snapshot(self.context, p_authorized, self.primary_path, domain="P")
        self.assertTrue(other_context.recovery_required)
        with self.assertRaises(Closed):
            Coordinator(other_context).primary.execute_effect_once(op, operation_digest)
        self.assertIsNone(self.coordinator.primary.effect(op))

    def test_all_critical_failure_boundaries_resume_explicitly(self) -> None:
        points = [
            FailurePoint.PREPARE_BEFORE_W_COMMIT,
            FailurePoint.PREPARE_AFTER_W_COMMIT,
            FailurePoint.PREPARE_BEFORE_P_APPLY,
            FailurePoint.PREPARE_BEFORE_P_COMMIT,
            FailurePoint.PREPARE_AFTER_P_COMMIT,
            FailurePoint.AUTHORIZE_BEFORE_W_COMMIT,
            FailurePoint.AUTHORIZE_AFTER_W_COMMIT,
            FailurePoint.AUTHORIZE_BEFORE_P_APPLY,
            FailurePoint.AUTHORIZE_BEFORE_P_COMMIT,
            FailurePoint.AUTHORIZE_AFTER_P_COMMIT,
            FailurePoint.EFFECT_BEFORE,
            FailurePoint.EFFECT_AFTER,
            FailurePoint.RESULT_BEFORE_W_COMMIT,
            FailurePoint.RESULT_AFTER_W_COMMIT,
            FailurePoint.RESULT_BEFORE_P_APPLY,
            FailurePoint.RESULT_BEFORE_P_COMMIT,
            FailurePoint.RESULT_AFTER_P_COMMIT,
            FailurePoint.CRITICAL_FINAL_RECONCILIATION,
        ]
        for index, point in enumerate(points):
            with self.subTest(point=point.value):
                op = self.new_id()
                inputs = {
                    "operation_digest": digest(f"op-{index}"),
                    "receipt_digest": digest(f"receipt-{index}"),
                    "hold_digest": digest(f"hold-{index}"),
                    "expected_generation": self.coordinator.witness.state()["generation"],
                    "confirmed": True,
                    "hold_clear": True,
                }
                with self.assertRaises(InjectedFailure):
                    self.coordinator.run_critical(op, **inputs, fail_at=point)
                result = self.coordinator.resume_operation(op, **inputs)
                self.assertEqual(result["state"], "result_recorded")
                self.assertEqual(result["effect_count"], 1)
                self.assertTrue(self.coordinator.inspect().coherent)

    def test_witness_unavailability_never_allows_primary_only_reservation(self) -> None:
        self.coordinator.witness.close()
        with self.assertRaises(Closed):
            self.coordinator.reserve_admission(self.new_id(), digest("x"), 0)
        self.assertIsNone(self.coordinator.primary.reservation("not-an-operation"))

    def test_primary_unavailability_keeps_witness_consumption_and_never_returns_success(self) -> None:
        self.coordinator.primary.close()
        op = self.new_id()
        with self.assertRaises(Closed):
            self.coordinator.reserve_admission(op, digest("primary-offline"), 0)
        self.assertEqual(self.coordinator.witness.state()["total_consumed"], 0)
        self.assertIsNone(self.coordinator.primary.reservation(op))

    def test_restore_during_pending_operation_cannot_use_nominal_resume_path(self) -> None:
        snapshot = self.root / "snapshots" / "p-genesis.sqlite"
        create_snapshot(self.context, self.primary_path, snapshot)
        op = self.new_id()
        identity = digest("pending-then-restore")
        with self.assertRaises(InjectedFailure):
            self.coordinator.reserve_admission(
                op, identity, 0, fail_at=FailurePoint.ADMISSION_AFTER_W_COMMIT
            )
        restore_snapshot(self.context, snapshot, self.primary_path, domain="P")
        with self.assertRaises(Closed):
            self.coordinator.resume_operation(op, identity_digest=identity)

    def test_primary_rollback_is_incomplete_and_closed(self) -> None:
        self.fill(3)
        snapshot = self.root / "snapshots" / "p-at-three.sqlite"
        create_snapshot(self.context, self.primary_path, snapshot)
        self.fill(2)
        restore_snapshot(self.context, snapshot, self.primary_path, domain="P")
        result = self.coordinator.inspect()
        self.assertFalse(result.coherent)
        self.assertEqual(result.witness_generation, 5)
        self.assertEqual(result.primary_generation, 3)
        self.assertEqual(result.freshness, "not_demonstrable")
        with self.assertRaises(Closed):
            self.coordinator.reserve_admission(self.new_id(), digest("blocked"), 5)

    def test_witness_rollback_contradicting_primary_is_quarantined(self) -> None:
        self.fill(3)
        snapshot = self.root / "snapshots" / "w-at-three.sqlite"
        create_snapshot(self.context, self.witness_path, snapshot)
        self.fill(2)
        restore_snapshot(self.context, snapshot, self.witness_path, domain="W")
        result = self.coordinator.inspect()
        self.assertFalse(result.coherent)
        self.assertIn("Primary is ahead", result.reason)
        with self.assertRaises(Closed):
            self.coordinator.require_recovery_evidence()

    def test_simultaneous_old_restore_is_coherent_but_freshness_is_unknown(self) -> None:
        self.fill(3)
        w_snapshot = self.root / "snapshots" / "w-at-three.sqlite"
        p_snapshot = self.root / "snapshots" / "p-at-three.sqlite"
        create_snapshot(self.context, self.witness_path, w_snapshot)
        create_snapshot(self.context, self.primary_path, p_snapshot)
        self.fill(2)
        restore_snapshot(self.context, w_snapshot, self.witness_path, domain="W")
        restore_snapshot(self.context, p_snapshot, self.primary_path, domain="P")
        result = self.coordinator.inspect()
        self.assertTrue(result.coherent)
        self.assertEqual(result.witness_generation, 3)
        self.assertEqual(result.freshness, "not_demonstrable")
        with self.assertRaises(Closed):
            self.coordinator.reserve_admission(self.new_id(), digest("blocked"), 3)
        reopened = open_existing_lab(self.root, self.witness_path, self.primary_path)
        with self.assertRaises(Closed):
            Coordinator(reopened).run_critical(
                self.new_id(), digest("x"), digest("r"), digest("h"), 3,
                confirmed=True, hold_clear=True,
            )

    def test_snapshots_use_sqlite_backup_api_and_reject_cross_domain_restore(self) -> None:
        snapshot = self.root / "snapshots" / "w.sqlite"
        create_snapshot(self.context, self.witness_path, snapshot)
        with self.assertRaises(LabGuardError):
            restore_snapshot(self.context, snapshot, self.primary_path, domain="P")

    def test_truncated_or_altered_witness_history_fails_integrity(self) -> None:
        self.fill(2)
        tamper_for_test(
            self.context, "W",
            "DELETE FROM events WHERE generation = ?", (2,),
        )
        result = self.coordinator.inspect()
        self.assertFalse(result.coherent)
        self.assertEqual(result.freshness, "not_demonstrable")

    def test_altered_primary_event_digest_is_detected(self) -> None:
        self.fill(1)
        tamper_for_test(
            self.context, "P",
            "UPDATE events SET head_digest = ? WHERE generation = 1",
            (digest("fake-head"),),
        )
        self.assertFalse(self.coordinator.inspect().coherent)

    def test_truncated_primary_history_is_detected(self) -> None:
        self.fill(2)
        tamper_for_test(self.context, "P", "DELETE FROM events WHERE generation = ?", (1,))
        self.assertFalse(self.coordinator.inspect().coherent)

    def test_two_valid_same_generation_branches_are_detected_as_a_fork(self) -> None:
        p_genesis = self.root / "snapshots" / "p-genesis.sqlite"
        create_snapshot(self.context, self.primary_path, p_genesis)
        first = self.new_id()
        self.coordinator.reserve_admission(first, digest("branch-a"), 0)

        branch_root = self.parent / "branch-b"
        branch_context = initialize_lab(
            branch_root, branch_root / "w.sqlite", branch_root / "p.sqlite"
        )
        branch_coordinator = Coordinator(branch_context)
        self.addCleanup(branch_coordinator.primary.close)
        self.addCleanup(branch_coordinator.witness.close)
        second = self.new_id()
        branch_coordinator.reserve_admission(second, digest("branch-b"), 0)
        branch_event = branch_coordinator.witness.event(1)
        with self.assertRaises(Conflict):
            self.coordinator.primary.apply(branch_event)

        snapshot_dir = self.root / "snapshots"
        snapshot_dir.mkdir(exist_ok=True)
        branch_p_snapshot = snapshot_dir / "p-branch-b.sqlite"
        source = sqlite3.connect(branch_context.primary_path)
        target = sqlite3.connect(branch_p_snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        restore_snapshot(self.context, branch_p_snapshot, self.primary_path, domain="P")
        result = self.coordinator.inspect()
        self.assertFalse(result.coherent)
        self.assertIn("Conflicting history or fork", result.reason)

    def test_generation_gap_conflict_and_reused_identity_are_refused(self) -> None:
        operation_id = self.new_id()
        identity = digest("duplicate-identity")
        self.coordinator.reserve_admission(operation_id, identity, 0)
        with self.assertRaises(Conflict):
            self.coordinator.witness.reserve(self.new_id(), digest("stale"), 0)
        with self.assertRaises(Conflict):
            self.coordinator.witness.reserve(
                self.new_id(), identity, self.coordinator.witness.state()["generation"]
            )


if __name__ == "__main__":
    unittest.main()
