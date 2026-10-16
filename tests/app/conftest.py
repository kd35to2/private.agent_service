from unittest.mock import patch

import pytest
import streamlit.config

from schema import AgentInfo, ServiceMetadata
from schema.models import OpenAIModelName


@pytest.fixture(scope="session", autouse=True)
def initialize_streamlit_config():
    # Resolve Windows profile paths before mock_env clears the process environment.
    streamlit.config.get_config_options()


@pytest.fixture
def mock_agent_client(mock_env, monkeypatch):
    """Fixture for creating a mock AgentClient with a clean environment."""
    monkeypatch.setenv("USER_AUTH_ENABLED", "false")

    mock_info = ServiceMetadata(
        default_agent="rag-assistant",
        agents=[
            AgentInfo(key="rag-assistant", description="Test agent"),
        ],
        default_model=OpenAIModelName.GPT_5_NANO,
        models=[OpenAIModelName.GPT_5_NANO, OpenAIModelName.GPT_5_MINI],
    )

    with (
        patch("client.AgentClient") as mock_agent_client,
        patch("voice.VoiceManager.from_env", return_value=None),
    ):
        mock_agent_client_instance = mock_agent_client.return_value
        mock_agent_client_instance.info = mock_info
        # Give the mock a deterministic selected agent.
        mock_agent_client_instance.agent = "rag-assistant"
        yield mock_agent_client_instance
