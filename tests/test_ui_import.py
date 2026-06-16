from concurrent.futures import Future
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd
import pytest


def test_streamlit_app_imports():
    import green_direct.ui.app as app

    assert callable(app.main)


def test_workflow_page_normalizes_legacy_and_unknown_values():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self, page):
            self.session_state = {"workflow_page": page}

    legacy = DummyStreamlit("技术仿真")
    assert app._normalize_workflow_page(legacy) == "方案仿真"
    assert legacy.session_state["workflow_page"] == "方案仿真"

    unknown = DummyStreamlit("不存在的页面")
    assert app._normalize_workflow_page(unknown) == "欢迎页"
    assert unknown.session_state["workflow_page"] == "欢迎页"

    old_recommendation = DummyStreamlit("方案推荐及图表概览")
    assert app._normalize_workflow_page(old_recommendation) == "方案推荐"
    assert old_recommendation.session_state["workflow_page"] == "方案推荐"


def test_workflow_pages_split_recommendation_and_charts():
    import green_direct.ui.app as app

    assert app.WORKFLOW_PAGES == [
        "欢迎页",
        "方案仿真",
        "经济性测算",
        "方案推荐",
        "图表概览",
        "图表下载和报告生成",
    ]
    assert app.WORKFLOW_PAGE_META["图表下载和报告生成"]["index"] == "06"


def test_runtime_snapshot_round_trips_session_state(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    snapshot_path = tmp_path / "latest_session_snapshot.pkl"
    monkeypatch.setenv(app.RUNTIME_SNAPSHOT_ENV, "1")
    monkeypatch.setattr(app, "RUNTIME_STATE_DIR", tmp_path)
    monkeypatch.setattr(app, "LATEST_SESSION_SNAPSHOT_PATH", snapshot_path)

    class DummyStreamlit:
        def __init__(self, state):
            self.session_state = state

    batch_result = SimpleNamespace(summary=pd.DataFrame({"scenario_id": ["S0001"]}), hourly_details={"S0001": pd.DataFrame()})
    source = DummyStreamlit(
        {
            "batch_result": batch_result,
            "config_snapshot": {"demo": True},
            "recommendation_v1_inputs": {"power_side_firr_threshold": 0.07},
            app.PROJECT_PRICE_CURVE_DATA_KEY: read_price_curve("samples/price_curve_template_down_grid.csv"),
            app.PROJECT_PRICE_CURVE_META_KEY: {"source_name": "price_curve_template_down_grid.csv"},
        }
    )

    app._save_runtime_snapshot(source)

    target = DummyStreamlit({app.TECHNICAL_STUDY_INPUT_KEY: object()})
    restored = app._restore_runtime_snapshot_if_needed(target)

    assert restored is True
    assert target.session_state["batch_result"] is not None
    assert target.session_state["config_snapshot"] == {"demo": True}
    assert app.TECHNICAL_STUDY_INPUT_KEY not in target.session_state
    assert app.PROJECT_PRICE_CURVE_DATA_KEY not in target.session_state
    assert app.PROJECT_PRICE_CURVE_META_KEY not in target.session_state
    assert "已从项目本地快照恢复" in target.session_state["_runtime_restore_notice"]


def test_runtime_snapshot_is_disabled_by_default(tmp_path, monkeypatch):
    import green_direct.ui.app as app

    snapshot_path = tmp_path / "latest_session_snapshot.pkl"
    monkeypatch.delenv(app.RUNTIME_SNAPSHOT_ENV, raising=False)
    monkeypatch.setattr(app, "RUNTIME_STATE_DIR", tmp_path)
    monkeypatch.setattr(app, "LATEST_SESSION_SNAPSHOT_PATH", snapshot_path)

    class DummyStreamlit:
        def __init__(self, state):
            self.session_state = state

    source = DummyStreamlit(
        {
            "batch_result": SimpleNamespace(
                summary=pd.DataFrame({"scenario_id": ["S0001"]}),
                hourly_details={"S0001": pd.DataFrame()},
            )
        }
    )

    app._save_runtime_snapshot(source)
    restored = app._restore_runtime_snapshot_if_needed(DummyStreamlit({}))

    assert restored is False
    assert not snapshot_path.exists()


def test_runtime_snapshot_is_disabled_when_pilot_auth_is_enabled(tmp_path, monkeypatch):
    import green_direct.ui.app as app

    snapshot_path = tmp_path / "latest_session_snapshot.pkl"
    monkeypatch.setenv(app.RUNTIME_SNAPSHOT_ENV, "1")
    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setattr(app, "RUNTIME_STATE_DIR", tmp_path)
    monkeypatch.setattr(app, "LATEST_SESSION_SNAPSHOT_PATH", snapshot_path)

    class DummyStreamlit:
        def __init__(self, state):
            self.session_state = state

    app._save_runtime_snapshot(
        DummyStreamlit({"batch_result": SimpleNamespace(summary=pd.DataFrame({"scenario_id": ["S0001"]}))})
    )

    assert app._restore_runtime_snapshot_if_needed(DummyStreamlit({})) is False
    assert not snapshot_path.exists()


def test_pilot_auth_gate_is_disabled_by_default(monkeypatch):
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {}

    monkeypatch.delenv(app.PILOT_AUTH_ENV, raising=False)

    assert app._pilot_auth_enabled() is False
    assert app._ensure_pilot_authenticated(DummyStreamlit()) is True


def test_pilot_authenticated_user_validates_local_session(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import User
    from green_direct.services import LocalPilotAuth, LocalPilotRegistry, LocalResultStore

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=LocalResultStore(tmp_path))
    auth.set_password(user_id="admin", password="admin-password")
    session = auth.login(login_name="admin@example.local", password="admin-password")

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_SESSION_ID_KEY: session.session_id,
                app.PILOT_SESSION_TOKEN_KEY: session.token,
            }

    dummy = DummyStreamlit()
    user = app._pilot_authenticated_user(dummy)

    assert user.user_id == "admin"
    assert dummy.session_state[app.PILOT_USER_ID_KEY] == "admin"
    assert dummy.session_state[app.PILOT_USER_DISPLAY_KEY] == "Admin"
    assert dummy.session_state[app.PILOT_LOGIN_NAME_KEY] == "admin@example.local"


def test_pilot_invalid_session_clears_work_state(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import User
    from green_direct.services import LocalPilotAuth, LocalPilotRegistry, LocalResultStore

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=LocalResultStore(tmp_path))
    auth.set_password(user_id="admin", password="admin-password")
    session = auth.login(login_name="admin@example.local", password="admin-password")

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_SESSION_ID_KEY: session.session_id,
                app.PILOT_SESSION_TOKEN_KEY: "wrong-token",
                "batch_result": object(),
                "download_payloads": {"demo": True},
            }

    dummy = DummyStreamlit()

    assert app._pilot_authenticated_user(dummy) is None
    assert app.PILOT_SESSION_ID_KEY not in dummy.session_state
    assert app.PILOT_SESSION_TOKEN_KEY not in dummy.session_state
    assert "batch_result" not in dummy.session_state
    assert "download_payloads" not in dummy.session_state
    assert dummy.session_state[app.WORKFLOW_PAGE_KEY] == app.WORKFLOW_PAGES[0]
    assert app.PILOT_LOGIN_NOTICE_KEY in dummy.session_state


def test_pilot_project_switch_clears_work_state():
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import Project, ProjectMembership, ProjectRole

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_ACTIVE_PROJECT_ID_KEY: "project_1",
                "batch_result": object(),
                "download_payloads": {"old": True},
                app.WORKFLOW_PAGE_KEY: app.WORKFLOW_PAGES[2],
            }

    dummy = DummyStreamlit()
    app._activate_pilot_project(
        dummy,
        project=Project("project_2", "Second project"),
        membership=ProjectMembership("m2", "project_2", "admin", ProjectRole.ADMIN),
        clear_work_state=True,
    )

    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_ID_KEY] == "project_2"
    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_NAME_KEY] == "Second project"
    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_ROLE_KEY] == "admin"
    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY] is True
    assert "batch_result" not in dummy.session_state
    assert "download_payloads" not in dummy.session_state
    assert dummy.session_state[app.WORKFLOW_PAGE_KEY] == app.WORKFLOW_PAGES[0]


def test_pilot_project_role_change_to_viewer_clears_work_state_and_blocks_submit(monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import Project, ProjectMembership, ProjectRole

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_ACTIVE_PROJECT_ID_KEY: "project_1",
                app.PILOT_ACTIVE_PROJECT_ROLE_KEY: "analyst",
                "batch_result": object(),
                app.WORKFLOW_PAGE_KEY: app.WORKFLOW_PAGES[1],
            }

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    dummy = DummyStreamlit()
    app._activate_pilot_project(
        dummy,
        project=Project("project_1", "Internal pilot project"),
        membership=ProjectMembership(
            "m1",
            "project_1",
            "viewer",
            ProjectRole.VIEWER,
            can_export_artifacts=False,
        ),
        clear_work_state=False,
    )

    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_ROLE_KEY] == "viewer"
    assert dummy.session_state[app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY] is False
    assert "batch_result" not in dummy.session_state
    assert dummy.session_state[app.WORKFLOW_PAGE_KEY] == app.WORKFLOW_PAGES[0]
    assert app._current_pilot_project_can_submit_jobs(dummy) is False
    assert app._current_pilot_project_can_export_artifacts(dummy) is False


