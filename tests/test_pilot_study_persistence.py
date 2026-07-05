import json
from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import pytest

from green_direct.batch.batch_runner import BatchResult
from green_direct.economy import EconomicParams
from green_direct.models.diagnostics import InputDiagnostics
from green_direct.models.pilot_backend import (
    ArtifactKind,
    ArtifactRetentionPolicy,
    AuditAction,
    JobStatus,
    JobType,
    Project,
    ProjectRole,
    User,
)
from green_direct.services import (
    LocalJobStore,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAccessError,
    PilotAccessService,
    economic_input_fingerprint,
    persist_economic_study_result,
    persist_export_artifact,
    persist_hourly_detail_artifact,
    persist_recommendation_study_result,
    persist_technical_study_result,
    queue_job_with_input_artifact,
    recommendation_result_fingerprint,
    technical_input_fingerprint,
)
from green_direct.services.study_runner import (
    EconomicStudyResult,
    RecommendationInputSnapshot,
    RecommendationStudyResult,
    TechnicalStudyInput,
    TechnicalStudyResult,
)


def _access_service(tmp_path) -> PilotAccessService:
    return PilotAccessService(
        registry=LocalPilotRegistry(tmp_path),
        job_store=LocalJobStore(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )


def _technical_result(study_id: str = "study_1") -> TechnicalStudyResult:
    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "pv_capacity": 5.0,
                "wind_capacity": 2.0,
                "bess_power": 1.0,
                "green_load_rate": 0.42,
            }
        ]
    )
    return TechnicalStudyResult(
        study_id=study_id,
        batch_result=BatchResult(
            summary=summary,
            hourly_details={},
            errors=pd.DataFrame(),
            warnings=[],
            scenario_count=1,
        ),
        input_diagnostics=InputDiagnostics(),
        config_snapshot={
            "study_id": study_id,
            "scenario_grid": {"pv_capacity": {"start": 5, "end": 5, "step": 1}},
            "detail_retention": {"retain_hourly_details": False},
        },
    )


def _technical_input() -> TechnicalStudyInput:
    timestamps = pd.date_range("2026-01-01", periods=24, freq="h")

    def csv_payload(column: str, value: float) -> bytes:
        return pd.DataFrame({"timestamp": timestamps, column: [value] * len(timestamps)}).to_csv(index=False).encode(
            "utf-8"
        )

    return TechnicalStudyInput(
        load_source=csv_payload("load", 1.0),
        pv_source=csv_payload("pv", 0.5),
        wind_source=csv_payload("wind", 0.3),
        load_time_col="timestamp",
        load_value_col="load",
        pv_time_col="timestamp",
        pv_value_col="pv",
        wind_time_col="timestamp",
        wind_value_col="wind",
        scenario_grid={"pv_capacity": {"start": 5, "end": 5, "step": 1}},
    )


def _economic_result() -> EconomicStudyResult:
    return EconomicStudyResult(
        power_summary=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "firr": [0.08],
                "fnpv": [12.5],
            }
        ),
        power_annual_cashflows={
            "S0001": pd.DataFrame(
                {
                    "scenario_id": ["S0001", "S0001"],
                    "year": [0, 1],
                    "net_cash_flow": [-100.0, 18.0],
                }
            )
        },
        single_entity_summary=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "single_entity_firr_pre_tax": [0.11],
                "annual_self_use_saving": [18.0],
            }
        ),
        single_entity_annual_cashflows={
            "S0001": pd.DataFrame(
                {
                    "scenario_id": ["S0001", "S0001"],
                    "year": [0, 1],
                    "net_cash_flow": [-100.0, 22.0],
                }
            )
        },
        recommendation_inputs=RecommendationInputSnapshot(
            economic_params=EconomicParams(),
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.40,
            environmental_value_per_kwh=0.01,
            min_power_side_acceptable_firr=0.07,
        ),
        price_mode="fixed_price",
    )


def _recommendation_result() -> RecommendationStudyResult:
    return RecommendationStudyResult(
        portfolio=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "seat_labels": ["same_entity_firr_best"],
                "recommendation_reason": ["highest reliable FIRR"],
                "tradeoff_note": [pd.NA],
            }
        ),
        load_side_detail=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "load_side_tradable_benefit": [10.0],
            }
        ),
    )


