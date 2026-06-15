import pandas as pd
import pytest

from green_direct.batch.batch_runner import BatchResult
from green_direct.economy import EconomicParams
from green_direct.models.diagnostics import InputDiagnostics
from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    JobStatus,
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
    persist_recommendation_study_result,
    persist_technical_study_result,
    recommendation_result_fingerprint,
    technical_input_fingerprint,
)
from green_direct.services.study_runner import (
    EconomicStudyResult,
    RecommendationInputSnapshot,
    RecommendationStudyResult,
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


def _economic_result() -> EconomicStudyResult:
    return EconomicStudyResult(
        power_summary=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "firr": [0.08],
                "fnpv": [12.5],
            }
        ),
        power_annual_cashflows={},
        single_entity_summary=pd.DataFrame(
            {
                "scenario_id": ["S0001"],
                "single_entity_firr_pre_tax": [0.11],
                "annual_self_use_saving": [18.0],
            }
        ),
        single_entity_annual_cashflows={},
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
    )

    loaded_job = service.job_store.load_job(project.project_id, "study_1", persisted.job.job_id)
    summary_artifact = service.result_store.load_artifact(project.project_id, "study_1", "technical_summary")
    config_artifact = service.result_store.load_artifact(project.project_id, "study_1", "config_snapshot")
    result_record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")

    assert loaded_job.status == JobStatus.SUCCEEDED
    assert loaded_job.input_fingerprint == technical_input_fingerprint(technical_result)
    assert summary_artifact.kind == ArtifactKind.TECHNICAL_SUMMARY
    assert config_artifact.kind == ArtifactKind.CONFIG_SNAPSHOT
    assert service.result_store.read_artifact_payload(summary_artifact).decode("utf-8").startswith("scenario_id")
    assert '"study_id": "study_1"' in service.result_store.read_artifact_payload(config_artifact).decode("utf-8")
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
    assert first.result_record.result_id != second.result_record.result_id
    power_payload = service.result_store.read_artifact_payload(first.power_summary_artifact).decode("utf-8")
    single_entity_payload = service.result_store.read_artifact_payload(first.single_entity_summary_artifact).decode("utf-8")
    assert "firr" in power_payload
    assert "single_entity_firr_pre_tax" in single_entity_payload


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