def test_pilot_technical_result_helper_persists_and_attaches_refs(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.diagnostics import InputDiagnostics
    from green_direct.models.pilot_backend import ArtifactKind, Project, User
    from green_direct.services.study_runner import StudyResult, TechnicalStudyInput, TechnicalStudyResult

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    technical_result = TechnicalStudyResult(
        study_id="study_ui",
        batch_result=BatchResult(
            summary=pd.DataFrame({"scenario_id": ["S0001"], "green_load_rate": [0.4]}),
            hourly_details={},
            errors=pd.DataFrame(),
            warnings=[],
            scenario_count=1,
        ),
        input_diagnostics=InputDiagnostics(),
        config_snapshot={"study_id": "study_ui", "scenario_grid": {"pv_capacity": [5]}},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
            }

    dummy = DummyStreamlit()
    technical_input = TechnicalStudyInput(
        load_source=b"timestamp,load\n2026-01-01 00:00:00,1\n",
        pv_source=b"timestamp,pv\n2026-01-01 00:00:00,0.5\n",
        wind_source=b"timestamp,wind\n2026-01-01 00:00:00,0.3\n",
        load_time_col="timestamp",
        load_value_col="load",
        pv_time_col="timestamp",
        pv_value_col="pv",
        wind_time_col="timestamp",
        wind_value_col="wind",
        scenario_grid={"pv_capacity": {"start": 5, "end": 5, "step": 1}},
    )

    persisted = app._persist_pilot_technical_result_if_enabled(dummy, technical_result, technical_input)
    study_result = app._study_result_with_pilot_refs(StudyResult.from_technical(technical_result), persisted)

    assert persisted is not None
    assert study_result.result_store_refs["project_id"] == project.project_id
    assert study_result.result_store_refs["technical_job_id"] == persisted.job.job_id
    assert study_result.result_store_refs["technical_summary_artifact_id"] == "technical_summary"
    assert study_result.result_store_refs["config_snapshot_artifact_id"] == "config_snapshot"
    assert study_result.result_store_refs["input_curve_load_artifact_id"] == "input_curve_load"
    assert app.PILOT_RESULT_STORE_NOTICE_KEY in dummy.session_state
    assert (
        app._pilot_access_service()
        .result_store.load_artifact(project.project_id, "study_ui", "config_snapshot")
        .kind
        == ArtifactKind.CONFIG_SNAPSHOT
    )


def test_pilot_economy_and_recommendation_helpers_persist_refs_and_dedupe(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
    from green_direct.models.pilot_backend import JobType, Project, User
    from green_direct.services.study_runner import (
        EconomicStudyResult,
        RecommendationInputSnapshot,
        RecommendationStudyResult,
        StudyResult,
    )

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                "study_result": StudyResult(study_id="study_ui"),
            }

    dummy = DummyStreamlit()
    economy = EconomicStudyResult(
        power_summary=pd.DataFrame({"scenario_id": ["S0001"], "firr": [0.08]}),
        power_annual_cashflows={},
        single_entity_summary=pd.DataFrame({"scenario_id": ["S0001"], "single_entity_firr_pre_tax": [0.11]}),
        single_entity_annual_cashflows={},
        recommendation_inputs=RecommendationInputSnapshot(
            economic_params=EconomicParams(),
            load_side_avoided_charge_price=0.50,
            green_power_settlement_price_with_vat=0.40,
        ),
    )
    recommendation = RecommendationStudyResult(
        portfolio=pd.DataFrame({"scenario_id": ["S0001"], "seat_labels": ["same_entity_firr_best"]}),
        load_side_detail=pd.DataFrame({"scenario_id": ["S0001"], "load_side_tradable_benefit": [10.0]}),
    )

    persisted_economy = app._persist_pilot_economic_result_if_enabled(dummy, economy)
    study_result = app._study_result_with_pilot_economy_refs(
        dummy.session_state["study_result"],
        persisted_economy,
    )
    dummy.session_state["study_result"] = study_result
    persisted_recommendation = app._persist_pilot_recommendation_result_if_enabled(dummy, recommendation)
    duplicate_recommendation = app._persist_pilot_recommendation_result_if_enabled(dummy, recommendation)
    study_result = app._study_result_with_pilot_recommendation_refs(study_result, persisted_recommendation)

    assert persisted_economy is not None
    assert persisted_recommendation is not None
    assert duplicate_recommendation is None
    assert study_result.result_store_refs["economy_job_id"] == persisted_economy.job.job_id
    assert (
        study_result.result_store_refs["recommendation_input_artifact_id"]
        == persisted_economy.recommendation_input_artifact.artifact_id
    )
    assert study_result.result_store_refs["recommendation_job_id"] == persisted_recommendation.job.job_id
    jobs = app._pilot_access_service().job_store.list_project_jobs(project.project_id)
    assert len(jobs) == 2
    assert {job.job_type for job in jobs} == {JobType.ECONOMIC_STUDY, JobType.RECOMMENDATION}


def test_pilot_project_activity_frames_summarize_jobs_and_results():
    from datetime import datetime, timezone

    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import Job, JobStatus, JobType, StudyResultRecord

    earlier = datetime(2026, 6, 15, 1, tzinfo=timezone.utc)
    later = datetime(2026, 6, 15, 2, tzinfo=timezone.utc)

    older_job = Job(
        job_id="job_old",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="analyst",
        job_type=JobType.TECHNICAL_STUDY,
        status=JobStatus.SUCCEEDED,
        queued_at=earlier,
    )
    newer_job = Job(
        job_id="job_new",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="analyst",
        job_type=JobType.RECOMMENDATION,
        status=JobStatus.RUNNING,
        progress_current=1,
        progress_total=2,
        queued_at=later,
        started_at=earlier,
        worker_id="worker_1",
        last_heartbeat_at=earlier,
    )
    older_result = StudyResultRecord(
        result_id="technical_result",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_old",
        technical_summary_artifact_id="technical_summary",
        created_at=earlier,
    )
    newer_result = StudyResultRecord(
        result_id="recommendation_result_job_new",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_new",
        recommendation_artifact_id="recommendation_portfolio_job_new",
        report_artifact_ids={"load_side_detail": "recommendation_load_side_detail_job_new"},
        created_at=later,
    )

    job_frame = app._pilot_job_history_frame([older_job, newer_job])
    status_frame = app._pilot_job_status_frame(
        [older_job, newer_job],
        now=later,
        stale_after_seconds=3600,
    )
    result_frame = app._pilot_result_history_frame([older_result, newer_result])

    assert job_frame.iloc[0]["job_id"] == "job_new"
    assert job_frame.iloc[0]["进度"] == "1/2"
    assert status_frame.iloc[0]["worker"] == "worker_1"
    assert status_frame.iloc[0]["最后心跳"] == "2026-06-15 01:00"
    assert status_frame.iloc[0]["超时"] == "是"
    assert status_frame.iloc[1]["超时"] == "-"
    assert result_frame.iloc[0]["result_id"] == "recommendation_result_job_new"
    assert result_frame.iloc[0]["类型"] == "recommendation"
    assert result_frame.iloc[0]["产物数"] == 2


def test_pilot_result_history_frame_surfaces_pinned_records():
    from datetime import datetime, timezone

    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import StudyResultRecord

    earlier = datetime(2026, 6, 15, 1, tzinfo=timezone.utc)
    later = datetime(2026, 6, 15, 2, tzinfo=timezone.utc)
    pinned_older = StudyResultRecord(
        result_id="technical_result",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_old",
        technical_summary_artifact_id="technical_summary",
        created_at=earlier,
        pinned_at=later,
        pinned_by_user_id="admin",
        label="report candidate",
    )
    unpinned_newer = StudyResultRecord(
        result_id="recommendation_result_job_new",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_new",
        recommendation_artifact_id="recommendation_portfolio_job_new",
        created_at=later,
    )

    result_frame = app._pilot_result_history_frame([unpinned_newer, pinned_older])

    assert result_frame.iloc[0]["result_id"] == "technical_result"
    assert result_frame.iloc[0]["标记"] == "重点"
    assert result_frame.iloc[0]["备注"] == "report candidate"


def test_pilot_active_job_helpers_filter_and_gate_cancel():
    from datetime import datetime, timezone

    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import Job, JobStatus, JobType, ProjectRole

    earlier = datetime(2026, 6, 15, 1, tzinfo=timezone.utc)
    later = datetime(2026, 6, 15, 2, tzinfo=timezone.utc)
    queued_job = Job(
        job_id="job_queued",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="analyst",
        job_type=JobType.TECHNICAL_STUDY,
        status=JobStatus.QUEUED,
        queued_at=earlier,
    )
    running_job = Job(
        job_id="job_running",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="analyst",
        job_type=JobType.RECOMMENDATION,
        status=JobStatus.RUNNING,
        progress_current=1,
        progress_total=2,
        queued_at=later,
    )
    succeeded_job = Job(
        job_id="job_done",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="other_analyst",
        job_type=JobType.ECONOMIC_STUDY,
        status=JobStatus.SUCCEEDED,
        queued_at=later,
        finished_at=later,
    )

    active_jobs = app._active_pilot_jobs([queued_job, succeeded_job, running_job])

    assert [job.job_id for job in active_jobs] == ["job_running", "job_queued"]
    assert "job_running / recommendation / running / 1/2 / analyst" == app._pilot_job_option_label(running_job)
    assert app._can_cancel_pilot_job(running_job, actor_user_id="analyst", project_role=ProjectRole.ANALYST.value)
    assert not app._can_cancel_pilot_job(
        running_job,
        actor_user_id="other_analyst",
        project_role=ProjectRole.ANALYST.value,
    )
    assert app._can_cancel_pilot_job(
        running_job,
        actor_user_id="admin",
        project_role=ProjectRole.ADMIN.value,
    )
    assert not app._can_cancel_pilot_job(
        succeeded_job,
        actor_user_id="admin",
        project_role=ProjectRole.ADMIN.value,
    )
    assert not app._can_cancel_pilot_job(
        running_job,
        actor_user_id="viewer",
        project_role=ProjectRole.VIEWER.value,
    )


def test_pilot_history_artifact_refs_and_download_use_access_service(tmp_path):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, AuditAction, Project, StudyResultRecord, User
    from green_direct.services import LocalJobStore, LocalPilotRegistry, LocalResultStore, PilotAccessService

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    access = PilotAccessService(
        registry=registry,
        job_store=LocalJobStore(tmp_path),
        result_store=result_store,
    )
    registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    artifact = result_store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id\nS0001\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    record = StudyResultRecord(
        result_id="technical_result",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id=artifact.artifact_id,
        report_artifact_ids={"markdown": "brief_report", "chart_html": "chart_html_zip"},
    )

    assert app._pilot_result_artifact_refs(record) == [
        ("技术汇总", "technical_summary"),
        ("图表 HTML 包", "chart_html_zip"),
        ("Markdown 报告", "brief_report"),
    ]

    download = app._pilot_load_artifact_download(
        access,
        actor_user_id="admin",
        record=record,
        artifact_id="technical_summary",
    )

    assert download["payload"] == b"scenario_id\nS0001\n"
    assert download["file_name"] == "technical_summary.csv"
    assert download["mime"] == "text/csv"
    assert result_store.read_audit_log("project_1")[-1].action == AuditAction.DOWNLOAD_ARTIFACT


def test_pilot_restore_technical_summary_rebuilds_summary_only_session(tmp_path):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, Project, StudyResultRecord, User
    from green_direct.services import LocalJobStore, LocalPilotRegistry, LocalResultStore, PilotAccessService, StudyResult

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    access = PilotAccessService(
        registry=registry,
        job_store=LocalJobStore(tmp_path),
        result_store=result_store,
    )
    registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    result_store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,green_load_rate\nS0001,0.5\nS0002,0.6\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    result_store.store_artifact(
        artifact_id="config_snapshot",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.CONFIG_SNAPSHOT,
        payload=(
            '{"study_id":"study_1","scenario_grid":{"pv_capacity":[5]},'
            '"input_artifact_ids":{"load":"input_curve_load"}}'
        ),
        filename="config_snapshot.json",
        content_type="application/json",
    )
    record = StudyResultRecord(
        result_id="technical_result",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id="technical_summary",
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "economy_v1_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                app.TECHNICAL_STUDY_INPUT_KEY: object(),
                app.PROJECT_PRICE_CURVE_DATA_KEY: object(),
                app.PILOT_HISTORY_ARTIFACT_DOWNLOADS_KEY: {"old": b"payload"},
            }

    dummy = DummyStreamlit()
    restored = app._pilot_restore_technical_summary_to_session(
        dummy,
        access=access,
        actor_user_id="admin",
        record=record,
    )

    batch_result = dummy.session_state["batch_result"]
    assert list(batch_result.summary["scenario_id"]) == ["S0001", "S0002"]
    assert batch_result.hourly_details == {}
    assert batch_result.scenario_count == 2
    assert dummy.session_state["config_snapshot"]["scenario_grid"] == {"pv_capacity": [5]}
    assert dummy.session_state["config_snapshot"]["restored_from_result_store"]["summary_only"] is True
    assert isinstance(dummy.session_state["study_result"], StudyResult)
    assert dummy.session_state["study_result"].result_store_refs["technical_job_id"] == "job_1"
    assert dummy.session_state["study_result"].result_store_refs["input_curve_load_artifact_id"] == "input_curve_load"
    assert "economy_v1_result" not in dummy.session_state
    assert app.TECHNICAL_STUDY_INPUT_KEY not in dummy.session_state
    assert app.PROJECT_PRICE_CURVE_DATA_KEY not in dummy.session_state
    assert app.PILOT_HISTORY_ARTIFACT_DOWNLOADS_KEY not in dummy.session_state
    assert restored["row_count"] == 2


def test_pilot_restore_economy_summary_uses_view_permission_without_export(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
    from green_direct.models.pilot_backend import ArtifactKind, AuditAction, Project, ProjectRole, StudyResultRecord, User

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    access.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_tech",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,green_load_rate\nS0001,0.5\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="config_snapshot",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_tech",
        kind=ArtifactKind.CONFIG_SNAPSHOT,
        payload='{"study_id":"study_1","scenario_grid":{"pv_capacity":[5]}}',
        filename="config_snapshot.json",
        content_type="application/json",
    )
    access.result_store.store_artifact(
        artifact_id="economy_summary_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_economy",
        kind=ArtifactKind.ECONOMY_SUMMARY,
        payload="scenario_id,firr\nS0001,0.08\n",
        filename="power_economy_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="single_entity_summary_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_economy",
        kind=ArtifactKind.ECONOMY_SUMMARY,
        payload="scenario_id,single_entity_firr_pre_tax\nS0001,0.11\n",
        filename="single_entity_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="recommendation_inputs_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_economy",
        kind=ArtifactKind.RECOMMENDATION_INPUT,
        payload=json.dumps(
            {
                "economic_params": {
                    "operation_years": 20,
                    "other_operating_revenues": [
                        {
                            "name": "容量补贴",
                            "amount_with_vat": 1.2,
                            "vat_rate": 0.06,
                            "active_rule": "specific_years",
                            "specific_years": [1, 2],
                        }
                    ],
                },
                "load_side_avoided_charge_price": 0.51,
                "green_power_settlement_price_with_vat": 0.41,
                "environmental_value_per_kwh": 0.02,
                "min_power_side_acceptable_firr": 0.06,
            },
            ensure_ascii=False,
        ),
        filename="recommendation_inputs.json",
        content_type="application/json",
    )
    power_cashflows = BytesIO()
    with ZipFile(power_cashflows, "w") as archive:
        archive.writestr("S0001.csv", "scenario_id,year,net_cash_flow\nS0001,0,-100\nS0001,1,18\n")
    single_entity_cashflows = BytesIO()
    with ZipFile(single_entity_cashflows, "w") as archive:
        archive.writestr("S0001.csv", "scenario_id,year,net_cash_flow\nS0001,0,-100\nS0001,1,22\n")
    access.result_store.store_artifact(
        artifact_id="power_annual_cashflows_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_economy",
        kind=ArtifactKind.ANNUAL_CASHFLOW,
        payload=power_cashflows.getvalue(),
        filename="power_annual_cashflows.zip",
        content_type="application/zip",
    )
    access.result_store.store_artifact(
        artifact_id="single_entity_annual_cashflows_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_economy",
        kind=ArtifactKind.ANNUAL_CASHFLOW,
        payload=single_entity_cashflows.getvalue(),
        filename="single_entity_annual_cashflows.zip",
        content_type="application/zip",
    )
    technical_record = StudyResultRecord(
        result_id="technical_result",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_tech",
        technical_summary_artifact_id="technical_summary",
    )
    economy_record = StudyResultRecord(
        result_id="economy_result_job_1",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_economy",
        economy_summary_artifact_id="economy_summary_job_1",
        single_entity_summary_artifact_id="single_entity_summary_job_1",
        recommendation_input_artifact_id="recommendation_inputs_job_1",
        annual_cashflow_artifact_ids={
            "power": "power_annual_cashflows_job_1",
            "single_entity": "single_entity_annual_cashflows_job_1",
        },
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "analyst",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY: False,
                "recommendation_v1_inputs": {"old": True},
                "download_payloads": {"old": b"payload"},
            }

    dummy = DummyStreamlit()
    app._pilot_restore_technical_summary_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=technical_record,
    )
    mismatched_record = StudyResultRecord(
        result_id="economy_result_job_2",
        project_id=project.project_id,
        study_id="study_2",
        created_by_job_id="job_economy",
        economy_summary_artifact_id="economy_summary_job_1",
    )
    with pytest.raises(ValueError, match="同一 study"):
        app._pilot_restore_economy_summary_to_session(
            dummy,
            access=access,
            actor_user_id="analyst",
            record=mismatched_record,
        )
    assert "economy_v1_result" not in dummy.session_state
    mismatched_project_record = StudyResultRecord(
        result_id="economy_result_project_2",
        project_id="project_2",
        study_id="study_1",
        created_by_job_id="job_economy",
        economy_summary_artifact_id="economy_summary_job_1",
    )
    with pytest.raises(ValueError, match="所属项目"):
        app._pilot_restore_economy_summary_to_session(
            dummy,
            access=access,
            actor_user_id="analyst",
            record=mismatched_project_record,
        )
    assert "economy_v1_result" not in dummy.session_state

    restored = app._pilot_restore_economy_summary_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=economy_record,
    )

    assert restored["row_count"] == 1
    assert dummy.session_state["economy_v1_result"]["summary"]["firr"].tolist() == [0.08]
    assert dummy.session_state["economy_v1_result"]["annual_cashflows"]["S0001"]["net_cash_flow"].tolist() == [
        -100,
        18,
    ]
    assert dummy.session_state["economy_v1_result"]["price_mode"] == "restored_summary"
    assert dummy.session_state["single_entity_economy_result"]["summary"]["single_entity_firr_pre_tax"].tolist() == [
        0.11
    ]
    assert dummy.session_state["single_entity_economy_result"]["annual_cashflows"]["S0001"][
        "net_cash_flow"
    ].tolist() == [-100, 22]
    recommendation_inputs = dummy.session_state["recommendation_v1_inputs"]
    assert recommendation_inputs["load_side_avoided_charge_price"] == 0.51
    assert recommendation_inputs["green_power_settlement_price_with_vat"] == 0.41
    assert recommendation_inputs["environmental_value_per_kwh"] == 0.02
    assert recommendation_inputs["min_power_side_acceptable_firr"] == 0.06
    assert isinstance(recommendation_inputs["economic_params"], EconomicParams)
    assert isinstance(recommendation_inputs["avoided_grid_params"], AvoidedGridPurchaseParams)
    assert recommendation_inputs["avoided_grid_params"].net_avoided_grid_cost_price == 0.51
    assert recommendation_inputs["economic_params"].operation_years == 20
    assert recommendation_inputs["economic_params"].other_operating_revenues[0].specific_years == (1, 2)
    assert "download_payloads" not in dummy.session_state
    assert dummy.session_state["study_result"].result_store_refs["economy_result_id"] == "economy_result_job_1"
    assert dummy.session_state["study_result"].result_store_refs["power_economy_summary_artifact_id"] == (
        "economy_summary_job_1"
    )
    assert dummy.session_state["study_result"].result_store_refs["recommendation_input_artifact_id"] == (
        "recommendation_inputs_job_1"
    )
    assert dummy.session_state["study_result"].result_store_refs["power_annual_cashflow_artifact_id"] == (
        "power_annual_cashflows_job_1"
    )
    assert dummy.session_state["study_result"].result_store_refs["single_entity_annual_cashflow_artifact_id"] == (
        "single_entity_annual_cashflows_job_1"
    )
    audit_actions = [event.action for event in access.result_store.read_audit_log(project.project_id)]
    assert AuditAction.VIEW_ARTIFACT in audit_actions
    assert AuditAction.DOWNLOAD_ARTIFACT not in audit_actions


