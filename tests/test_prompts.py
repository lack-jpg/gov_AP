"""
test_prompts - Prompt Registry tests
"""
from __future__ import annotations

import pytest

from prompts.registry import (
    PromptRegistry,
    PromptTemplate,
    get_registry,
    get_prompt,
    get_prompt_with_vars,
    reset_registry,
)


class TestPromptTemplate:
    def test_render(self):
        pt = PromptTemplate(
            name="TEST", agent_name="test",
            role="你是{{ name }}", goal="任务: {{ task }}",
        )
        rendered = pt.render(name="助手", task="查询")
        assert "助手" in rendered
        assert "查询" in rendered

    def test_unresolved_vars_kept(self):
        pt = PromptTemplate(name="TEST", agent_name="test", role="你是{{ missing }}")
        rendered = pt.render()
        assert "{{ missing }}" in rendered


class TestPromptRegistry:
    def setup_method(self):
        reset_registry()
        self.registry = get_registry()

    def test_defaults_loaded(self):
        assert self.registry.get("SUPERVISOR_SYSTEM_PROMPT") is not None
        assert self.registry.get("INTENT_CLASSIFIER_PROMPT") is not None
        assert self.registry.get("POLICY_RAG_PROMPT") is not None

    def test_version_management(self):
        v2 = PromptTemplate(
            name="SUPERVISOR_SYSTEM_PROMPT", agent_name="supervisor", version="v2",
            role="v2版本",
        )
        self.registry.register(v2)
        assert len(self.registry.list_versions("SUPERVISOR_SYSTEM_PROMPT")) == 2

        self.registry.activate_version("SUPERVISOR_SYSTEM_PROMPT", "v2")
        active = self.registry.get_active("SUPERVISOR_SYSTEM_PROMPT")
        assert active.version == "v2"

    def test_render_registry(self):
        result = self.registry.render(
            "SUPERVISOR_SYSTEM_PROMPT",
            user_query="我想开餐馆",
            intent="business_license",
        )
        assert "我想开餐馆" in result
        assert "business_license" in result

    def test_missing_template_raises(self):
        with pytest.raises(ValueError):
            self.registry.render("NONEXISTENT_TEMPLATE")


class TestConvenienceFunctions:
    def setup_method(self):
        reset_registry()

    def test_get_prompt(self):
        assert len(get_prompt("INTENT_CLASSIFIER_PROMPT")) > 0

    def test_get_prompt_with_vars(self):
        result = get_prompt_with_vars(
            "POLICY_RAG_PROMPT",
            user_query="如何查公积金",
            context="《公积金条例》",
        )
        assert "如何查公积金" in result
        assert "《公积金条例》" in result
