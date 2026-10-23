from agentprobe.prompt.builder import PromptBuilder
from agentprobe.skills.loader import SkillLoader


def test_memory_and_skills_injected(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "s1").mkdir()
    (tmp_path / "skills" / "s1" / "SKILL.md").write_text(
        "---\nname: s1\ndescription: d1\n---\n\nbody\n"
    )
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("# AGENTS\nstatic\n")
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("remember this")
    builder = PromptBuilder(prompt_file, memory_file, SkillLoader(tmp_path / "skills"))
    text = builder.build()
    assert "# AGENTS" in text
    assert "remember this" in text
    assert "AVAILABLE SKILLS" in text
    assert "s1" in text
    assert "d1" in text


def test_missing_memory_empty_section(tmp_path):
    (tmp_path / "skills").mkdir()
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("static")
    builder = PromptBuilder(prompt_file, tmp_path / "nope" / "MEMORY.md", SkillLoader(tmp_path / "skills"))
    text = builder.build()
    assert "(empty)" in text


def test_subagent_no_memory(tmp_path):
    (tmp_path / "skills").mkdir()
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("static")
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("secret memory")
    builder = PromptBuilder(prompt_file, memory_file, SkillLoader(tmp_path / "skills"), include_memory=False)
    text = builder.build()
    assert "secret memory" not in text
    assert "# MEMORY" not in text