def test_pilot_restore_recommendation_uses_view_permission_without_export(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, AuditAction, Project, ProjectRole, StudyResultRecord, User
    from green_direct.services import RecommendationStudyResult

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    access.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_tech",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,green_load_rate\nS0001,0.5\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="recommendation_portfolio_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_recommendation",
        kind=ArtifactKind.RECOMMENDATION_PORTFOLIO,
        payload=(
            "scenario_id,recommendation_rank,recommendation_labels,recommendation_status,recommendation_reason\n"
            "S0001,1,工程代表,selected,历史推荐\n"
        ),
        filename="recommendation_portfolio.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="recommendation_load_side_detail_job_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_recommendation",
        kind=ArtifactKind.RECOMMENDATION_PORTFOLIO,
        payload="scenario_id,load_side_annual_benefit\nS0001,123.4\n",
        filename="recommendation_load_side_detail.csv",
        content_type="text/csv",
    )
    technical_record = StudyResultRecord(
        result_id="technical_result",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_tech",
        technical_summary_artifact_id="technical_summary",
    )
    recommendation_record = StudyResultRecord(
        result_id="recommendation_result_job_1",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_recommendation",
        recommendation_artifact_id="recommendation_portfolio_job_1",
        report_artifact_ids={"load_side_detail": "recommendation_load_side_detail_job_1"},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "analyst",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY: False,
                "recommendation_v1_inputs": {"old": True},
                "download_payloads": {"old": b"payload"},
                "export_report_scenario": "S9999",
            }

    dummy = DummyStreamlit()
    app._pilot_restore_technical_summary_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=technical_record,
    )
    mismatched_study_record = StudyResultRecord(
        result_id="recommendation_result_job_2",
        project_id=project.project_id,
        study_id="study_2",
        created_by_job_id="job_recommendation",
        recommendation_artifact_id="recommendation_portfolio_job_1",
    )
    with pytest.raises(ValueError, match="同一 study"):
        app._pilot_restore_recommendation_to_session(
            dummy,
            access=access,
            actor_user_id="analyst",
            record=mismatched_study_record,
        )
    mismatched_project_record = StudyResultRecord(
        result_id="recommendation_result_project_2",
        project_id="project_2",
        study_id="study_1",
        created_by_job_id="job_recommendation",
        recommendation_artifact_id="recommendation_portfolio_job_1",
    )
    with pytest.raises(ValueError, match="所属项目"):
        app._pilot_restore_recommendation_to_session(
            dummy,
            access=access,
            actor_user_id="analyst",
            record=mismatched_project_record,
        )

    restored = app._pilot_restore_recommendation_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=recommendation_record,
    )

    recommendation_result = dummy.session_state["recommendation_v1_result"]
    assert isinstance(recommendation_result, RecommendationStudyResult)
    assert restored["row_count"] == 1
    assert recommendation_result.portfolio["recommendation_reason"].tolist() == ["历史推荐"]
    assert recommendation_result.load_side_detail["load_side_annual_benefit"].tolist() == [123.4]
    assert "recommendation_v1_inputs" not in dummy.session_state
    assert "download_payloads" not in dummy.session_state
    assert "export_report_scenario" not in dummy.session_state
    assert dummy.session_state["study_result"].result_store_refs["recommendation_result_id"] == (
        "recommendation_result_job_1"
    )
    _, display_recommendation, error_message = app._build_recommendation_result_for_display(
        dummy,
        dummy.session_state["batch_result"].summary,
    )
    assert error_message is None
    assert display_recommendation is recommendation_result
    assert app._workflow_step_done(dummy, "方案推荐") is True
    audit_actions = [event.action for event in access.result_store.read_audit_log(project.project_id)]
    assert audit_actions.count(AuditAction.VIEW_ARTIFACT) >= 2
    assert AuditAction.DOWNLOAD_ARTIFACT not in audit_actions


def test_pilot_restore_summary_can_load_hourly_artifact_for_view_without_export(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, AuditAction, Project, ProjectRole, StudyResultRecord, User

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    access.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,green_load_rate\nS0001,0.5\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="hourly_detail_S0001",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.HOURLY_DETAIL,
        payload="scenario_id,hour_index,load_power\nS0001,0,1.0\n",
        filename="hourly_detail_S0001.csv",
        content_type="text/csv",
    )
    record = StudyResultRecord(
        result_id="technical_result",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id="technical_summary",
        hourly_detail_artifact_ids={"S0001": "hourly_detail_S0001"},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "analyst",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY: False,
            }

    dummy = DummyStreamlit()
    app._pilot_restore_technical_summary_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=record,
    )

    loaded = app._load_pilot_hourly_detail_artifact_if_available(dummy, "S0001")

    assert loaded is True
    assert dummy.session_state["batch_result"].hourly_details["S0001"]["load_power"].tolist() == [1.0]
    assert dummy.session_state["study_result"].result_store_refs["hourly_detail_artifact_id_S0001"] == (
        "hourly_detail_S0001"
    )
    assert access.result_store.read_audit_log(project.project_id)[-1].action == AuditAction.VIEW_ARTIFACT


def test_pilot_restore_summary_can_rebuild_input_from_input_artifacts_and_recompute(
    tmp_path,
    monkeypatch,
):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.pilot_backend import ArtifactKind, AuditAction, Project, ProjectRole, StudyResultRecord, User
    from green_direct.services import TechnicalStudyInput

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    access.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = access.create_project(actor_user_id="admin", project=Project("project_1", "Pilot project"))
    access.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )

    def curve_payload(column: str, value: float) -> str:
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=24, freq="h"),
                column: [value] * 24,
            }
        )
        return frame.to_csv(index=False)

    summary_csv = (
        "scenario_id,pv_capacity,wind_capacity,bess_power,bess_energy,green_load_rate\n"
        "S0001,1.0,0.0,0.0,0.0,0.5\n"
    )
    config_snapshot = {
        "study_id": "study_1",
        "scenario_grid": {
            "pv_capacity": {"start": 1, "end": 1, "step": 1},
            "wind_capacity": {"start": 0, "end": 0, "step": 1},
            "bess_power": {"start": 0, "end": 0, "step": 1},
            "bess_duration_hours": [0],
        },
        "bess": {"soc_initial": 0.5, "soc_min": 0.1, "soc_max": 0.9},
        "policy": {"allow_export": False},
        "performance": {"parallel_workers": 1},
        "cleaning": {"allow_negative_pu": True},
        "time": {"dt_hours": 1.0, "supported_hours": [24], "validate_length": False},
        "curve_columns": {
            "load": {"time_col": "timestamp", "value_col": "load"},
            "pv": {"time_col": "timestamp", "value_col": "pv"},
            "wind": {"time_col": "timestamp", "value_col": "wind"},
        },
        "input_artifact_ids": {
            "load": "input_curve_load",
            "pv": "input_curve_pv",
            "wind": "input_curve_wind",
        },
    }
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload=summary_csv,
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="config_snapshot",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.CONFIG_SNAPSHOT,
        payload=json.dumps(config_snapshot),
        filename="config_snapshot.json",
        content_type="application/json",
    )
    for curve_key, column, value in [
        ("load", "load", 1.0),
        ("pv", "pv", 0.5),
        ("wind", "wind", 0.3),
    ]:
        access.result_store.store_artifact(
            artifact_id=f"input_curve_{curve_key}",
            project_id=project.project_id,
            study_id="study_1",
            job_id="job_1",
            kind=ArtifactKind.INPUT_CURVE,
            payload=curve_payload(column, value),
            filename=f"input_curve_{curve_key}.csv",
            content_type="text/csv",
        )
    record = StudyResultRecord(
        result_id="technical_result",
        project_id=project.project_id,
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id="technical_summary",
    )
    access.result_store.save_result_record(record)

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "analyst",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_CAN_EXPORT_KEY: False,
            }

    dummy = DummyStreamlit()
    app._pilot_restore_technical_summary_to_session(
        dummy,
        access=access,
        actor_user_id="analyst",
        record=record,
    )

    restored = app._restore_technical_study_input_from_pilot_artifacts(dummy)
    inputs = dummy.session_state[app.TECHNICAL_STUDY_INPUT_KEY]

    assert restored is True
    assert isinstance(inputs, TechnicalStudyInput)
    assert inputs.load_value_col == "load"
    assert inputs.pv_value_col == "pv"
    assert inputs.wind_value_col == "wind"
    assert inputs.validate_length is False
    assert inputs.time_params.supported_hours == (24,)
    assert inputs.policy_params.allow_export is False

    hourly = pd.DataFrame({"scenario_id": ["S0001"], "hour_index": [0], "load_power": [1.0]})
    captured = {}

    def fake_regenerate(inputs_arg, *, scenario_id, summary):
        captured["inputs"] = inputs_arg
        captured["scenario_id"] = scenario_id
        return SimpleNamespace(hourly_detail=hourly)

    monkeypatch.setattr(app, "run_hourly_detail_for_scenario", fake_regenerate)
    monkeypatch.setattr(app, "_clear_chart_export_cache", lambda st: None)
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    message = app._append_hourly_detail_to_current_result(
        dummy,
        "S0001",
        dummy.session_state["batch_result"].summary,
    )
    next_batch = dummy.session_state["batch_result"]
    saved_hourly = access.result_store.load_artifact(project.project_id, "study_1", "hourly_detail_S0001")
    audit_actions = [event.action for event in access.result_store.read_audit_log(project.project_id)]

    assert "S0001" in message
    assert captured["inputs"] is inputs
    assert captured["scenario_id"] == "S0001"
    assert isinstance(next_batch, BatchResult)
    assert next_batch.hourly_details["S0001"].equals(hourly)
    assert saved_hourly.kind == ArtifactKind.HOURLY_DETAIL
    assert AuditAction.VIEW_ARTIFACT in audit_actions
    assert AuditAction.DOWNLOAD_ARTIFACT not in audit_actions


def test_streamlit_app_shows_pilot_login_gate_when_enabled(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)

    assert len(app_test.exception) == 0
    assert any(text_input.label == "账号 / 邮箱" for text_input in app_test.text_input)
    assert not any(button.label == "开始方案仿真" for button in app_test.button)


