"""Tests for knowledge provisioning (AP9, AP10, AP11, R8, R10)."""
import hashlib
import tempfile
from pathlib import Path

import pytest
import yaml

from src.services.knowledge_provisioner import KnowledgeProvisioner
from src.config import Settings


def test_provision_writes_agents_md():
    """Provision writes AGENTS.md from template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        provisioner = KnowledgeProvisioner(settings)
        
        receipt = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        agents_md = Path(tmpdir) / "AGENTS.md"
        assert agents_md.exists()
        content = agents_md.read_text(encoding="utf-8")
        assert "PROMPT.md has absolute priority" in content
        assert "vhdl-synthesis-rules" in content
        assert "arty-s7-50-board" in content
        assert "AGENTS.md" in receipt.files


def test_provision_writes_skills():
    """Provision writes all skill directories with SKILL.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        provisioner = KnowledgeProvisioner(settings)
        
        receipt = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        skills_dir = Path(tmpdir) / ".opencode" / "skills"
        assert skills_dir.exists()
        
        expected_skills = [
            "vhdl-synthesis-rules",
            "vhdl-fsm",
            "vhdl-testbench",
            "timing-constraints",
            "arty-s7-50-board",
            "ghdl-vivado-errors",
        ]
        
        for skill in expected_skills:
            skill_md = skills_dir / skill / "SKILL.md"
            assert skill_md.exists(), f"Missing {skill}/SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            assert content.startswith("# Skill:"), f"{skill} missing header"
            assert "Quelle:" in content or "UNGEPRÜFT" in content, f"{skill} missing source"
            rel = f".opencode/skills/{skill}/SKILL.md"
            assert rel in receipt.files


def test_provision_writes_board_yaml():
    """Provision writes board facts YAML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        provisioner = KnowledgeProvisioner(settings)
        
        receipt = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        board_yaml = Path(tmpdir) / "knowledge" / "board.yaml"
        assert board_yaml.exists()
        content = yaml.safe_load(board_yaml.read_text(encoding="utf-8"))
        assert content["board_id"] == "arty_s7_50"
        assert "clocks" in content
        assert "leds" in content
        assert "rag_rules" in content
        assert "knowledge/board.yaml" in receipt.files


def test_provision_idempotent():
    """Second provision run produces identical hashes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        provisioner = KnowledgeProvisioner(settings)
        
        receipt1 = provisioner.provision(tmpdir, board_id="arty_s7_50")
        receipt2 = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        assert receipt1.version == receipt2.version
        assert receipt1.files == receipt2.files


def test_provision_does_not_touch_user_files():
    """Provision never overwrites PROMPT.md, src/, tests/, constraints/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        provisioner = KnowledgeProvisioner(settings)
        
        # Create user files first
        (Path(tmpdir) / "PROMPT.md").write_text("My prompt", encoding="utf-8")
        (Path(tmpdir) / "src").mkdir()
        (Path(tmpdir) / "src" / "my.vhd").write_text("my vhdl", encoding="utf-8")
        (Path(tmpdir) / "tests").mkdir()
        (Path(tmpdir) / "tests" / "my_tb.vhd").write_text("my tb", encoding="utf-8")
        (Path(tmpdir) / "constraints").mkdir()
        (Path(tmpdir) / "constraints" / "my.xdc").write_text("my xdc", encoding="utf-8")
        
        # Record hashes before
        before = {
            "PROMPT.md": hashlib.sha256((Path(tmpdir) / "PROMPT.md").read_bytes()).hexdigest(),
            "src/my.vhd": hashlib.sha256((Path(tmpdir) / "src/my.vhd").read_bytes()).hexdigest(),
            "tests/my_tb.vhd": hashlib.sha256((Path(tmpdir) / "tests/my_tb.vhd").read_bytes()).hexdigest(),
            "constraints/my.xdc": hashlib.sha256((Path(tmpdir) / "constraints/my.xdc").read_bytes()).hexdigest(),
        }
        
        provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        # Hashes unchanged
        after = {
            "PROMPT.md": hashlib.sha256((Path(tmpdir) / "PROMPT.md").read_bytes()).hexdigest(),
            "src/my.vhd": hashlib.sha256((Path(tmpdir) / "src/my.vhd").read_bytes()).hexdigest(),
            "tests/my_tb.vhd": hashlib.sha256((Path(tmpdir) / "tests/my_tb.vhd").read_bytes()).hexdigest(),
            "constraints/my.xdc": hashlib.sha256((Path(tmpdir) / "constraints/my.xdc").read_bytes()).hexdigest(),
        }
        assert before == after


def test_provision_disabled_skips():
    """Provision with knowledge.enabled=false does nothing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = False
        provisioner = KnowledgeProvisioner(settings)
        
        receipt = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        assert receipt.version == "0"
        assert receipt.files == {}
        assert not (Path(tmpdir) / "AGENTS.md").exists()
        assert not (Path(tmpdir) / ".opencode").exists()