def test_persist_technical_study_result_writes_job_artifacts_and_record(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    technical_result = _technical_result()

    persisted = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=technical_result,
        technical_input=_technical_input(),
    )

    loaded_job = service.job_store.load_job(project.project_id, "study_1", persisted.job.job_id)
    summary_artifact = service.result_store.load_artifact(project.project_id, "study_1", "technical_summary")
    config_artifact = service.result_store.load_artifact(project.project_id, "study_1", "config_snapshot")
    load_input_artifact = service.result_store.load_artifact(project.project_id, "study_1", "input_curve_load")
    result_record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")
    config_payload = service.result_store.read_artifact_payload(config_artifact).decode("utf-8")

    assert loaded_job.status == JobStatus.SUCCEEDED
    assert loaded_job.input_fingerprint == technical_input_fingerprint(technical_result)
    assert summary_artifact.kind == ArtifactKind.TECHNICAL_SUMMARY
    assert config_artifact.kind == ArtifactKind.CONFIG_SNAPSHOT
    assert load_input_artifact.kind == ArtifactKind.INPUT_CURVE
    assert load_input_artifact.retention_policy == ArtifactRetentionPolicy.EXPIRE
    assert load_input_artifact.expires_at is not None
    assert "timestamp,load" in service.result_store.read_artifact_payload(load_input_artifact).decode("utf-8")
    assert set(persisted.input_curve_artifacts) == {"load", "pv", "wind"}
    assert service.result_store.read_artifact_payload(summary_artifact).decode("utf-8").startswith("scenario_id")
    assert '"study_id": "study_1"' in config_payload
    assert '"input_artifact_ids"' in config_payload
    assert result_record.created_by_job_id == persisted.job.job_id
    assert result_record.technical_summary_artifact_id == "technical_summary"
    assert any(
        event.action == AuditAction.SUBMIT_JOB
        for event in service.result_store.read_audit_log(project.project_id)
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        for event in service.result_store.read_audit_log(project.project_id)
    )
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.target_id == "input_curve_load"
        and event.metadata["curve"] == "load"
        for event in service.result_store.read_audit_log(project.project_id)
    )


def test_persist_technical_study_result_replaces_visible_project_result(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )

    first = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=_technical_result("study_old"),
    )
    second = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=_technical_result("study_current"),
    )

    visible_records = service.result_store.list_project_result_records(project.project_id)
    archived_first = service.result_store.load_result_record(
        project.project_id,
        first.result_record.study_id,
        first.result_record.result_id,
    )

    assert [record.study_id for record in visible_records] == [second.result_record.study_id]
    assert visible_records[0].result_id == "technical_result"
    assert archived_first.is_deleted
    assert archived_first.deleted_by_user_id == "admin"
    assert any(
        event.action == AuditAction.DELETE_RESULT_RECORD
        and event.target_id == first.result_record.result_id
        and event.metadata["reason"] == "replace_current_project_result"
        for event in service.result_store.read_audit_log(project.project_id)
    )


def test_persist_technical_study_result_rejects_viewer(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
    )

    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        persist_technical_study_result(
            access_service=service,
            actor_user_id="viewer",
            project_id=project.project_id,
            technical_result=_technical_result(),
        )

    assert service.job_store.list_project_jobs(project.project_id) == []


def test_persist_hourly_detail_artifact_attaches_to_technical_result(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    technical = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=_technical_result(),
    )
    hourly = pd.DataFrame(
        {
            "scenario_id": ["S0001"],
            "timestamp": ["2026-01-01 00:00:00"],
            "load_power": [1.25],
        }
    )

    persisted = persist_hourly_detail_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        scenario_id="S0001",
        hourly_detail=hourly,
        technical_job_id=technical.job.job_id,
    )

    record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")
    payload = service.result_store.read_artifact_payload(persisted.artifact).decode("utf-8")

    assert persisted.artifact.kind == ArtifactKind.HOURLY_DETAIL
    assert persisted.artifact.retention_policy == ArtifactRetentionPolicy.EXPIRE
    assert persisted.artifact.expires_at is not None
    assert "load_power" in payload
    assert "1.25" in payload
    assert record.hourly_detail_artifact_ids == {"S0001": "hourly_detail_S0001"}
    assert record.created_by_job_id == technical.job.job_id
    assert any(
        event.action == AuditAction.STORE_ARTIFACT and event.target_id == "hourly_detail_S0001"
        for event in service.result_store.read_audit_log(project.project_id)
    )


def test_persist_hourly_detail_artifact_rejects_viewer(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    technical = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=_technical_result(),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
    )

    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        persist_hourly_detail_artifact(
            access_service=service,
            actor_user_id="viewer",
            project_id=project.project_id,
            study_id="study_1",
            scenario_id="S0001",
            hourly_detail=pd.DataFrame({"scenario_id": ["S0001"], "hour_index": [0]}),
            technical_job_id=technical.job.job_id,
        )