def test_streamlit_app_allows_login_with_pilot_account(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import User
    from green_direct.services import LocalPilotAdminService, LocalPilotAuth, LocalPilotRegistry, LocalResultStore
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=result_store)
    admin = LocalPilotAdminService(registry=registry, auth=auth, result_store=result_store)
    admin.bootstrap_platform_admin(
        user=User("admin", "admin@example.local", "Admin", is_platform_admin=True),
        password="admin-password",
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)
    app_test.text_input[0].input("admin@example.local")
    app_test.text_input[1].input("admin-password")
    app_test.button[0].click().run(timeout=10)

    assert len(app_test.exception) == 0
    assert not any(text_input.label == "密码" for text_input in app_test.text_input)
    assert any(button.label == "退出登录" for button in app_test.button)
    assert any(text_input.label == "项目 ID" for text_input in app_test.text_input)
    assert not any(button.label == "开始方案仿真" for button in app_test.button)

    inputs = {text_input.label: text_input for text_input in app_test.text_input}
    inputs["项目 ID"].input("project_1")
    inputs["项目名称"].input("Internal pilot project")
    next(button for button in app_test.button if button.label == "创建项目").click().run(timeout=10)

    assert len(app_test.exception) == 0
    assert any(button.label == "开始方案仿真" for button in app_test.button)
    assert LocalPilotRegistry(tmp_path).load_project("project_1").name == "Internal pilot project"


def test_streamlit_platform_admin_can_create_user(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import User
    from green_direct.services import LocalPilotAdminService, LocalPilotAuth, LocalPilotRegistry, LocalResultStore
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=result_store)
    admin = LocalPilotAdminService(registry=registry, auth=auth, result_store=result_store)
    admin.bootstrap_platform_admin(
        user=User("admin", "admin@example.local", "Admin", is_platform_admin=True),
        password="admin-password",
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)
    app_test.text_input[0].input("admin@example.local")
    app_test.text_input[1].input("admin-password")
    app_test.button[0].click().run(timeout=10)

    next(button for button in app_test.button if button.label == "Admin  平台管理").click().run(timeout=10)
    inputs = {text_input.label: text_input for text_input in app_test.text_input}
    inputs["用户 ID"].input("analyst")
    inputs["登录名 / 邮箱"].input("analyst@example.local")
    inputs["显示名称"].input("Analyst")
    inputs["初始密码"].input("analyst-password")
    next(button for button in app_test.button if button.label == "创建用户").click().run(timeout=10)

    created = LocalPilotRegistry(tmp_path).load_user("analyst")
    assert created.login_name == "analyst@example.local"
    assert created.is_platform_admin is False


def test_streamlit_platform_admin_can_create_and_archive_project(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ProjectRole, ProjectStatus, User
    from green_direct.services import LocalPilotAdminService, LocalPilotAuth, LocalPilotRegistry, LocalResultStore
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=result_store)
    admin = LocalPilotAdminService(registry=registry, auth=auth, result_store=result_store)
    admin.bootstrap_platform_admin(
        user=User("admin", "admin@example.local", "Admin", is_platform_admin=True),
        password="admin-password",
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)
    app_test.text_input[0].input("admin@example.local")
    app_test.text_input[1].input("admin-password")
    app_test.button[0].click().run(timeout=10)

    next(button for button in app_test.button if button.label == "Admin  平台管理").click().run(timeout=10)
    inputs = {text_input.label: text_input for text_input in app_test.text_input}
    inputs["新项目 ID"].input("project_ui")
    inputs["新项目名称"].input("UI Pilot Project")
    next(button for button in app_test.button if button.label == "创建项目").click().run(timeout=10)

    created = LocalPilotRegistry(tmp_path).load_project("project_ui")
    membership = LocalPilotRegistry(tmp_path).get_project_membership("project_ui", "admin")
    assert created.name == "UI Pilot Project"
    assert membership is not None
    assert membership.role == ProjectRole.ADMIN

    next(button for button in app_test.button if button.label == "归档所选项目").click().run(timeout=10)

    archived = LocalPilotRegistry(tmp_path).load_project("project_ui")
    assert archived.status == ProjectStatus.ARCHIVED


def test_streamlit_non_admin_does_not_show_platform_admin_entry(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import User
    from green_direct.services import LocalPilotAdminService, LocalPilotAuth, LocalPilotRegistry, LocalResultStore
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=result_store)
    admin = LocalPilotAdminService(registry=registry, auth=auth, result_store=result_store)
    admin.bootstrap_platform_admin(
        user=User("admin", "admin@example.local", "Admin", is_platform_admin=True),
        password="admin-password",
    )
    admin.create_user(
        actor_user_id="admin",
        user=User("analyst", "analyst@example.local", "Analyst"),
        initial_password="analyst-password",
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)
    app_test.text_input[0].input("analyst@example.local")
    app_test.text_input[1].input("analyst-password")
    app_test.button[0].click().run(timeout=10)

    assert len(app_test.exception) == 0
    assert not any(button.label == "Admin  平台管理" for button in app_test.button)


def test_platform_admin_audit_frame_serializes_metadata():
    import green_direct.ui.app as app
    from datetime import datetime, timezone

    from green_direct.models.pilot_backend import AuditAction, AuditLog

    event = AuditLog(
        event_id="audit_1",
        actor_user_id="admin",
        action=AuditAction.UPDATE_USER,
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        target_type="user",
        target_id="analyst",
        metadata={"b": 2, "a": 1},
        created_at=datetime(2026, 1, 1, 8, 30, tzinfo=timezone.utc),
    )

    frame = app._platform_admin_audit_frame([event])

    assert list(frame.columns) == [
        "时间",
        "动作",
        "执行人",
        "project_id",
        "study_id",
        "job_id",
        "对象类型",
        "对象 ID",
        "metadata",
    ]
    assert frame.loc[0, "时间"] == "2026-01-01T08:30:00+00:00"
    assert frame.loc[0, "动作"] == "update_user"
    assert frame.loc[0, "metadata"] == '{"a":1,"b":2}'


def test_platform_admin_worker_once_uses_supported_scope_and_reports_result(monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import JobStatus, JobType

    captured = {}
    monkeypatch.setenv(app.PILOT_ADMIN_WORKER_ID_ENV, "ui-worker")
    monkeypatch.setattr(app, "_pilot_access_service", lambda: "access-service")

    job = SimpleNamespace(
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        job_type=JobType.TECHNICAL_STUDY,
        status=JobStatus.SUCCEEDED,
    )
    result = SimpleNamespace(
        job=job,
        artifact=SimpleNamespace(artifact_id="hourly_detail_S0001"),
        message="Stored hourly detail artifact",
        succeeded=True,
    )

    def fake_execute_next_worker_job(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(app, "execute_next_worker_job", fake_execute_next_worker_job)

    message = app._run_platform_admin_worker_once(actor_user_id="admin@example.local", project_id="project_1")

    assert captured["access_service"] == "access-service"
    assert captured["actor_user_id"] == "admin@example.local"
    assert captured["worker_id"] == "ui-worker-admin-example.local"
    assert captured["project_id"] == "project_1"
    assert captured["job_types"] == app.SUPPORTED_PILOT_MANUAL_WORKER_JOB_TYPES
    assert "已处理任务" in message
    assert "hourly_detail_S0001" in message


def test_platform_admin_worker_once_reports_idle_queue(monkeypatch):
    import green_direct.ui.app as app

    monkeypatch.setattr(app, "_pilot_access_service", lambda: "access-service")
    monkeypatch.setattr(app, "execute_next_worker_job", lambda **kwargs: None)

    assert app._run_platform_admin_worker_once(actor_user_id="admin", project_id=None) == "暂无可处理的排队任务。"


def test_platform_admin_stale_cleanup_uses_access_service(monkeypatch):
    import green_direct.ui.app as app

    captured = {}

    class Access:
        def fail_stale_running_jobs_for_platform_admin(self, **kwargs):
            captured.update(kwargs)
            return [SimpleNamespace(job_id="job_1"), SimpleNamespace(job_id="job_2")]

    monkeypatch.setattr(app, "_pilot_access_service", lambda: Access())

    message = app._fail_platform_admin_stale_jobs(
        actor_user_id="admin",
        project_id="project_1",
        stale_after_seconds=120,
    )

    assert captured == {
        "actor_user_id": "admin",
        "project_id": "project_1",
        "stale_after_seconds": 120,
    }
    assert message == "已将 2 个超时运行任务标记为 failed。"


def test_curve_display_tooltip_shows_input_curve_metrics():
    from green_direct.ui.app import _curve_display_tooltip

    load_data = pd.DataFrame(
        {
            "时间": pd.date_range("2024-01-01", periods=3, freq="h"),
            "数值": [10000.0, 20000.0, 30000.0],
        }
    )
    profile_data = pd.DataFrame(
        {
            "时间": pd.date_range("2024-01-01", periods=3, freq="h"),
            "数值": [1000.0, 500.0, 562.0],
        }
    )

    load_tip = _curve_display_tooltip("负荷", load_data, "时间", "数值")
    pv_tip = _curve_display_tooltip("光伏", profile_data, "时间", "数值")
    wind_tip = _curve_display_tooltip("风电", profile_data, "时间", "数值")

    assert "负荷电量：6 亿kWh" in load_tip
    assert "光伏利用小时：2,062 h" in pv_tip
    assert "风电利用小时：2,062 h" in wind_tip
    assert "有效点数：3 / 3" in load_tip


def test_go_to_workflow_page_maps_alias_and_reruns():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {}
            self.did_rerun = False

        def rerun(self):
            self.did_rerun = True

    dummy = DummyStreamlit()
    app._go_to_workflow_page(dummy, "经济性评价")

    assert dummy.session_state["_workflow_page_target"] == "经济性测算"
    assert dummy.did_rerun is True


def test_welcome_start_button_does_not_mutate_radio_state_after_instantiation():
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.run(timeout=10)

    next(button for button in app_test.button if button.label == "开始方案仿真").click().run(timeout=10)

    assert len(app_test.exception) == 0


def test_technical_next_button_does_not_mutate_radio_state_after_instantiation():
    from streamlit.testing.v1 import AppTest

    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "pv_capacity": 1.0,
                "wind_capacity": 1.0,
                "bess_power": 1.0,
                "bess_energy": 2.0,
                "pass_policy": True,
                "green_load_rate": 0.3,
                "curtail_rate": 0.1,
                "grid_import_rate": 0.2,
                "self_use_rate": 0.8,
                "export_rate": 0.05,
            }
        ]
    )
    batch_result = SimpleNamespace(
        summary=summary,
        hourly_details={"S0001": pd.DataFrame({"timestamp": pd.date_range("2020-01-01", periods=24, freq="h")})},
        warnings=[],
        errors=pd.DataFrame(),
        scenario_count=1,
    )

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.session_state["workflow_page"] = "方案仿真"
    app_test.session_state["batch_result"] = batch_result
    app_test.run(timeout=10)
    next(button for button in app_test.button if button.label == "进入经济性测算").click().run(timeout=10)

    assert len(app_test.exception) == 0


def test_workflow_page_applies_queued_target_before_radio_render():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {"workflow_page": "欢迎页", "_workflow_page_target": "方案仿真"}

    dummy = DummyStreamlit()

    assert app._normalize_workflow_page(dummy) == "方案仿真"
    assert dummy.session_state["workflow_page"] == "方案仿真"
    assert "_workflow_page_target" not in dummy.session_state


def test_preserve_widget_state_keeps_simulation_form_values():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {"simulation_pv_capacity_end": 18.0}

    dummy = DummyStreamlit()
    app._preserve_widget_state(dummy, app.SIMULATION_WIDGET_STATE_KEYS)

    assert dummy.session_state["simulation_pv_capacity_end"] == 18.0


def test_single_scenario_grid_from_exact_builds_one_candidate():
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import estimate_scenario_count

    grid, errors = app._single_scenario_grid_from_exact(
        pv_capacity=5.0,
        wind_capacity=5.0,
        bess_power=2.0,
        bess_energy=8.0,
    )

    assert errors == []
    assert grid == {
        "pv_capacity": {"start": 5.0, "end": 5.0, "step": 5.0},
        "wind_capacity": {"start": 5.0, "end": 5.0, "step": 5.0},
        "bess_power": {"start": 2.0, "end": 2.0, "step": 2.0},
        "bess_duration_hours": [4.0],
    }
    assert estimate_scenario_count(grid) == 1


def test_single_scenario_grid_from_exact_rejects_invalid_configs():
    import green_direct.ui.app as app

    no_renewable_grid, no_renewable_errors = app._single_scenario_grid_from_exact(
        pv_capacity=0.0,
        wind_capacity=0.0,
        bess_power=2.0,
        bess_energy=8.0,
    )
    no_power_grid, no_power_errors = app._single_scenario_grid_from_exact(
        pv_capacity=5.0,
        wind_capacity=0.0,
        bess_power=0.0,
        bess_energy=8.0,
    )

    assert no_renewable_grid is None
    assert any("纯储能" in error for error in no_renewable_errors)
    assert no_power_grid is None
    assert any("储能功率为 0" in error for error in no_power_errors)


def test_exact_scenario_inputs_are_preserved_across_workflow_pages():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "simulation_scenario_pool_mode": "指定单方案",
                "simulation_exact_pv_capacity": 5.0,
                "simulation_exact_wind_capacity": 6.0,
                "simulation_exact_bess_power": 2.0,
                "simulation_exact_bess_energy": 8.0,
            }

    dummy = DummyStreamlit()
    app._preserve_widget_state(dummy, app.SIMULATION_WIDGET_STATE_KEYS)

    assert dummy.session_state["simulation_scenario_pool_mode__stored_value"] == "指定单方案"
    assert dummy.session_state["simulation_exact_bess_energy__stored_value"] == 8.0