def test_provision_missing_source_logs_warning():
    """Provision with missing source directory logs warning, doesn't fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        settings.knowledge.enabled = True
        # Point to non-existent knowledge dir
        provisioner = KnowledgeProvisioner(settings)
        provisioner._source_root = Path(tmpdir) / "nonexistent"
        
        receipt = provisioner.provision(tmpdir, board_id="arty_s7_50")
        
        assert receipt.version == "0"
        assert receipt.files == {}


def test_skill_files_have_valid_format():
    """All skill files have valid format (description, kebab-case id, <=200 lines)."""
    skills_root = Path(__file__).resolve().parent.parent / "src" / "knowledge" / "skills"

    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir():
            continue
        
        # Check directory name is kebab-case
        assert skill_dir.name.islower()
        assert all(c.isalnum() or c == '-' for c in skill_dir.name)
        assert not skill_dir.name.startswith('-')
        assert not skill_dir.name.endswith('-')
        
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), f"Missing SKILL.md in {skill_dir.name}"
        
        content = skill_md.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        # Check line count
        assert len(lines) <= 200, f"{skill_dir.name} exceeds 200 lines ({len(lines)})"
        
        # Check header
        assert content.startswith("# Skill:"), f"{skill_dir.name} missing # Skill: header"
        
        # Check description exists (second line after header typically)
        assert "Beschreibung:" in content or "Description:" in content, \
            f"{skill_dir.name} missing Beschreibung"
        
        # Check source
        assert "Quelle:" in content or "UNGEPRÜFT" in content, \
            f"{skill_dir.name} missing Quelle"


def test_agents_md_tpl_valid():
    """AGENTS.md.tpl has valid format (<=150 lines, placeholders)."""
    tpl_path = Path(__file__).resolve().parent.parent / "src" / "knowledge" / "AGENTS.md.tpl"
    assert tpl_path.exists()

    content = tpl_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert len(lines) <= 150, f"AGENTS.md.tpl exceeds 150 lines ({len(lines)})"
    assert "{{skills_list}}" in content
    assert "{{skills_dir}}" in content
    assert "{{board_id}}" in content
    assert "PROMPT.md has absolute priority" in content


def test_knowledge_version_file():
    """VERSION file exists and is readable."""
    version_path = Path(__file__).resolve().parent.parent / "src" / "knowledge" / "VERSION"
    assert version_path.exists()
    version = version_path.read_text(encoding="utf-8").strip()
    assert version.isdigit()


def test_task_runner_includes_knowledge_line():
    """OpenCodeTaskRunner adds knowledge line for each stage."""
    from src.services.opencode_task_runner import OpenCodeTaskRunner, STAGE_SKILLS
    
    # Check all stages have skills defined
    expected_stages = ["plan", "implement_module", "implement_testbench", "implement_top", "review_and_fix"]
    for stage in expected_stages:
        assert stage in STAGE_SKILLS, f"Stage {stage} missing skills"
        assert len(STAGE_SKILLS[stage]) > 0, f"Stage {stage} has empty skills"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])