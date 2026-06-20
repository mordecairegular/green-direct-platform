from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
from green_direct.models.params import PolicyParams
from green_direct.models.pilot_backend import ArtifactKind, AuditAction, JobStatus, JobType, Project, User
from green_direct.services import (
    LocalJobStore,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAccessService,
    TechnicalStudyInput,
    execute_next_worker_job,
    execute_worker_loop,
    persist_economic_study_result,
    persist_technical_study_result,
    queue_job_with_input_artifact,
    run_economic_study,
    run_technical_study,
)


def _access_service(tmp_path) -> PilotAccessService:
    return PilotAccessService(
        registry=LocalPilotRegistry(tmp_path),
        job_store=LocalJobStore(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )


def _curve_csv(values: list[float], column: str) -> bytes:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(values), freq="h"),
            column: values,
        }
    )
    return frame.to_csv(index=False).encode("utf-8")


def _small_technical_input(*, retain_hourly_details: bool = False) -> TechnicalStudyInput:
    return TechnicalStudyInput(
        load_source=_curve_csv([10.0, 10.0], "load"),
        pv_source=_curve_csv([1.0, 0.0], "pv"),
        wind_source=_curve_csv([0.0, 1.0], "wind"),
        load_time_col="timestamp",
        load_value_col="load",
        pv_time_col="timestamp",
        pv_value_col="pv",
        wind_time_col="timestamp",
        wind_value_col="wind",
        scenario_grid={
            "pv_capacity": {"start": 0, "end": 1, "step": 1},
            "wind_capacity": {"start": 0, "end": 1, "step": 1},
            "bess_power": {"start": 0, "end": 0, "step": 1},
            "bess_duration_hours": [0],
        },
        policy_params=PolicyParams(allow_export=False),
        validate_length=False,
        retain_hourly_details=retain_hourly_details,
    )


def _project_with_admin(service: PilotAccessService) -> Project:
    service.registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    return service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )


def test_worker_executes_hourly_detail_job_from_input_artifacts(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    summary_only_input = _small_technical_input(retain_hourly_details=False)
    technical = run_technical_study(summary_only_input, study_id="study_1")
    full = run_technical_study(_small_technical_input(retain_hourly_details=True), study_id="study_full")
    selected_id = str(technical.summary["scenario_id"].iloc[-1])
    persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=technical,
        technical_input=summary_only_input,
    )
    queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.TECHNICAL_STUDY,
        payload={
            "task": "hourly_detail",
            "scenario_id": selected_id,
            "technical_result_id": "technical_result",
            "retention_days": 30,
        },
        input_artifact_ids={
            "technical_summary": "technical_summary",
            "config_snapshot": "config_snapshot",
            "input_curve_load": "input_curve_load",
            "input_curve_pv": "input_curve_pv",
            "input_curve_wind": "input_curve_wind",
        },
        job_id="job_hourly_detail_worker",
        progress_total=1,
        progress_message="hourly detail queued",
    )

    result = execute_next_worker_job(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=[JobType.TECHNICAL_STUDY],
    )

    assert result is not None
    assert result.succeeded
    assert result.job.job_id == "job_hourly_detail_worker"
    assert result.job.status == JobStatus.SUCCEEDED
    assert result.job.progress_current == 1
    assert result.job.progress_total == 1
    assert result.artifact is not None
    assert result.artifact.kind == ArtifactKind.HOURLY_DETAIL
    assert result.artifact.job_id == "job_hourly_detail_worker"
    record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")
    assert record.hourly_detail_artifact_ids == {selected_id: f"hourly_detail_{selected_id}"}
    payload = service.result_store.read_artifact_payload(result.artifact)
    hourly_detail = pd.read_csv(BytesIO(payload))
    hourly_detail["timestamp"] = pd.to_datetime(hourly_detail["timestamp"])
    pd.testing.assert_frame_equal(
        hourly_detail.reset_index(drop=True),
        full.hourly_details[selected_id].reset_index(drop=True),
        check_dtype=False,
    )
    audit_events = service.result_store.read_audit_log(project.project_id)
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.job_id == "job_hourly_detail_worker"
        and event.target_id == f"hourly_detail_{selected_id}"
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_hourly_detail_worker"
        and event.metadata["status"] == "succeeded"
        and event.metadata["worker_id"] == "worker_1"
        for event in audit_events
    )


