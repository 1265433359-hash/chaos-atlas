def test_openai_compatible_backend_imports_without_optional_scenario_modules():
    from tools.chaos_eater_adapter.llm_backend import OpenAICompatBackend

    backend = OpenAICompatBackend(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
    )
    assert backend.name == "openai-compatible:deepseek-v4-flash"
