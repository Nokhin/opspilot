from pathlib import Path

import pytest

from opspilot.cli import bootstrap
from opspilot.config import Settings
from opspilot.orchestration.service import OpsPilotService


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, corpus_dir=Path("corpus/policies"))


@pytest.fixture
def service(settings):
    bootstrap(settings)
    return OpsPilotService(settings)