def test_persist_export_artifact_writes_report_and_chart_package(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )

    markdown = persist_export_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        artifact_key="markdown",
        payload="# Pilot report\n",
        filename="green_direct_report_S0001.md",
        content_type="text/markdown",
        artifact_kind=ArtifactKind.REPORT,
        metadata={"scenario_id": "S0001"},
    )
    chart = persist_export_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        artifact_key="chart_html",
        payload=b"chart zip bytes",
        filename="chart_html_S0001.zip",
        content_type="application/zip",
        artifact_kind=ArtifactKind.CHART_PACKAGE,
        metadata={"scenario_id": "S0001"},
    )

    markdown_payload = service.result_store.read_artifact_payload(markdown.artifact).decode("utf-8")
    chart_payload = service.result_store.read_artifact_payload(chart.artifact)
    audit_events = service.result_store.read_audit_log(project.project_id)

    assert markdown.job.status == JobStatus.SUCCEEDED
    assert markdown.job.job_type == JobType.REPORT_EXPORT
    assert markdown.artifact.kind == ArtifactKind.REPORT
    assert markdown.artifact.retention_policy == ArtifactRetentionPolicy.EXPIRE
    assert markdown.artifact.expires_at is not None
    assert markdown.result_record.report_artifact_ids == {"markdown": markdown.artifact.artifact_id}
    assert markdown_payload == "# Pilot report\n"
    assert chart.job.job_type == JobType.CHART_EXPORT
    assert chart.artifact.kind == ArtifactKind.CHART_PACKAGE
    assert chart.result_record.report_artifact_ids == {"chart_html": chart.artifact.artifact_id}
    assert chart_payload == b"chart zip bytes"
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.target_id == markdown.artifact.artifact_id
        and event.metadata["artifact_key"] == "markdown"
        and event.metadata["scenario_id"] == "S0001"
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.target_id == chart.artifact.artifact_id
        and event.metadata["kind"] == ArtifactKind.CHART_PACKAGE.value
        for event in audit_events
    )


def test_persist_export_artifact_rejects_viewer(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
        can_export_artifacts=True,
    )

    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        persist_export_artifact(
            access_service=service,
            actor_user_id="viewer",
            project_id=project.project_id,
            study_id="study_1",
            artifact_key="markdown",
            payload="# Pilot report\n",
            filename="green_direct_report_S0001.md",
            content_type="text/markdown",
            artifact_kind=ArtifactKind.REPORT,
        )


def test_queue_job_with_input_artifact_writes_payload_and_queued_job(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_source",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id\nS0001\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )

    queued = queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.TECHNICAL_STUDY,
        payload={
            "task": "hourly_detail",
            "scenario_id": "S0001",
            "result_id": "technical_result",
        },
        input_artifact_ids={"technical_summary": "technical_summary"},
        job_id="job_hourly_detail_1",
        progress_total=1,
        progress_message="hourly detail queued",
    )

    loaded_job = service.job_store.load_job(project.project_id, "study_1", "job_hourly_detail_1")
    input_artifact = service.result_store.load_artifact(
        project.project_id,
        "study_1",
        "job_input_job_hourly_detail_1",
    )
    payload = json.loads(service.result_store.read_artifact_payload(input_artifact).decode("utf-8"))
    audit_events = service.result_store.read_audit_log(project.project_id)

    assert queued.job == loaded_job
    assert queued.input_artifact == input_artifact
    assert queued.input_fingerprint == loaded_job.input_fingerprint
    assert loaded_job.status == JobStatus.QUEUED
    assert loaded_job.job_type == JobType.TECHNICAL_STUDY
    assert loaded_job.progress_total == 1
    assert loaded_job.progress_message == "hourly detail queued"
    assert loaded_job.input_artifact_ids == {
        "job_payload": "job_input_job_hourly_detail_1",
        "technical_summary": "technical_summary",
    }
    assert input_artifact.kind == ArtifactKind.JOB_INPUT
    assert input_artifact.retention_policy == ArtifactRetentionPolicy.EXPIRE
    assert input_artifact.expires_at is not None
    assert payload == {
        "task": "hourly_detail",
        "scenario_id": "S0001",
        "result_id": "technical_result",
    }
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.target_id == input_artifact.artifact_id
        and event.metadata["kind"] == ArtifactKind.JOB_INPUT.value
        and event.metadata["referenced_input_artifact_ids"] == {"technical_summary": "technical_summary"}
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.SUBMIT_JOB
        and event.job_id == "job_hourly_detail_1"
        and event.metadata["input_artifact_ids"] == loaded_job.input_artifact_ids
        for event in audit_events
    )


def test_queue_job_with_input_artifact_rejects_viewer_before_writing_payload(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
    )

    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        queue_job_with_input_artifact(
            access_service=service,
            actor_user_id="viewer",
            project_id=project.project_id,
            study_id="study_1",
            job_type=JobType.TECHNICAL_STUDY,
            payload={"task": "hourly_detail", "scenario_id": "S0001"},
            job_id="job_viewer_payload",
        )

    assert service.job_store.list_project_jobs(project.project_id) == []
    with pytest.raises(FileNotFoundError):
        service.result_store.load_artifact(
            project.project_id,
            "study_1",
            "job_input_job_viewer_payload",
        )


