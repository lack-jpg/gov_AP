"""
test_conversation - 多轮对话：历史格式化 + 初始 State 注入（DB-free 逻辑层）
"""
from __future__ import annotations

from backend.services.conversation_service import format_history_text, new_conversation_id
from orchestration.langgraph.state import create_initial_state


def test_new_conversation_id():
    cid = new_conversation_id()
    assert cid.startswith("conv_")
    assert len(cid) > 10


def test_format_history_text():
    history = [
        {"role": "user", "content": "第一问：想开餐馆"},
        {"role": "assistant", "content": "第一答：需要执照"},
        {"role": "user", "content": "第二问：那还要什么材料？"},
        {"role": "assistant", "content": "第二答：需要食品许可"},
        {"role": "user", "content": "第三问：在哪里办理？"},
        {"role": "assistant", "content": "第三答：政务大厅"},
    ]
    text = format_history_text(history, max_turns=2)
    assert "用户" in text
    assert "助手" in text
    # 最近 2 轮 = 4 条消息，最旧的前 2 条被截掉
    assert "第三答" in text
    assert "第一问" not in text


def test_format_history_text_empty():
    assert format_history_text([], max_turns=4) == ""
    assert format_history_text(None, max_turns=4) == ""


def test_create_initial_state_with_history():
    """多轮对话：messages + conversation_history 注入初始 State。"""
    state = create_initial_state(
        user_query="那还需要哪些材料？",
        messages=[{"role": "user", "content": "我想开一家餐馆需要什么手续？"}],
        conversation_history="用户: 我想开一家餐馆需要什么手续？",
    )
    assert state["messages"] == [{"role": "user", "content": "我想开一家餐馆需要什么手续？"}]
    assert state["conversation_history"] == "用户: 我想开一家餐馆需要什么手续？"
    assert state["user_query"] == "那还需要哪些材料？"


def test_create_initial_state_defaults():
    """单轮对话默认空历史。"""
    state = create_initial_state("开公司需要什么", trace_id="trace_x")
    assert state["messages"] == []
    assert state["conversation_history"] == ""
    assert state["trace_id"] == "trace_x"
