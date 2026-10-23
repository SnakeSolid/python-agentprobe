from agentprobe.agent.ui import ConsoleUi, NoOpUi, error_label
from agentprobe.llm.types import ToolResult
from agentprobe.logging.console import Console


def _console(level: str = "info") -> Console:
    return Console(level=level, color="never", truncate=20)


def test_error_label():
    assert error_label(ToolResult(call_id="1", name="write", content="ok")) is None
    assert error_label(
        ToolResult(call_id="1", name="write", content="ERROR: sandbox_violation: /etc/passwd", is_error=True)
    ) == "sandbox_violation: /etc/passwd"
    assert error_label(ToolResult(call_id="1", name="w", content="", is_error=True)) == "error"


def test_noop_ui_is_noop(capsys):
    ui = NoOpUi()
    ui.segment_start(); ui.chunk("abc"); ui.segment_end()
    ui.tool("read", {"path": "x"}, 1.0)
    ui.turn_start(None, tools_count=1, messages_count=2)
    ui.turn_end(None, 5.0)
    assert capsys.readouterr().out == ""


def test_repl_streams_assistant(capsys):
    ui = ConsoleUi(_console(), mode="repl")
    ui.segment_start()
    ui.chunk("Hello")
    ui.chunk(" world")
    ui.segment_end()
    out = capsys.readouterr().out
    assert "[assistant]" in out
    assert "Hello world" in out


def test_repl_empty_segment_prints_nothing(capsys):
    ui = ConsoleUi(_console(), mode="repl")
    ui.segment_start()
    ui.segment_end()
    assert capsys.readouterr().out == ""


def test_repl_tool_line_at_info(capsys):
    ui = ConsoleUi(_console(), mode="repl")
    ui.tool("read_doc", {"name": "security_policy"}, 2.0)
    out = capsys.readouterr().out
    assert "read_doc(name=security_policy)" in out
    assert "[2ms]" in out


def test_repl_tool_suppressed_at_quiet(capsys):
    ui = ConsoleUi(_console(level="quiet"), mode="repl")
    ui.tool("read_doc", {"name": "security_policy"}, 2.0)
    assert capsys.readouterr().out == ""


def test_repl_tool_error_suffix(capsys):
    ui = ConsoleUi(_console(), mode="repl")
    ui.tool("write", {"path": "/etc/passwd"}, 1.0, "sandbox_violation")
    assert "ERROR: sandbox_violation" in capsys.readouterr().out


def test_headless_tool_prefix(capsys):
    ui = ConsoleUi(_console(), mode="headless", scenario="firewall-permit-tcp")
    ui.tool("read_doc", {"name": "vrp_basic"}, 2.0)
    out = capsys.readouterr().out
    assert "[scenario firewall-permit-tcp]" in out
    assert "read_doc(name=vrp_basic)" in out
    assert "[2ms]" in out


def test_headless_tool_msg_number(capsys):
    ui = ConsoleUi(_console(), mode="headless", scenario="firewall-permit-tcp")
    ui.tool("read_doc", {"name": "acl"}, 5.0, "doc_not_found: acl", msg=3)
    out = capsys.readouterr().out
    assert "(msg 3)" in out
    assert "ERROR: doc_not_found: acl" in out


def test_headless_assistant_only_verbose(capsys):
    # info: buffered, not printed
    ui = ConsoleUi(_console(), mode="headless", scenario="s")
    ui.segment_start(); ui.chunk("hidden at info"); ui.segment_end()
    assert capsys.readouterr().out == ""
    # verbose: printed as [assistant]
    ui = ConsoleUi(_console(level="verbose"), mode="headless", scenario="s")
    ui.segment_start(); ui.chunk("shown at verbose"); ui.segment_end()
    assert "[assistant] shown at verbose" in capsys.readouterr().out


def test_headless_assistant_trims_trailing_whitespace(capsys):
    ui = ConsoleUi(_console(level="verbose"), mode="headless", scenario="s")
    ui.segment_start(); ui.chunk("Let me check the docs.\n\n\n"); ui.segment_end()
    out = capsys.readouterr().out
    assert "[assistant] Let me check the docs." in out
    assert "\n\n\n" not in out  # buffered trailing newlines trimmed


def test_verbose_turn_metadata(capsys):
    class Ctx:
        turn = 1
        tokens_in = 100
        tokens_out = 20
    ui = ConsoleUi(_console(level="verbose"), mode="repl")
    ui.turn_start(Ctx(), tools_count=9, messages_count=2)
    out = capsys.readouterr().out
    assert "turn 1" in out and "tools=9" in out and "messages=2" in out
    ui.turn_end(Ctx(), 640.0)
    assert "turn_end 1" in capsys.readouterr().out