def test_worker_executes_annual_cashflow_job_from_saved_economy_inputs(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    technical_input = _small_technical_input(retain_hourly_details=False)
    technical = run_technical_study(technical_input, study_id="study_1")
    selected_id = str(technical.summary["scenario_id"].iloc[-1])
    persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=technical,
        technical_input=technical_input,
    )
    params = EconomicParams(operation_years=3, self_use_price_with_vat=0.42)
    avoided = AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.57)
    economy = run_economic_study(
        technical.summary,
        economic_params=params,
        avoided_grid_params=avoided,
        load_side_avoided_charge_price=0.57,
        green_power_settlement_price_with_vat=0.42,
        retain_annual_cashflows=False,
        annual_cashflow_scenario_ids=(),
    )
    persisted_economy = persist_economic_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        economic_result=economy,
    )
    direct = run_economic_study(
        technical.summary[technical.summary["scenario_id"].astype(str) == selected_id],
        economic_params=params,
        avoided_grid_params=avoided,
        load_side_avoided_charge_price=0.57,
        green_power_settlement_price_with_vat=0.42,
        retain_annual_cashflows=False,
        annual_cashflow_scenario_ids=[selected_id],
    )
    queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.ECONOMIC_STUDY,
        payload={
            "task": "annual_cashflow",
            "scenario_id": selected_id,
            "economy_result_id": persisted_economy.result_record.result_id,
            "perspective": "both",
            "retention_days": 30,
        },
        input_artifact_ids={
            "technical_summary": "technical_summary",
            "recommendation_inputs": persisted_economy.recommendation_input_artifact.artifact_id,
            "power_economy_summary": persisted_economy.power_summary_artifact.artifact_id,
        },
        job_id="job_annual_cashflow_worker",
        progress_total=2,
        progress_message=f"annual cashflow queued: {selected_id}",
    )

    result = execute_next_worker_job(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=[JobType.ECONOMIC_STUDY],
    )

    assert result is not None
    assert result.succeeded
    assert result.job.job_id == "job_annual_cashflow_worker"
    assert result.job.progress_current == 2
    assert result.job.progress_total == 2
    record = service.result_store.load_result_record(
        project.project_id,
        "study_1",
        persisted_economy.result_record.result_id,
    )
    assert record.annual_cashflow_artifact_ids["power:" + selected_id] == f"power_annual_cashflow_{selected_id}"
    assert record.annual_cashflow_artifact_ids["single_entity:" + selected_id] == (
        f"single_entity_annual_cashflow_{selected_id}"
    )
    power_artifact = service.result_store.load_artifact(
        project.project_id,
        "study_1",
        f"power_annual_cashflow_{selected_id}",
    )
    assert power_artifact.kind == ArtifactKind.ANNUAL_CASHFLOW
    assert power_artifact.job_id == "job_annual_cashflow_worker"
    with ZipFile(BytesIO(service.result_store.read_artifact_payload(power_artifact))) as archive:
        power_cashflow = pd.read_csv(BytesIO(archive.read(f"{selected_id}.csv")))
    pd.testing.assert_frame_equal(
        power_cashflow.reset_index(drop=True),
        direct.power_annual_cashflows[selected_id].reset_index(drop=True),
        check_dtype=False,
    )
    audit_events = service.result_store.read_audit_log(project.project_id)
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.job_id == "job_annual_cashflow_worker"
        and event.target_id == f"power_annual_cashflow_{selected_id}"
        for event in audit_events
    )


def test_worker_marks_unsupported_job_failed(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.ECONOMIC_STUDY,
        payload={"task": "economy"},
        job_id="job_unsupported",
    )

    result = execute_next_worker_job(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=[JobType.ECONOMIC_STUDY],
    )

    assert result is not None
    assert not result.succeeded
    assert result.job.status == JobStatus.FAILED
    assert "economic_study worker currently supports task=annual_cashflow only" in str(result.job.error_message)


def test_worker_loop_processes_jobs_until_max_jobs(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    for job_id in ("job_unsupported_1", "job_unsupported_2"):
        queue_job_with_input_artifact(
            access_service=service,
            actor_user_id="admin",
            project_id=project.project_id,
            study_id="study_1",
            job_type=JobType.ECONOMIC_STUDY,
            payload={"task": "economy"},
            job_id=job_id,
        )
    seen_job_ids: list[str] = []
    sleeps: list[float] = []

    summary = execute_worker_loop(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_loop",
        job_types=[JobType.ECONOMIC_STUDY],
        poll_interval_seconds=0.25,
        max_jobs=2,
        sleep=sleeps.append,
        on_result=lambda result: seen_job_ids.append(result.job.job_id),
    )

    assert summary.stopped_reason == "max_jobs"
    assert summary.jobs_executed == 2
    assert summary.succeeded_jobs == 0
    assert summary.failed_jobs == 2
    assert summary.idle_polls == 0
    assert seen_job_ids == ["job_unsupported_1", "job_unsupported_2"]
    assert sleeps == []
    assert service.job_store.load_job(project.project_id, "study_1", "job_unsupported_1").status == JobStatus.FAILED
    assert service.job_store.load_job(project.project_id, "study_1", "job_unsupported_2").status == JobStatus.FAILED


def test_worker_loop_can_exit_after_idle_polls(tmp_path):
    service = _access_service(tmp_path)
    _project_with_admin(service)
    sleeps: list[float] = []

    summary = execute_worker_loop(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_loop",
        job_types=[JobType.TECHNICAL_STUDY],
        poll_interval_seconds=0.25,
        idle_exit_after=2,
        sleep=sleeps.append,
    )

    assert summary.stopped_reason == "idle_exit_after"
    assert summary.jobs_executed == 0
    assert summary.succeeded_jobs == 0
    assert summary.failed_jobs == 0
    assert summary.idle_polls == 2
    assert summary.last_result is None
    assert sleeps == [0.25]