def test_project_price_curve_state_invalidates_economy_results():
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "economy_v1_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                "single_entity_economy_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                "recommendation_v1_inputs": {"old": True},
                "download_payloads": {"old": True},
            }

    dummy = DummyStreamlit()
    price_curve = read_price_curve("samples/price_curve_template_down_grid.csv")

    app._remember_project_price_curve(dummy, price_curve, "price_curve_template_down_grid.csv", "sig-1")

    assert dummy.session_state[app.PROJECT_PRICE_CURVE_DATA_KEY] is price_curve
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY] is True
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_META_KEY]["source_name"] == "price_curve_template_down_grid.csv"
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_META_KEY]["row_count"] == 8784
    assert "economy_v1_result" not in dummy.session_state
    assert "single_entity_economy_result" not in dummy.session_state
    assert "recommendation_v1_inputs" not in dummy.session_state
    assert "download_payloads" not in dummy.session_state


def test_incompatible_project_price_curve_is_discarded_for_current_hourly_rows():
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "economy_v1_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                "single_entity_economy_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                app.PROJECT_PRICE_CURVE_DATA_KEY: read_price_curve("samples/price_curve_template_down_grid.csv"),
                app.PROJECT_PRICE_CURVE_META_KEY: {
                    "source_name": "price_curve_template_down_grid.csv",
                    "row_count": 8784,
                    "field_count": 5,
                    "signature": "old-template",
                },
                app.PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY: True,
            }

    dummy = DummyStreamlit()
    hourly_details = {
        "S0001": pd.DataFrame(
            {
                "timestamp": pd.date_range("2025-01-01", periods=8760, freq="h"),
                "hour_index": range(8760),
            }
        )
    }

    notice = app._discard_incompatible_project_price_curve(dummy, hourly_details)

    assert notice is not None
    assert "8,784" in notice
    assert "8,760" in notice
    assert app.PROJECT_PRICE_CURVE_DATA_KEY not in dummy.session_state
    assert app.PROJECT_PRICE_CURVE_META_KEY not in dummy.session_state
    assert "economy_v1_result" not in dummy.session_state
    assert "single_entity_economy_result" not in dummy.session_state


def test_matching_project_price_curve_is_kept_for_current_hourly_rows():
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    price_curve = read_price_curve("samples/price_curve_template_down_grid.csv")

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PROJECT_PRICE_CURVE_DATA_KEY: price_curve,
                app.PROJECT_PRICE_CURVE_META_KEY: {
                    "source_name": "price_curve_template_down_grid.csv",
                    "row_count": 8784,
                    "field_count": 5,
                    "signature": "matching-template",
                },
                app.PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY: True,
            }

    dummy = DummyStreamlit()
    hourly_details = {
        "S0001": pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=8784, freq="h"),
                "hour_index": range(8784),
            }
        )
    }

    notice = app._discard_incompatible_project_price_curve(dummy, hourly_details)

    assert notice is None
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_DATA_KEY] is price_curve
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_META_KEY]["row_count"] == 8784


def test_large_run_detail_retention_plan_switches_to_summary_first():
    import green_direct.ui.app as app

    small = app._technical_detail_retention_plan(
        100,
        threshold=5000,
        large_run_hourly_detail_limit=20,
    )
    large = app._technical_detail_retention_plan(
        6000,
        threshold=5000,
        large_run_hourly_detail_limit=3,
    )
    summary_only = app._technical_detail_retention_plan(
        6000,
        threshold=5000,
        large_run_hourly_detail_limit=0,
    )

    assert small["mode"] == "full"
    assert small["retain_hourly_details"] is True
    assert small["hourly_detail_scenario_ids"] == ()
    assert large["mode"] == "summary_first"
    assert large["retain_hourly_details"] is False
    assert large["hourly_detail_scenario_ids"] == ("S0001", "S0002", "S0003")
    assert summary_only["hourly_detail_scenario_ids"] == ()


def test_economy_cashflow_retention_plan_switches_to_summary_first():
    import green_direct.ui.app as app

    summary = pd.DataFrame({"scenario_id": ["S0101", "S0102", "S0103", "S0104"]})

    small = app._economy_cashflow_retention_plan(summary.iloc[:2], threshold=3, retained_limit=2)
    large = app._economy_cashflow_retention_plan(summary, threshold=3, retained_limit=2)
    summary_only = app._economy_cashflow_retention_plan(summary, threshold=3, retained_limit=0)

    assert small["mode"] == "full"
    assert small["retain_annual_cashflows"] is True
    assert small["annual_cashflow_scenario_ids"] == ()
    assert large["mode"] == "summary_first"
    assert large["retain_annual_cashflows"] is False
    assert large["annual_cashflow_scenario_ids"] == ("S0101", "S0102")
    assert summary_only["annual_cashflow_scenario_ids"] == ()


def test_economy_cashflow_retention_environment_guardrails(monkeypatch):
    import green_direct.ui.app as app

    monkeypatch.setenv(app.ECONOMY_CASHFLOW_RETENTION_THRESHOLD_ENV, "12")
    monkeypatch.setenv(app.ECONOMY_RETAINED_CASHFLOW_LIMIT_ENV, "3")
    assert app._economy_cashflow_retention_threshold() == 12
    assert app._economy_retained_cashflow_limit() == 3

    monkeypatch.setenv(app.ECONOMY_CASHFLOW_RETENTION_THRESHOLD_ENV, "invalid")
    monkeypatch.setenv(app.ECONOMY_RETAINED_CASHFLOW_LIMIT_ENV, "-1")
    assert app._economy_cashflow_retention_threshold() == app.DEFAULT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD
    assert app._economy_retained_cashflow_limit() == 0


def test_economy_cashflow_retention_missing_notice_only_for_unretained_scenario():
    import green_direct.ui.app as app

    economy_result = {
        "cashflow_retention": {
            "mode": "summary_first",
            "retain_annual_cashflows": False,
            "annual_cashflow_scenario_ids": ["S0101", "S0102"],
            "scenario_count": 5000,
        }
    }

    assert app._economy_cashflow_retention_missing_notice(economy_result, "S0101") is None
    notice = app._economy_cashflow_retention_missing_notice(economy_result, "S0103")
    assert notice is not None
    assert "summary-first" in notice
    assert "S0103" in notice


def test_technical_workload_estimate_scales_with_detail_retention_and_workers():
    import green_direct.ui.app as app

    full_retention = app._technical_detail_retention_plan(
        6000,
        threshold=10000,
        large_run_hourly_detail_limit=20,
    )
    summary_first = app._technical_detail_retention_plan(
        6000,
        threshold=5000,
        large_run_hourly_detail_limit=20,
    )

    full_workload = app._technical_workload_summary(
        6000,
        hour_count=8760,
        parallel_workers=1,
        detail_retention_plan=full_retention,
    )
    summary_workload = app._technical_workload_summary(
        6000,
        hour_count=8760,
        parallel_workers=1,
        detail_retention_plan=summary_first,
    )
    parallel_workload = app._technical_workload_summary(
        6000,
        hour_count=8760,
        parallel_workers=4,
        detail_retention_plan=summary_first,
    )

    assert full_workload["retained_detail_count"] == 6000
    assert summary_workload["retained_detail_count"] == 20
    assert full_workload["estimate_seconds"] > summary_workload["estimate_seconds"]
    assert parallel_workload["estimate_seconds"] < summary_workload["estimate_seconds"]
    assert "预计耗时约" in summary_workload["estimate_text"]


def test_large_run_confirmation_helpers_require_and_reset_by_signature():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.LARGE_RUN_CONFIRMATION_SIGNATURE_KEY: "old-signature",
                "simulation_confirm_large_run": True,
            }

        def checkbox(self, _label, *, key, **_kwargs):
            return self.session_state[key]

    workload = {
        "scenario_count": 6000,
        "hour_count": 8760,
        "parallel_workers": 1,
        "retained_detail_count": 20,
        "detail_mode": "summary_first",
    }
    dummy = DummyStreamlit()

    assert app._large_run_confirmation_required(6000, threshold=5000)
    assert not app._large_run_confirmation_required(5000, threshold=5000)
    assert app._technical_workload_hour_count(pd.DataFrame(index=range(8760)), pd.DataFrame(index=range(8784))) == 8760
    assert not app._render_large_run_confirmation(dummy, workload=workload)
    assert dummy.session_state["simulation_confirm_large_run"] is False

    dummy.session_state["simulation_confirm_large_run"] = True
    assert app._render_large_run_confirmation(dummy, workload=workload)


def test_simulation_scenario_count_limit_uses_environment_guardrail(monkeypatch):
    import green_direct.ui.app as app

    monkeypatch.setenv(app.MAX_SCENARIOS_PER_RUN_ENV, "123")
    assert app._max_scenarios_per_run() == 123

    monkeypatch.setenv(app.MAX_SCENARIOS_PER_RUN_ENV, "0")
    assert app._max_scenarios_per_run() is None

    monkeypatch.setenv(app.MAX_SCENARIOS_PER_RUN_ENV, "invalid")
    assert app._max_scenarios_per_run() == app.DEFAULT_MAX_SCENARIOS_PER_RUN


def test_scenario_count_limit_notice_blocks_oversized_pool():
    import green_direct.ui.app as app

    assert app._scenario_count_limit_notice(100, 100) is None
    assert app._scenario_count_limit_notice(101, 100)
    assert app.MAX_SCENARIOS_PER_RUN_ENV in app._scenario_count_limit_notice(101, 100)


def test_append_hourly_detail_updates_current_result(monkeypatch):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.diagnostics import InputDiagnostics
    from green_direct.services import StudyResult, TechnicalStudyInput, TechnicalStudyResult

    summary = pd.DataFrame(
        {
            "scenario_id": ["S0002"],
            "pv_capacity": [1.0],
            "wind_capacity": [0.0],
            "bess_power": [0.0],
            "bess_energy": [0.0],
        }
    )
    batch_result = BatchResult(
        summary=summary,
        hourly_details={},
        errors=pd.DataFrame(),
        warnings=[],
        scenario_count=1,
    )
    technical_result = TechnicalStudyResult(
        study_id="study-ui",
        batch_result=batch_result,
        input_diagnostics=InputDiagnostics(),
        config_snapshot={},
    )
    technical_input = TechnicalStudyInput(
        load_source=b"",
        pv_source=b"",
        wind_source=b"",
        load_time_col="time",
        load_value_col="load",
        pv_time_col="time",
        pv_value_col="pv",
        wind_time_col="time",
        wind_value_col="wind",
        scenario_grid={},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.TECHNICAL_STUDY_INPUT_KEY: technical_input,
                "batch_result": batch_result,
                "study_result": StudyResult.from_technical(technical_result),
                "download_payloads": {"old": b"payload"},
            }

    hourly = pd.DataFrame({"scenario_id": ["S0002"], "hour_index": [0], "load_power": [1.0]})
    dummy = DummyStreamlit()
    monkeypatch.setattr(
        app,
        "run_hourly_detail_for_scenario",
        lambda inputs, *, scenario_id, summary: SimpleNamespace(hourly_detail=hourly),
    )
    monkeypatch.setattr(app, "_clear_chart_export_cache", lambda st: None)
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    message = app._append_hourly_detail_to_current_result(dummy, "S0002", summary)

    next_batch = dummy.session_state["batch_result"]
    assert "S0002" in message
    assert next_batch is not batch_result
    assert next_batch.hourly_details["S0002"].equals(hourly)
    assert dummy.session_state["study_result"].technical_result.batch_result is next_batch
    assert "download_payloads" not in dummy.session_state


def test_append_hourly_detail_persists_pilot_artifact(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.diagnostics import InputDiagnostics
    from green_direct.models.pilot_backend import ArtifactKind, Project, User
    from green_direct.services import StudyResult, TechnicalStudyInput, TechnicalStudyResult

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0002"],
            "pv_capacity": [1.0],
            "wind_capacity": [0.0],
            "bess_power": [0.0],
            "bess_energy": [0.0],
        }
    )
    batch_result = BatchResult(
        summary=summary,
        hourly_details={},
        errors=pd.DataFrame(),
        warnings=[],
        scenario_count=1,
    )
    technical_result = TechnicalStudyResult(
        study_id="study-ui-hourly",
        batch_result=batch_result,
        input_diagnostics=InputDiagnostics(),
        config_snapshot={"study_id": "study-ui-hourly"},
    )
    technical_input = TechnicalStudyInput(
        load_source=b"",
        pv_source=b"",
        wind_source=b"",
        load_time_col="time",
        load_value_col="load",
        pv_time_col="time",
        pv_value_col="pv",
        wind_time_col="time",
        wind_value_col="wind",
        scenario_grid={},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.TECHNICAL_STUDY_INPUT_KEY: technical_input,
                "batch_result": batch_result,
                "download_payloads": {"old": b"payload"},
            }

    dummy = DummyStreamlit()
    persisted_technical = app._persist_pilot_technical_result_if_enabled(
        dummy,
        technical_result,
        technical_input=technical_input,
    )
    dummy.session_state["study_result"] = app._study_result_with_pilot_refs(
        StudyResult.from_technical(technical_result),
        persisted_technical,
    )
    hourly = pd.DataFrame(
        {
            "scenario_id": ["S0002"],
            "hour_index": [0],
            "load_power": [1.0],
        }
    )
    monkeypatch.setattr(
        app,
        "run_hourly_detail_for_scenario",
        lambda inputs, *, scenario_id, summary: SimpleNamespace(hourly_detail=hourly),
    )
    monkeypatch.setattr(app, "_clear_chart_export_cache", lambda st: None)
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    app._append_hourly_detail_to_current_result(dummy, "S0002", summary)

    store = app._pilot_access_service().result_store
    artifact = store.load_artifact(project.project_id, "study-ui-hourly", "hourly_detail_S0002")
    record = store.load_result_record(project.project_id, "study-ui-hourly", "technical_result")
    payload = store.read_artifact_payload(artifact).decode("utf-8")

    assert artifact.kind == ArtifactKind.HOURLY_DETAIL
    assert record.hourly_detail_artifact_ids == {"S0002": "hourly_detail_S0002"}
    assert "load_power" in payload
    assert dummy.session_state["study_result"].result_store_refs["hourly_detail_artifact_id_S0002"] == (
        "hourly_detail_S0002"
    )
    assert app.PILOT_RESULT_STORE_NOTICE_KEY in dummy.session_state


