from agentprobe.prompt.builder import PromptBuilder
from agentprobe.skills.loader import SkillLoader


def _write_skill(root, folder, name, description, body="body", include_frontmatter=True):
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    if include_frontmatter:
        content = f"---\nname: {name}\ndescription: {description}\n---\n{body}"
    else:
        content = f"no frontmatter\n{body}"
    (d / "SKILL.md").write_text(content)


def test_skill_loader_valid(tmp_path):
    _write_skill(tmp_path, "my_skill", "my_skill", "does things")
    loader = SkillLoader(tmp_path)
    assert loader.skill_names() == ["my_skill"]
    assert "my_skill" in loader.available_skills_block()
    assert "does things" in loader.available_skills_block()


def test_skill_loader_folder_mismatch_skipped(tmp_path):
    _write_skill(tmp_path, "folder_x", "other_name", "desc")
    loader = SkillLoader(tmp_path)
    assert loader.skill_names() == []


def test_skill_loader_missing_frontmatter_skipped(tmp_path):
    _write_skill(tmp_path, "plain", "plain", "desc", include_frontmatter=False)
    loader = SkillLoader(tmp_path)
    assert loader.skill_names() == []


def test_prompt_builder_appends_memory_and_skills(tmp_path):
    _write_skill(tmp_path / "skills", "s1", "s1", "skill desc")
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("BASE PROMPT")
    mem = tmp_path / "MEMORY.md"
    mem.write_text("remembered fact")
    loader = SkillLoader(tmp_path / "skills")
    text = PromptBuilder(prompt_file, mem, loader).build()
    assert text.startswith("BASE PROMPT")
    assert "# MEMORY" in text
    assert "remembered fact" in text
    assert "# AVAILABLE SKILLS" in text
    assert "s1" in text


def test_prompt_builder_empty_memory_and_no_skills(tmp_path):
    prompt_file = tmp_path / "system.md"
    prompt_file.write_text("ONLY BASE")
    mem = tmp_path / "MEMORY.md"  # does not exist
    loader = SkillLoader(tmp_path)
    text = PromptBuilder(prompt_file, mem, loader).build()
    assert "# MEMORY" in text
    assert "(empty)" in text
    assert "(none)" in text
