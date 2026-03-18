from app.core.config import get_settings


def test_provider_api_keys_are_loaded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("BING_API_KEY", "bing-secret")
    monkeypatch.setenv("BING_API_ENDPOINT", "https://bing.example/search")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-secret")
    monkeypatch.setenv("GOOGLE_CSE_ID", "custom-search-id")
    monkeypatch.setenv("DUCKDUCKGO_API_KEY", "ddg-secret")

    settings = get_settings()

    assert settings.has_provider_api_key("bing") is True
    assert settings.provider_api_credentials("bing") == {
        "api_key": "bing-secret",
        "api_endpoint": "https://bing.example/search",
        "custom_search_id": None,
    }
    assert settings.provider_api_credentials("brave")["api_key"] == "brave-secret"
    assert settings.provider_api_credentials("google") == {
        "api_key": "google-secret",
        "api_endpoint": None,
        "custom_search_id": "custom-search-id",
    }
    assert settings.provider_api_credentials("duckduckgo")["api_key"] == "ddg-secret"


def test_provider_api_keys_default_to_empty() -> None:
    settings = get_settings()

    assert settings.has_provider_api_key("bing") is False
    assert settings.provider_api_credentials("google") == {
        "api_key": None,
        "api_endpoint": None,
        "custom_search_id": None,
    }
