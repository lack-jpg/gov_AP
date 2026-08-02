"""
prompts - Prompt Registry: centralized prompt management with version control

Author: le
Date: 2026/7/29
Version: 0.2
Task: Prompts package initialization
"""
from __future__ import annotations

from prompts.registry import (
    PromptTemplate,
    PromptRegistry,
    get_registry,
    reset_registry,
    get_prompt,
    get_prompt_with_vars,
)

__all__ = [
    "PromptTemplate",
    "PromptRegistry",
    "get_registry",
    "reset_registry",
    "get_prompt",
    "get_prompt_with_vars",
]