def test_queue_hourly_detail_job_uses_saved_project_artifacts(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.diagnostics import InputDiagnostics
    from green_direct.models.pilot_backend import ArtifactKind, JobStatus, Project, User
    from green_direct.services import StudyResult, TechnicalStudyInput, TechnicalStudyResult

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0002"],
            "pv_capacity": [1.0],
            "wind_capacity": [0.0],
            "bess_power": [0.0],
            "bess_energy": [0.0],
        }
    )
    batch_result = BatchResult(
        summary=summary,
        hourly_details={},
        errors=pd.DataFrame(),
        warnings=[],
        scenario_count=1,
    )
    technical_result = TechnicalStudyResult(
        study_id="study-ui-worker",
        batch_result=batch_result,
        input_diagnostics=InputDiagnostics(),
        config_snapshot={
            "study_id": "study-ui-worker",
            "curve_columns": {
                "load": {"time_col": "time", "value_col": "load"},
                "pv": {"time_col": "time", "value_col": "pv"},
                "wind": {"time_col": "time", "value_col": "wind"},
            },
        },
    )
    technical_input = TechnicalStudyInput(
        load_source=b"time,load\n2026-01-01 00:00:00,1\n",
        pv_source=b"time,pv\n2026-01-01 00:00:00,0\n",
        wind_source=b"time,wind\n2026-01-01 00:00:00,0\n",
        load_time_col="time",
        load_value_col="load",
        pv_time_col="time",
        pv_value_col="pv",
        wind_time_col="time",
        wind_value_col="wind",
        scenario_grid={},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_ROLE_KEY: "admin",
                app.TECHNICAL_STUDY_INPUT_KEY: technical_input,
                "batch_result": batch_result,
            }

    dummy = DummyStreamlit()
    persisted_technical = app._persist_pilot_technical_result_if_enabled(
        dummy,
        technical_result,
        technical_input=technical_input,
    )
    dummy.session_state["study_result"] = app._study_result_with_pilot_refs(
        StudyResult.from_technical(technical_result),
        persisted_technical,
    )

    job = app._queue_pilot_hourly_detail_job_if_enabled(dummy, "S0002")

    assert job is not None
    assert job.status == JobStatus.QUEUED
    assert job.job_type.value == "technical_study"
    assert job.progress_message == "hourly detail queued: S0002"
    assert job.input_artifact_ids["technical_summary"] == "technical_summary"
    assert job.input_artifact_ids["config_snapshot"] == "config_snapshot"
    assert job.input_artifact_ids["input_curve_load"] == "input_curve_load"
    payload_artifact = access.result_store.load_artifact(
        project.project_id,
        "study-ui-worker",
        job.input_artifact_ids["job_payload"],
    )
    payload = json.loads(access.result_store.read_artifact_payload(payload_artifact).decode("utf-8"))
    assert payload_artifact.kind == ArtifactKind.JOB_INPUT
    assert payload == {
        "task": "hourly_detail",
        "scenario_id": "S0002",
        "technical_result_id": "technical_result",
        "retention_days": 30,
    }
    assert "后台逐小时明细补算任务" in dummy.session_state[app.PILOT_RESULT_STORE_NOTICE_KEY]


def test_completed_hourly_detail_job_refreshes_result_ref_and_loads_artifact(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.batch.batch_runner import BatchResult
    from green_direct.models.diagnostics import InputDiagnostics
    from green_direct.models.pilot_backend import JobStatus, Project, User
    from green_direct.services import (
        StudyResult,
        TechnicalStudyInput,
        TechnicalStudyResult,
        persist_hourly_detail_artifact,
    )

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(app, "_clear_chart_export_cache", lambda st: None)
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0002"],
            "pv_capacity": [1.0],
            "wind_capacity": [0.0],
            "bess_power": [0.0],
            "bess_energy": [0.0],
        }
    )
    batch_result = BatchResult(
        summary=summary,
        hourly_details={},
        errors=pd.DataFrame(),
        warnings=[],
        scenario_count=1,
    )
    technical_result = TechnicalStudyResult(
        study_id="study-ui-worker",
        batch_result=batch_result,
        input_diagnostics=InputDiagnostics(),
        config_snapshot={
            "study_id": "study-ui-worker",
            "curve_columns": {
                "load": {"time_col": "time", "value_col": "load"},
                "pv": {"time_col": "time", "value_col": "pv"},
                "wind": {"time_col": "time", "value_col": "wind"},
            },
        },
    )
    technical_input = TechnicalStudyInput(
        load_source=b"time,load\n2026-01-01 00:00:00,1\n",
        pv_source=b"time,pv\n2026-01-01 00:00:00,0\n",
        wind_source=b"time,wind\n2026-01-01 00:00:00,0\n",
        load_time_col="time",
        load_value_col="load",
        pv_time_col="time",
        pv_value_col="pv",
        wind_time_col="time",
        wind_value_col="wind",
        scenario_grid={},
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_ROLE_KEY: "admin",
                app.TECHNICAL_STUDY_INPUT_KEY: technical_input,
                "batch_result": batch_result,
            }

    dummy = DummyStreamlit()
    persisted_technical = app._persist_pilot_technical_result_if_enabled(
        dummy,
        technical_result,
        technical_input=technical_input,
    )
    dummy.session_state["study_result"] = app._study_result_with_pilot_refs(
        StudyResult.from_technical(technical_result),
        persisted_technical,
    )
    queued = app._queue_pilot_hourly_detail_job_if_enabled(dummy, "S0002")
    assert queued is not None
    claimed = access.claim_next_job_for_worker(
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=["technical_study"],
    )
    assert claimed is not None
    hourly = pd.DataFrame({"scenario_id": ["S0002"], "hour_index": [0], "load_power": [1.5]})
    persist_hourly_detail_artifact(
        access_service=access,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study-ui-worker",
        scenario_id="S0002",
        hourly_detail=hourly,
        technical_result_id="technical_result",
        artifact_job_id=claimed.job_id,
    )
    completed = access.succeed_worker_job(
        actor_user_id="admin",
        worker_id="worker_1",
        project_id=project.project_id,
        study_id="study-ui-worker",
        job_id=claimed.job_id,
    )
    assert completed.status == JobStatus.SUCCEEDED
    assert "hourly_detail_artifact_id_S0002" not in dummy.session_state["study_result"].result_store_refs

    loaded = app._load_completed_pilot_hourly_detail_job_if_available(dummy, "S0002")

    assert loaded is True
    assert dummy.session_state["batch_result"].hourly_details["S0002"]["load_power"].tolist() == [1.5]
    assert dummy.session_state["study_result"].result_store_refs["hourly_detail_artifact_id_S0002"] == (
        "hourly_detail_S0002"
    )


def test_queue_annual_cashflow_job_uses_saved_economy_artifacts(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, JobStatus, Project, User
    from green_direct.services import StudyResult

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_tech",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,pv_capacity,wind_capacity,bess_power,bess_energy\nS0002,1,0,0,0\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="recommendation_inputs_job_1",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_economy",
        kind=ArtifactKind.RECOMMENDATION_INPUT,
        payload=json.dumps(
            {
                "economic_params": {},
                "avoided_grid_params": {"net_avoided_grid_cost_price": 0.55},
                "load_side_avoided_charge_price": 0.55,
                "green_power_settlement_price_with_vat": 0.40,
            },
            ensure_ascii=False,
        ),
        filename="recommendation_inputs.json",
        content_type="application/json",
    )
    access.result_store.store_artifact(
        artifact_id="economy_summary_job_1",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_economy",
        kind=ArtifactKind.ECONOMY_SUMMARY,
        payload="scenario_id,price_mode\nS0002,fixed_price\n",
        filename="power_economy_summary.csv",
        content_type="text/csv",
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_ROLE_KEY: "admin",
                "study_result": StudyResult(
                    study_id="study-ui-economy-worker",
                    result_store_refs={
                        "economy_result_id": "economy_result_job_1",
                        "technical_summary_artifact_id": "technical_summary",
                        "recommendation_input_artifact_id": "recommendation_inputs_job_1",
                        "power_economy_summary_artifact_id": "economy_summary_job_1",
                    },
                ),
            }

    dummy = DummyStreamlit()
    job = app._queue_pilot_annual_cashflow_job_if_enabled(dummy, "S0002")

    assert job is not None
    assert job.status == JobStatus.QUEUED
    assert job.job_type.value == "economic_study"
    assert job.progress_message == "annual cashflow queued: S0002"
    assert job.input_artifact_ids["technical_summary"] == "technical_summary"
    assert job.input_artifact_ids["recommendation_inputs"] == "recommendation_inputs_job_1"
    assert job.input_artifact_ids["power_economy_summary"] == "economy_summary_job_1"
    payload_artifact = access.result_store.load_artifact(
        project.project_id,
        "study-ui-economy-worker",
        job.input_artifact_ids["job_payload"],
    )
    payload = json.loads(access.result_store.read_artifact_payload(payload_artifact).decode("utf-8"))
    assert payload_artifact.kind == ArtifactKind.JOB_INPUT
    assert payload == {
        "task": "annual_cashflow",
        "scenario_id": "S0002",
        "economy_result_id": "economy_result_job_1",
        "perspective": "both",
        "retention_days": 30,
    }


def test_completed_annual_cashflow_job_loads_artifacts(tmp_path, monkeypatch):
    import green_direct.ui.app as app
    from green_direct.models.pilot_backend import ArtifactKind, JobStatus, Project, StudyResultRecord, User
    from green_direct.services import StudyResult, persist_annual_cashflow_artifact

    monkeypatch.setenv(app.PILOT_AUTH_ENV, "1")
    monkeypatch.setenv(app.PILOT_STORE_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    access = app._pilot_access_service()
    access.registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    project = access.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    access.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_tech",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,pv_capacity,wind_capacity,bess_power,bess_energy\nS0002,1,0,0,0\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    access.result_store.store_artifact(
        artifact_id="recommendation_inputs_job_1",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_economy",
        kind=ArtifactKind.RECOMMENDATION_INPUT,
        payload=json.dumps(
            {
                "economic_params": {},
                "avoided_grid_params": {"net_avoided_grid_cost_price": 0.55},
                "load_side_avoided_charge_price": 0.55,
                "green_power_settlement_price_with_vat": 0.40,
            },
            ensure_ascii=False,
        ),
        filename="recommendation_inputs.json",
        content_type="application/json",
    )
    access.result_store.store_artifact(
        artifact_id="economy_summary_job_1",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id="job_economy",
        kind=ArtifactKind.ECONOMY_SUMMARY,
        payload="scenario_id,price_mode\nS0002,fixed_price\n",
        filename="power_economy_summary.csv",
        content_type="text/csv",
    )
    access.result_store.save_result_record(
        StudyResultRecord(
            result_id="economy_result_job_1",
            project_id=project.project_id,
            study_id="study-ui-economy-worker",
            created_by_job_id="job_economy",
            economy_summary_artifact_id="economy_summary_job_1",
            recommendation_input_artifact_id="recommendation_inputs_job_1",
        )
    )

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                app.PILOT_USER_ID_KEY: "admin",
                app.PILOT_ACTIVE_PROJECT_ID_KEY: project.project_id,
                app.PILOT_ACTIVE_PROJECT_ROLE_KEY: "admin",
                "study_result": StudyResult(
                    study_id="study-ui-economy-worker",
                    result_store_refs={
                        "economy_result_id": "economy_result_job_1",
                        "technical_summary_artifact_id": "technical_summary",
                        "recommendation_input_artifact_id": "recommendation_inputs_job_1",
                        "power_economy_summary_artifact_id": "economy_summary_job_1",
                    },
                ),
                "economy_v1_result": {"summary": pd.DataFrame(), "annual_cashflows": {}},
                "single_entity_economy_result": {"summary": pd.DataFrame(), "annual_cashflows": {}},
            }

    dummy = DummyStreamlit()
    queued = app._queue_pilot_annual_cashflow_job_if_enabled(dummy, "S0002")
    assert queued is not None
    claimed = access.claim_next_job_for_worker(
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=["economic_study"],
    )
    assert claimed is not None
    power_annual = pd.DataFrame({"scenario_id": ["S0002", "S0002"], "year": [0, 1], "net_cash_flow": [-10.0, 3.0]})
    single_annual = pd.DataFrame({"scenario_id": ["S0002", "S0002"], "year": [0, 1], "net_cash_flow": [-9.0, 4.0]})
    persist_annual_cashflow_artifact(
        access_service=access,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        scenario_id="S0002",
        perspective="power",
        annual_cashflow=power_annual,
        economy_result_id="economy_result_job_1",
        artifact_job_id=claimed.job_id,
    )
    persist_annual_cashflow_artifact(
        access_service=access,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        scenario_id="S0002",
        perspective="single_entity",
        annual_cashflow=single_annual,
        economy_result_id="economy_result_job_1",
        artifact_job_id=claimed.job_id,
    )
    completed = access.succeed_worker_job(
        actor_user_id="admin",
        worker_id="worker_1",
        project_id=project.project_id,
        study_id="study-ui-economy-worker",
        job_id=claimed.job_id,
    )
    assert completed.status == JobStatus.SUCCEEDED

    loaded = app._load_completed_pilot_annual_cashflow_job_if_available(dummy, "S0002")

    assert loaded is True
    assert dummy.session_state["economy_v1_result"]["annual_cashflows"]["S0002"]["net_cash_flow"].tolist() == [
        -10.0,
        3.0,
    ]
    assert dummy.session_state["single_entity_economy_result"]["annual_cashflows"]["S0002"][
        "net_cash_flow"
    ].tolist() == [-9.0, 4.0]
    refs = dummy.session_state["study_result"].result_store_refs
    assert refs["power_annual_cashflow_artifact_id_S0002"] == "power_annual_cashflow_S0002"
    assert refs["single_entity_annual_cashflow_artifact_id_S0002"] == "single_entity_annual_cashflow_S0002"


