from agentprobe.skills.loader import SkillLoader


def test_valid_skill(tmp_path):
    (tmp_path / "skill_a").mkdir()
    (tmp_path / "skill_a" / "SKILL.md").write_text(
        "---\nname: skill_a\ndescription: desc a\n---\n\nbody\n"
    )
    loader = SkillLoader(tmp_path)
    block = loader.available_skills_block()
    assert "skill_a" in block
    assert "desc a" in block


def test_folder_name_mismatch_skipped(tmp_path):
    (tmp_path / "folder_x").mkdir()
    (tmp_path / "folder_x" / "SKILL.md").write_text(
        "---\nname: other\ndescription: desc\n---\n\nbody\n"
    )
    loader = SkillLoader(tmp_path)
    assert loader.available_skills_block() == ""


def test_missing_frontmatter_skipped(tmp_path):
    (tmp_path / "skill_b").mkdir()
    (tmp_path / "skill_b" / "SKILL.md").write_text("no frontmatter\n")
    loader = SkillLoader(tmp_path)
    assert loader.available_skills_block() == ""


def test_incomplete_frontmatter_skipped(tmp_path):
    (tmp_path / "skill_c").mkdir()
    (tmp_path / "skill_c" / "SKILL.md").write_text("---\nname: skill_c\n---\n\nbody\n")
    loader = SkillLoader(tmp_path)
    assert loader.available_skills_block() == ""