def test_queue_job_with_input_artifact_validates_external_artifacts_before_payload(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )

    with pytest.raises(FileNotFoundError):
        queue_job_with_input_artifact(
            access_service=service,
            actor_user_id="admin",
            project_id=project.project_id,
            study_id="study_1",
            job_type=JobType.ECONOMIC_STUDY,
            payload={"task": "economy", "result_id": "technical_result"},
            input_artifact_ids={"technical_summary": "missing_summary"},
            job_id="job_missing_input",
        )

    assert service.job_store.list_project_jobs(project.project_id) == []
    with pytest.raises(FileNotFoundError):
        service.result_store.load_artifact(
            project.project_id,
            "study_1",
            "job_input_job_missing_input",
        )


def test_persist_economic_study_result_writes_versioned_artifacts_and_record(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    economy = _economic_result()

    first = persist_economic_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        economic_result=economy,
    )
    second = persist_economic_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        economic_result=economy,
    )

    assert first.job.status == JobStatus.SUCCEEDED
    assert first.input_fingerprint == economic_input_fingerprint(economy)
    assert first.result_record.economy_summary_artifact_id == first.power_summary_artifact.artifact_id
    assert first.result_record.single_entity_summary_artifact_id == first.single_entity_summary_artifact.artifact_id
    assert first.result_record.recommendation_input_artifact_id == first.recommendation_input_artifact.artifact_id
    assert first.recommendation_input_artifact.kind == ArtifactKind.RECOMMENDATION_INPUT
    assert first.power_annual_cashflow_artifact is not None
    assert first.single_entity_annual_cashflow_artifact is not None
    assert first.power_annual_cashflow_artifact.kind == ArtifactKind.ANNUAL_CASHFLOW
    assert first.result_record.annual_cashflow_artifact_ids == {
        "power": first.power_annual_cashflow_artifact.artifact_id,
        "single_entity": first.single_entity_annual_cashflow_artifact.artifact_id,
    }
    assert first.result_record.result_id != second.result_record.result_id
    loaded_record = service.result_store.load_result_record(project.project_id, "study_1", first.result_record.result_id)
    assert loaded_record.recommendation_input_artifact_id == first.recommendation_input_artifact.artifact_id
    assert loaded_record.annual_cashflow_artifact_ids == first.result_record.annual_cashflow_artifact_ids
    power_payload = service.result_store.read_artifact_payload(first.power_summary_artifact).decode("utf-8")
    single_entity_payload = service.result_store.read_artifact_payload(first.single_entity_summary_artifact).decode("utf-8")
    recommendation_input_payload = json.loads(
        service.result_store.read_artifact_payload(first.recommendation_input_artifact).decode("utf-8")
    )
    with ZipFile(BytesIO(service.result_store.read_artifact_payload(first.power_annual_cashflow_artifact))) as archive:
        assert archive.namelist() == ["S0001.csv"]
        assert "net_cash_flow" in archive.read("S0001.csv").decode("utf-8")
    assert "firr" in power_payload
    assert "single_entity_firr_pre_tax" in single_entity_payload
    assert recommendation_input_payload["load_side_avoided_charge_price"] == 0.5
    assert recommendation_input_payload["green_power_settlement_price_with_vat"] == 0.4
    assert recommendation_input_payload["avoided_grid_params"]["net_avoided_grid_cost_price"] is None
    assert "economic_params" in recommendation_input_payload


def test_persist_recommendation_study_result_writes_portfolio_and_detail(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    recommendation = _recommendation_result()

    persisted = persist_recommendation_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        recommendation_result=recommendation,
    )

    assert persisted.job.status == JobStatus.SUCCEEDED
    assert persisted.input_fingerprint == recommendation_result_fingerprint(recommendation)
    assert persisted.portfolio_artifact.kind == ArtifactKind.RECOMMENDATION_PORTFOLIO
    assert persisted.result_record.recommendation_artifact_id == persisted.portfolio_artifact.artifact_id
    assert persisted.result_record.report_artifact_ids == {
        "load_side_detail": persisted.load_side_detail_artifact.artifact_id
    }
    portfolio_payload = service.result_store.read_artifact_payload(persisted.portfolio_artifact).decode("utf-8")
    detail_payload = service.result_store.read_artifact_payload(persisted.load_side_detail_artifact).decode("utf-8")
    assert "same_entity_firr_best" in portfolio_payload
    assert "load_side_tradable_benefit" in detail_payload