def test_partial_hourly_retention_clears_price_curve():
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "economy_v1_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                app.PROJECT_PRICE_CURVE_DATA_KEY: read_price_curve("samples/price_curve_template_down_grid.csv"),
                app.PROJECT_PRICE_CURVE_META_KEY: {"source_name": "price_curve_template_down_grid.csv"},
                app.PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY: True,
            }

    dummy = DummyStreamlit()
    notice = app._clear_project_price_curve_for_partial_hourly_retention(
        dummy,
        {
            "retain_hourly_details": False,
            "hourly_detail_scenario_ids": ("S0001", "S0002"),
        },
    )

    assert notice is not None
    assert "价格曲线经济性需要全部候选方案逐小时明细" in notice
    assert app.PROJECT_PRICE_CURVE_DATA_KEY not in dummy.session_state
    assert app.PROJECT_PRICE_CURVE_META_KEY not in dummy.session_state
    assert "economy_v1_result" not in dummy.session_state


def test_unconfirmed_project_price_curve_state_is_cleared():
    import green_direct.ui.app as app
    from green_direct.economy import read_price_curve

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {
                "economy_v1_result": {"summary": pd.DataFrame({"scenario_id": ["old"]})},
                app.PROJECT_PRICE_CURVE_DATA_KEY: read_price_curve("samples/price_curve_template_down_grid.csv"),
                app.PROJECT_PRICE_CURVE_META_KEY: {"source_name": "price_curve_template_down_grid.csv"},
            }

    dummy = DummyStreamlit()

    cleared = app._clear_unconfirmed_project_price_curve(dummy)

    assert cleared is True
    assert app.PROJECT_PRICE_CURVE_DATA_KEY not in dummy.session_state
    assert app.PROJECT_PRICE_CURVE_META_KEY not in dummy.session_state
    assert "economy_v1_result" not in dummy.session_state


def test_batch_curve_upload_can_identify_project_price_curve():
    import green_direct.ui.app as app

    class UploadedFile:
        def __init__(self, name: str):
            self.name = name

    assigned, price_curve_file, messages = app._auto_assign_curve_files(
        [
            UploadedFile("load_curve.csv"),
            UploadedFile("pv_curve.csv"),
            UploadedFile("wind_curve.csv"),
            UploadedFile("湖南省2025年110kV下网电价曲线_8760小时.csv"),
            UploadedFile("load_curve.xlsx"),
        ]
    )

    assert set(assigned) == {"负荷", "光伏", "风电"}
    assert price_curve_file is not None
    assert price_curve_file.name == "湖南省2025年110kV下网电价曲线_8760小时.csv"
    assert any("技术曲线 `load_curve.xlsx` 当前仅支持 CSV" in message for message in messages)


def test_batch_price_curve_upload_stores_project_level_curve():
    import green_direct.ui.app as app

    class DummyStreamlit:
        def __init__(self):
            self.session_state = {}
            self.errors = []

        def error(self, message):
            self.errors.append(message)

    class UploadedFile:
        name = "price_curve_template_down_grid.csv"

        def getvalue(self):
            return Path("samples/price_curve_template_down_grid.csv").read_bytes()

    dummy = DummyStreamlit()

    app._remember_uploaded_price_curve(dummy, UploadedFile(), context_label="批量导入中的电价曲线")

    assert dummy.errors == []
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_META_KEY]["source_name"] == "price_curve_template_down_grid.csv"
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_META_KEY]["row_count"] == 8784
    assert dummy.session_state[app.PROJECT_PRICE_CURVE_DATA_KEY].matched_columns["energy_market_price_with_vat"]


def test_sample_curve_loader_ignores_price_curve_templates(tmp_path, monkeypatch):
    import green_direct.ui.app as app

    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    for filename in [
        "load_curve.csv",
        "pv_curve.csv",
        "wind_curve.csv",
        "price_curve_template_down_grid.csv",
    ]:
        (sample_dir / filename).write_text("timestamp,value\n2020-01-01,1\n", encoding="utf-8")

    monkeypatch.setattr(app, "PROJECT_ROOT", tmp_path)

    assigned, messages = app._load_sample_curve_files()

    assert set(assigned) == {"负荷", "光伏", "风电"}
    assert not any("price_curve_template_down_grid.csv" in message for message in messages)


def test_price_curve_upload_is_project_level_not_economy_page_upload():
    app_source = Path("src/green_direct/ui/app.py").read_text(encoding="utf-8")

    assert "key=\"simulation_price_curve_upload\"" in app_source
    assert "key=\"economy_price_curve_upload\"" not in app_source


def test_simulation_page_removes_developer_facing_explanatory_copy():
    app_source = Path("src/green_direct/ui/app.py").read_text(encoding="utf-8")

    assert "任务边界" not in app_source
    assert "本页仍完整保留曲线上传" not in app_source
    assert "已上传逐时下网电价曲线" not in app_source
    assert "自动使用" not in app_source


def test_economy_result_keeps_price_curve_alignment_diagnostics_visible():
    app_source = Path("src/green_direct/ui/app.py").read_text(encoding="utf-8")

    assert '"price_curve_diagnostics": economic_study_result.price_curve_diagnostics' in app_source
    assert "价格曲线对齐诊断" in app_source


def test_simulation_capacity_input_survives_workflow_navigation():
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.session_state["workflow_page"] = "方案仿真"
    app_test.run(timeout=10)

    pv_end = next(widget for widget in app_test.number_input if widget.label == "光伏容量结束")
    pv_end.set_value(18.0).run(timeout=10)
    next(button for button in app_test.button if button.label == "03  经济测算").click().run(timeout=10)
    next(button for button in app_test.button if button.label == "02  方案仿真").click().run(timeout=10)
    pv_end_after_return = next(widget for widget in app_test.number_input if widget.label == "光伏容量结束")

    assert pv_end_after_return.value == 18.0
    assert len(app_test.exception) == 0


def test_simulation_page_exposes_parallel_worker_control():
    import green_direct.ui.app as app
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file("src/green_direct/ui/app.py")
    app_test.session_state["workflow_page"] = "方案仿真"
    app_test.run(timeout=10)

    worker_input = next(widget for widget in app_test.number_input if widget.label == "并行计算进程数")

    assert worker_input.value == 1
    assert "simulation_parallel_workers" in app.SIMULATION_WIDGET_STATE_KEYS
    assert len(app_test.exception) == 0


def test_simple_markdown_report_mentions_typical_day_method():
    from green_direct.ui.app import _build_simple_report_markdown

    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "方案类型": "风光储方案",
                "pv_capacity": 10.0,
                "wind_capacity": 5.0,
                "bess_power": 2.0,
                "bess_energy": 4.0,
                "pass_policy": True,
                "green_load_rate": 0.4,
                "self_use_rate": 0.7,
                "export_rate": 0.1,
                "curtail_rate": 0.05,
            }
        ]
    )

    report = _build_simple_report_markdown(
        summary=summary,
        selected_scenario_id="S0001",
        economy_summary=None,
        single_entity_summary=None,
    ).decode("utf-8-sig")

    assert "季节中心日法" in report
    assert "S0001" in report


def test_topbar_data_range_uses_hourly_detail_timestamp():
    from green_direct.ui.app import _data_range_status

    batch_result = SimpleNamespace(
        hourly_details={
            "S0001": pd.DataFrame(
                {
                    "timestamp": pd.date_range("2024-01-01", periods=24, freq="h"),
                }
            )
        }
    )

    value, detail = _data_range_status(batch_result)

    assert value == "2024-01-01 ~ 2024-01-01"
    assert detail == "24 小时"


def test_recommendation_status_display_does_not_mark_no_candidate_as_ok():
    from green_direct.ui.app import _recommendation_status_display

    assert _recommendation_status_display("selected") == ("已入选", "ok")
    assert _recommendation_status_display("no_candidate") == ("无候选", "warn")
    assert _recommendation_status_display("pending") == ("待排序", "pending")


def test_first_report_scenario_prefers_valid_recommendation_portfolio_id():
    from green_direct.ui.app import _first_report_scenario_id

    summary = pd.DataFrame({"scenario_id": ["S0001", "S0002"]})
    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S9999", "S0002"]})
    )

    assert _first_report_scenario_id(summary, recommendation_result) == "S0002"


def test_default_export_scenario_prefers_current_then_recommendation():
    from green_direct.ui.app import _default_export_scenario_id

    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S9999", "S0002", "S0003"]})
    )

    assert _default_export_scenario_id(["S0001", "S0002", "S0003"], "S0003", recommendation_result) == "S0003"
    assert _default_export_scenario_id(["S0001", "S0002", "S0003"], None, recommendation_result) == "S0002"
    assert _default_export_scenario_id(["S0001", "S0002"], "S9999", None) == "S0001"


def test_dashboard_representative_summary_follows_portfolio_order():
    from green_direct.ui.app import _representative_summary_for_dashboard

    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002", "S0003"],
            "pv_capacity": [5.0, 10.0, 15.0],
            "wind_capacity": [0.0, 5.0, 10.0],
            "bess_power": [0.0, 2.0, 4.0],
            "bess_energy": [0.0, 8.0, 16.0],
        }
    )
    recommendation_result = SimpleNamespace(
        portfolio=pd.DataFrame({"scenario_id": ["S0003", "S9999", "S0001"]})
    )

    dashboard_summary = _representative_summary_for_dashboard(summary, recommendation_result)

    assert dashboard_summary["scenario_id"].tolist() == ["S0003", "S0001"]


def test_chart_summary_merges_landed_price_context_without_overwriting_technical_fields():
    from green_direct.ui.app import _merge_landed_price_context

    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "green_load_rate": [0.40, 0.55],
            "pv_capacity": [5.0, 10.0],
        }
    )
    economy = pd.DataFrame(
        {
            "scenario_id": ["S0002", "S0001"],
            "green_load_rate": [0.99, 0.88],
            "load_landed_price_before_green_with_vat": [0.65, 0.65],
            "load_landed_price_after_green_with_vat": [0.58, 0.60],
            "weighted_down_grid_landed_price_with_vat": [0.66, 0.64],
        }
    )

    merged = _merge_landed_price_context(summary, economy)

    assert merged["green_load_rate"].tolist() == [0.40, 0.55]
    assert merged.set_index("scenario_id").loc["S0001", "load_landed_price_after_green_with_vat"] == pytest.approx(0.60)
    assert merged.set_index("scenario_id").loc["S0002", "weighted_down_grid_landed_price_with_vat"] == pytest.approx(0.66)


def test_compact_dashboard_figures_use_real_fields():
    from green_direct.ui.app import (
        _build_capacity_comparison_figure,
        _build_compact_policy_comparison_figure,
        _build_compact_typical_day_figure,
    )

    comparison = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [5.0, 10.0],
            "wind_capacity": [0.0, 5.0],
            "bess_power": [0.0, 2.0],
            "bess_energy": [0.0, 8.0],
            "green_load_rate": [0.34, 0.65],
            "self_use_rate": [0.76, 0.74],
            "curtail_rate": [0.04, 0.03],
            "export_rate": [0.20, 0.10],
        }
    )
    policy_fig, missing = _build_compact_policy_comparison_figure(
        comparison,
        {"green_load_rate": 0.3, "self_use_rate": 0.6, "export_rate": 0.2},
    )

    assert missing == []
    assert policy_fig is not None
    assert policy_fig.data[0].type == "heatmap"
    assert list(policy_fig.data[0].x) == ["绿电占比≥30%", "自发自用率≥60%", "弃电率 低优", "上网比例≤20%"]
    assert [round(value, 4) for value in policy_fig.data[0].z[0]] == [0.04, 0.16, -0.04, 0.0]
    assert "达标余量" in str(policy_fig.to_plotly_json())
    assert "低弃电偏离" in str(policy_fig.to_plotly_json())

    capacity_fig, missing = _build_capacity_comparison_figure(comparison)
    assert missing == []
    assert capacity_fig is not None
    assert capacity_fig.data[0].type == "heatmap"
    assert list(capacity_fig.data[0].x) == ["光伏<br>万kW", "风电<br>万kW", "储能功率<br>万kW", "储能容量<br>万kWh"]
    assert list(capacity_fig.data[0].text[0]) == ["5", "0", "0", "0"]

    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-07-01", periods=48, freq="h"),
            "load_power": [20.0] * 48,
            "pv_generation_power": [0.0] * 6 + [12.0] * 10 + [0.0] * 32,
            "wind_generation_power": [6.0] * 48,
            "bess_charge_power": [0.0] * 48,
            "bess_discharge_power": [1.0] * 48,
            "grid_import_power": [8.0] * 48,
            "grid_export_power": [0.5] * 48,
            "curtail_power": [0.1] * 48,
            "soc_end": [0.5] * 48,
        }
    )
    typical_fig, label, method = _build_compact_typical_day_figure(hourly, "夏季")

    assert typical_fig is not None
    assert "/" in label
    assert "季节中心日法" in method


