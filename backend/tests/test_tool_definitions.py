import pytest
from services.tools.definitions import get_price_tool, tools_list


def test_tools_list_not_empty():
    assert len(tools_list) > 0


def test_get_price_tool_schema():
    tool = get_price_tool
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "get_price"
    assert "symbol" in tool["function"]["parameters"]["properties"]
    assert "symbol" in tool["function"]["parameters"]["required"]


def test_all_tools_have_required_fields():
    for tool in tools_list:
        assert "type" in tool
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]
