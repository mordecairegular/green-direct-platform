"""Application service layer wrappers."""

from green_direct.services.job_store import LocalJobStore
from green_direct.services.pilot_access import PilotAccessError, PilotAccessService
from green_direct.services.pilot_admin import LocalPilotAdminService, PilotAdminError
from green_direct.services.pilot_auth import (
    LocalPilotAuth,
    PilotAuthError,
    PilotLoginSession,
    PilotSessionRecord,
)
from green_direct.services.pilot_registry import LocalPilotRegistry
from green_direct.services.result_store import LocalResultStore
from green_direct.services.study_runner import (
    EconomicStudyResult,
    RecommendationInputSnapshot,
    RecommendationStudyResult,
    StudyResult,
    TechnicalStudyInput,
    TechnicalStudyResult,
    build_recommendation_study,
    run_economic_study,
    run_technical_study,
)

__all__ = [
    "EconomicStudyResult",
    "LocalJobStore",
    "LocalPilotAdminService",
    "LocalPilotAuth",
    "LocalPilotRegistry",
    "LocalResultStore",
    "PilotAccessError",
    "PilotAuthError",
    "PilotAccessService",
    "PilotAdminError",
    "PilotLoginSession",
    "PilotSessionRecord",
    "RecommendationInputSnapshot",
    "RecommendationStudyResult",
    "StudyResult",
    "TechnicalStudyInput",
    "TechnicalStudyResult",
    "build_recommendation_study",
    "run_economic_study",
    "run_technical_study",
]