def test_chart_overview_page_does_not_embed_export_handoff():
    import inspect
    import green_direct.ui.app as app

    source = inspect.getsource(app._render_chart_overview_page)
    dashboard_source = inspect.getsource(app._render_recommendation_dashboard_overview)

    assert "_render_recommendation_export_handoff" not in source
    assert "高级：典型日、能量流向与完整图表复核" not in source
    assert "容量配置结构矩阵" in dashboard_source
    assert "容量配置指纹矩阵" not in dashboard_source
    assert "详细图表方案（全部已计算方案）" in source
    assert "_render_scenario_quick_select_buttons" in source
    assert "_chart_overview_pending_detail_scenario" in source
    assert "show_overview=False" in source
    assert "show_hero=False" in source


def test_chart_html_zip_contains_html_and_meta_files():
    from green_direct.ui.app import _build_chart_html_zip, _comparison_summary_from_portfolio

    hours = 72
    hourly = pd.DataFrame(
        {
            "scenario_id": ["S0001"] * hours,
            "timestamp": pd.date_range("2020-03-01", periods=hours, freq="h"),
            "load_power": [10.0] * hours,
            "direct_self_use_power": [4.0] * hours,
            "bess_discharge_power": [1.0] * hours,
            "grid_import_power": [5.0] * hours,
            "bess_charge_power": [0.5] * hours,
            "grid_export_power": [0.2] * hours,
            "curtail_power": [0.1] * hours,
            "renewable_power": [5.0] * hours,
            "station_use_power": [0.0] * hours,
            "soc_end": [0.5] * hours,
        }
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002", "S0003"],
            "pv_capacity": [10.0, 20.0, 30.0],
            "wind_capacity": [5.0, 10.0, 15.0],
            "bess_power": [2.0, 3.0, 4.0],
            "bess_energy": [4.0, 6.0, 8.0],
            "self_use_rate": [0.7, 0.8, 0.82],
            "green_load_rate": [0.35, 0.4, 0.42],
            "export_rate": [0.1, 0.12, 0.13],
            "curtail_rate": [0.05, 0.03, 0.02],
            "self_use_energy": [100.0, 120.0, 130.0],
            "grid_export_energy": [10.0, 12.0, 13.0],
            "curtail_energy": [5.0, 4.0, 3.0],
            "bess_loss_energy": [1.0, 1.5, 1.8],
        }
    )
    portfolio = pd.DataFrame({"scenario_id": ["S0002"]})
    comparison = _comparison_summary_from_portfolio(summary, "S0001", portfolio)

    content = _build_chart_html_zip(summary, "S0001", hourly, comparison_summary=comparison)
    names = ZipFile(BytesIO(content)).namelist()
    readme = ZipFile(BytesIO(content)).read("README.md").decode("utf-8-sig")

    assert "README.md" in names
    assert any(name.endswith(".html") for name in names)
    assert any("typical" in name and name.endswith("_meta.md") for name in names)
    typical_html = [name for name in names if name.startswith("typical_") and name.endswith(".html")]
    key_day_html = [name for name in names if name.startswith("key_day_") and name.endswith(".html")]
    assert len(typical_html) == 4
    assert any("spring" in name for name in typical_html)
    assert any("winter" in name for name in typical_html)
    assert not any(any(date_part in name for date_part in ["03_01", "03_02", "03_03"]) for name in typical_html)
    assert len(key_day_html) == 5
    assert any(name.startswith("full_year_operation_") and name.endswith(".html") for name in names)
    assert comparison["scenario_id"].tolist() == ["S0002", "S0001"]
    assert "多方案对比范围：2 个方案" in readme
    assert "文件名不嵌入日期" in readme


def test_chart_png_docx_zip_contains_png_manifest_and_matches_html(monkeypatch):
    import green_direct.ui.app as app

    hours = 72
    hourly = pd.DataFrame(
        {
            "scenario_id": ["S0001"] * hours,
            "timestamp": pd.date_range("2020-03-01", periods=hours, freq="h"),
            "load_power": [10.0] * hours,
            "direct_self_use_power": [4.0] * hours,
            "bess_discharge_power": [1.0] * hours,
            "grid_import_power": [5.0] * hours,
            "bess_charge_power": [0.5] * hours,
            "grid_export_power": [0.2] * hours,
            "curtail_power": [0.1] * hours,
            "renewable_power": [5.0] * hours,
            "station_use_power": [0.0] * hours,
            "soc_end": [0.5] * hours,
        }
    )
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [10.0, 20.0],
            "wind_capacity": [5.0, 10.0],
            "bess_power": [2.0, 3.0],
            "bess_energy": [4.0, 6.0],
            "self_use_rate": [0.7, 0.8],
            "green_load_rate": [0.35, 0.4],
            "export_rate": [0.1, 0.12],
            "curtail_rate": [0.05, 0.03],
            "self_use_energy": [100.0, 120.0],
            "grid_export_energy": [10.0, 12.0],
            "curtail_energy": [5.0, 4.0],
            "bess_loss_energy": [1.0, 1.5],
        }
    )
    comparison = app._comparison_summary_from_portfolio(summary, "S0001", pd.DataFrame({"scenario_id": ["S0002"]}))

    def fake_png_bytes(result, profile):
        return f"png:{result.chart_id}:{profile.width_px}:{profile.height_for(result)}".encode("utf-8")

    def fake_png_bytes_batch(results, profile):
        return [fake_png_bytes(result, profile) for result in results]

    monkeypatch.setattr(app, "chart_to_png_bytes", fake_png_bytes)
    monkeypatch.setattr(app, "charts_to_png_bytes_batch", fake_png_bytes_batch)

    html_content = app._build_chart_html_zip(summary, "S0001", hourly, comparison_summary=comparison)
    progress_events = []
    png_content, warnings = app._build_chart_png_docx_zip(
        summary,
        "S0001",
        hourly,
        comparison_summary=comparison,
        progress_callback=lambda done, total, name: progress_events.append((done, total, name)),
    )

    html_names = ZipFile(BytesIO(html_content)).namelist()
    png_archive = ZipFile(BytesIO(png_content))
    png_names = png_archive.namelist()
    readme = png_archive.read("README.md").decode("utf-8-sig")
    manifest = pd.read_csv(BytesIO(png_archive.read("chart_manifest.csv")))

    assert warnings == []
    assert "README.md" in png_names
    assert "chart_manifest.csv" in png_names
    assert any(name.endswith(".png") for name in png_names)
    assert "16 cm" in readme
    html_prefixes = {name.removesuffix(".html") for name in html_names if name.endswith(".html")}
    png_prefixes = {name.removesuffix(".png") for name in png_names if name.endswith(".png")}
    assert png_prefixes == html_prefixes
    assert set(manifest["file_name"]) == {f"{prefix}.png" for prefix in png_prefixes}
    assert any(name.startswith("key_day_") and name.endswith(".png") for name in png_names)
    assert any(name.startswith("full_year_operation_") and name.endswith(".png") for name in png_names)
    assert not any(any(date_part in name for date_part in ["03_01", "03_02", "03_03"]) for name in png_names if name.startswith("typical_"))
    assert manifest["width_px"].eq(1800).all()
    assert "同一套颜色和显示口径" in readme
    assert progress_events[0][0] == 0
    assert progress_events[-1][0] == progress_events[-1][1]
    assert progress_events[-1][1] == len(png_prefixes)


def test_chart_png_docx_signature_changes_when_export_data_changes():
    import green_direct.ui.app as app

    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "self_use_rate": [0.7, 0.8],
            "green_load_rate": [0.35, 0.4],
        }
    )
    comparison = summary.copy()
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=2, freq="h"),
            "load_power": [1.0, 2.0],
        }
    )
    changed_hourly = hourly.copy()
    changed_hourly.loc[0, "load_power"] = 9.0
    changed_summary = summary.copy()
    changed_summary.loc[0, "self_use_rate"] = 0.9

    base_signature = app._chart_png_docx_export_signature("S0001", summary, hourly, comparison)

    assert app._chart_png_docx_export_signature("S0001", summary, changed_hourly, comparison) != base_signature
    assert app._chart_png_docx_export_signature("S0001", changed_summary, hourly, comparison) != base_signature


def test_chart_png_docx_background_job_stores_finished_result(monkeypatch):
    import green_direct.ui.app as app

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {app.CHART_PNG_DOCX_SESSION_ID_KEY: "unit-session"}

    def fake_build_zip(summary, selected_scenario_id, hourly, comparison_summary=None, progress_callback=None):
        if progress_callback:
            progress_callback(1, 2, "第一张图")
            progress_callback(2, 2, "完成")
        return b"fake-zip", []

    signature = "unit-test-background-png"
    app._CHART_PNG_DOCX_JOBS.pop(app._chart_png_docx_job_key(signature, session_id="unit-session"), None)
    monkeypatch.setattr(app, "_build_chart_png_docx_zip", fake_build_zip)
    monkeypatch.setattr(app, "_save_runtime_snapshot", lambda st: None)

    job = app._submit_chart_png_docx_job(
        signature,
        pd.DataFrame({"scenario_id": ["S0001"]}),
        "S0001",
        pd.DataFrame({"timestamp": pd.date_range("2020-01-01", periods=1, freq="h")}),
        pd.DataFrame({"scenario_id": ["S0001"]}),
        session_id="unit-session",
    )
    job["future"].result(timeout=5)
    fake_st = FakeStreamlit()

    status = app._poll_chart_png_docx_job(fake_st, signature)

    assert status["status"] == "complete"
    assert fake_st.session_state["chart_png_docx_export"]["data"] == b"fake-zip"
    assert fake_st.session_state["chart_png_docx_export"]["signature"] == signature
    assert job["progress"] == {"completed": 2, "total": 2, "message": "完成"}


def test_clear_chart_export_cache_removes_session_job():
    import green_direct.ui.app as app

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                app.CHART_PNG_DOCX_SESSION_ID_KEY: "unit-session-clear",
                "chart_png_docx_active_signature": "sig-clear",
                "chart_png_docx_export": {"data": b"old"},
                "chart_png_docx_export_error": "old-error",
            }

    dummy = FakeStreamlit()
    job_key = app._chart_png_docx_job_key("sig-clear", session_id="unit-session-clear")
    app._CHART_PNG_DOCX_JOBS[job_key] = {"future": Future()}

    app._clear_chart_export_cache(dummy)

    assert "chart_png_docx_export" not in dummy.session_state
    assert "chart_png_docx_export_error" not in dummy.session_state
    assert "chart_png_docx_active_signature" not in dummy.session_state
    assert job_key not in app._CHART_PNG_DOCX_JOBS


def test_single_entity_annual_workbook_has_context_and_field_explanations():
    from green_direct.ui.app import _build_single_entity_annual_workbook_bytes

    scenario_id = "S0165"
    annual = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "year": 0,
                "operation_year": 0,
                "period_type": "construction",
                "self_use_energy": 0.0,
                "grid_export_energy": 0.0,
                "net_avoided_grid_cost_price": 0.5,
                "avoided_grid_purchase_cash_price": 0.5,
                "self_use_saving": 0.0,
                "avoided_grid_purchase_cash_saving": 0.0,
                "environmental_value": 0.0,
                "grid_export_revenue_without_vat": 0.0,
                "other_external_revenue_without_vat": 0.0,
                "operating_cost_basis": 0.0,
                "bess_replacement_basis": 0.0,
                "bess_replacement_cash_outflow_with_vat": 0.0,
                "initial_investment_basis": 100.0,
                "construction_cash_outflow_with_vat": 110.0,
                "pre_tax_net_cash_flow": -100.0,
                "cumulative_net_cash_flow": -100.0,
                "discount_factor": 1.0,
                "discounted_net_cash_flow": -100.0,
                "cumulative_discounted_net_cash_flow": -100.0,
            }
        ]
    )
    technical_summary = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "方案类型": "风光储方案",
                "pv_capacity": 10.0,
                "wind_capacity": 5.0,
                "bess_power": 2.0,
                "bess_energy": 4.0,
                "pass_policy": True,
                "green_load_rate": 0.4,
                "self_use_rate": 0.7,
                "export_rate": 0.1,
                "curtail_rate": 0.05,
            }
        ]
    )
    economic_summary = pd.DataFrame(
        [
            {
                "scenario_id": scenario_id,
                "single_entity_firr_pre_tax": 0.12,
                "single_entity_firr_status": "ok",
                "single_entity_fnpv_pre_tax": 20.0,
                "initial_investment_basis": 100.0,
                "construction_cash_outflow_with_vat": 110.0,
                "net_avoided_grid_cost_price": 0.5,
            }
        ]
    )

    content = _build_single_entity_annual_workbook_bytes(
        scenario_id=scenario_id,
        annual=annual,
        technical_summary=technical_summary,
        economic_summary=economic_summary,
    )
    workbook = pd.ExcelFile(BytesIO(content))

    assert workbook.sheet_names == ["方案说明", "年度现金流", "字段说明"]
    annual_sheet = pd.read_excel(workbook, sheet_name="年度现金流")
    field_sheet = pd.read_excel(workbook, sheet_name="字段说明")
    scenario_sheet = pd.read_excel(workbook, sheet_name="方案说明")

    assert any(str(column).startswith("1. ") for column in annual_sheet.columns)
    assert "储能容量(万kWh)" in scenario_sheet["项目"].tolist()
    assert any("=5×7" in str(value) for value in field_sheet["计算/含义说明"])
