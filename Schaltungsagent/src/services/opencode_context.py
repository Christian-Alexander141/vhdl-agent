"""Context builder for OpenCode prompts.

This module provides a comprehensive context builder that gathers
all relevant project information for OpenCode prompts.
"""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OpenCodeContextBuilder:
    """Builds comprehensive context for OpenCode prompts.
    
    Gathers:
    - Project structure
    - Architecture information
    - RAG knowledge
    - Previous test results
    - Acceptance criteria
    - Expected artifacts
    """
    
    def __init__(self, filesystem_service, rag_service=None):
        self._fs = filesystem_service
        self._rag = rag_service
    
    def build_context(
        self,
        workspace: str,
        task: dict,
        design_state: dict | None = None,
        architecture: dict | None = None,
        previous_results: list[dict] | None = None,
        rag_knowledge: Any = None,
    ) -> str:
        """Build comprehensive context for OpenCode.
        
        Args:
            workspace: Project workspace path
            task: Current task information
            design_state: DesignState data (optional)
            architecture: Architecture data (optional)
            previous_results: Previous test/verification results (optional)
            rag_knowledge: RAG knowledge bundle (optional)
        
        Returns:
            Formatted context string
        """
        sections = []
        
        # Project information
        sections.append(self._build_project_section(workspace, task))
        
        # Target FPGA
        sections.append(self._build_fpga_section(design_state))
        
        # Requirements
        sections.append(self._build_requirements_section(design_state, task))
        
        # Architecture
        sections.append(self._build_architecture_section(architecture))
        
        # Current design (existing files)
        sections.append(self._build_current_design_section(workspace))
        
        # Task description
        sections.append(self._build_task_section(task))
        
        # Interfaces
        sections.append(self._build_interfaces_section(architecture))
        
        # Constraints
        sections.append(self._build_constraints_section(workspace, design_state))
        
        # RAG knowledge
        if rag_knowledge:
            sections.append(self._build_rag_section(rag_knowledge))
        
        # Previous failures
        if previous_results:
            sections.append(self._build_previous_failures_section(previous_results))
        
        # Acceptance criteria
        sections.append(self._build_acceptance_criteria_section(task))
        
        # Expected artifacts
        sections.append(self._build_expected_artifacts_section(task))
        
        # Instructions
        sections.append(self._build_instructions_section(task))
        
        return "\n\n".join(filter(None, sections))
    
    def _build_project_section(self, workspace: str, task: dict) -> str:
        """Build project information section."""
        project_id = task.get("project_id", "unknown")
        return f"""PROJECT
=======

workspace: {workspace}
project_id: {project_id}
domain: {task.get("domain", "vhdl")}
created_at: {task.get("created_at", "")}"""
    
    def _build_fpga_section(self, design_state: dict | None) -> str:
        """Build FPGA target section."""
        target_fpga = "arty_s7_50"
        if design_state:
            fpga_info = design_state.get("fpga", {})
            target_fpga = fpga_info.get("target", target_fpga)
        
        return f"""TARGET FPGA
==========

target: {target_fpga}
family: Xilinx Spartan-7
package: csga324"""
    
    def _build_requirements_section(self, design_state: dict | None, task: dict) -> str:
        """Build requirements section."""
        requirements = []
        if design_state:
            for req in design_state.get("requirements", []):
                if isinstance(req, dict):
                    requirements.append(f"- {req.get('description', '')}")
                else:
                    requirements.append(f"- {req}")
        
        if not requirements:
            request = task.get("request", task.get("inputs", {}).get("request", ""))
            requirements = [f"- {request}"]
        
        return f"""REQUIREMENTS
============

{chr(10).join(requirements)}"""
    
    def _build_architecture_section(self, architecture: dict | None) -> str:
        """Build architecture section."""
        if not architecture:
            return "ARCHITECTURE\n============\n\nNo architecture defined yet."
        
        modules = architecture.get("modules", [])
        interfaces = architecture.get("interfaces", {})
        clock_domain = architecture.get("clock_domain", "clk")
        reset_concept = architecture.get("reset_concept", "async_active_high")
        
        modules_text = "\n".join([
            f"- {m.get('name', 'unknown')}: {m.get('type', 'module')} "
            f"(inputs: {m.get('inputs', [])}, outputs: {m.get('outputs', [])})"
            for m in modules
        ]) if modules else "No modules defined"
        
        return f"""ARCHITECTURE
============

clock_domain: {clock_domain}
reset_concept: {reset_concept}

MODULES:
{modules_text}"""
    
    def _build_current_design_section(self, workspace: str) -> str:
        """Build current design section showing existing files."""
        src_files = []
        test_files = []
        
        src_dir = Path(workspace) / "src"
        if src_dir.exists():
            src_files = [f.name for f in src_dir.glob("*.vhd")]
        
        tests_dir = Path(workspace) / "tests"
        if tests_dir.exists():
            test_files = [f.name for f in tests_dir.glob("*.vhd")]
        
        return f"""CURRENT DESIGN
==============

SOURCE FILES:
{chr(10).join(f'- {f}' for f in src_files) if src_files else 'No source files'}

TEST FILES:
{chr(10).join(f'- {f}' for f in test_files) if test_files else 'No test files'}"""
    
    def _build_task_section(self, task: dict) -> str:
        """Build task description section."""
        task_type = task.get("type", "unknown")
        task_id = task.get("id", "unknown")
        description = task.get("description", task.get("inputs", {}).get("request", ""))
        
        return f"""TASK
====

task_id: {task_id}
task_type: {task_type}
description: {description}"""
    
    def _build_interfaces_section(self, architecture: dict | None) -> str:
        """Build interfaces section."""
        if not architecture:
            return "INTERFACES\n==========\n\nNo interfaces defined."
        
        interfaces = architecture.get("interfaces", {})
        if not interfaces:
            return "INTERFACES\n==========\n\nNo interfaces defined."
        
        interfaces_text = []
        for name, signals in interfaces.items():
            if isinstance(signals, dict):
                signals_text = ", ".join([f"{k}: {v}" for k, v in signals.items()])
            else:
                signals_text = str(signals)
            interfaces_text.append(f"- {name}: {signals_text}")
        
        return f"""INTERFACES
==========

{chr(10).join(interfaces_text)}"""
    
    def _build_constraints_section(self, workspace: str, design_state: dict | None) -> str:
        """Build constraints section."""
        constraints_files = []
        constraints_dir = Path(workspace) / "constraints"
        if constraints_dir.exists():
            constraints_files = [f.name for f in constraints_dir.glob("*.xdc")]
        
        return f"""CONSTRAINTS
===========

CONSTRAINT FILES:
{chr(10).join(f'- {f}' for f in constraints_files) if constraints_files else 'No constraint files'}"""
    
    def _build_rag_section(self, rag_knowledge: Any) -> str:
        """Build RAG knowledge section."""
        sections = []
        
        # Coding rules
        coding_rules = getattr(rag_knowledge, 'coding_rules', []) or []
        if coding_rules:
            rules_text = "\n".join([f"- {rule.description}" for rule in coding_rules[:10]])
            sections.append(f"CODING RULES:\n{rules_text}")
        
        # Reference designs
        ref_designs = getattr(rag_knowledge, 'reference_designs', []) or []
        if ref_designs:
            refs_text = "\n".join([f"- {ref.name}: {ref.description}" for ref in ref_designs[:5]])
            sections.append(f"REFERENCE DESIGNS:\n{refs_text}")
        
        # Templates
        template = getattr(rag_knowledge, 'matched_template', None)
        if template:
            sections.append(f"MATCHED TEMPLATE: {template}")
        
        if not sections:
            return ""
        
        return f"""RAG KNOWLEDGE
=============

{chr(10).join(sections)}"""
    
    def _build_previous_failures_section(self, previous_results: list[dict]) -> str:
        """Build previous failures section."""
        failures = []
        for result in previous_results:
            if not result.get("passed", True):
                error = result.get("error", result.get("message", "Unknown error"))
                stage = result.get("stage", "unknown")
                failures.append(f"- [{stage}] {error}")
        
        if not failures:
            return ""
        
        return f"""PREVIOUS FAILURES
=================

{chr(10).join(failures)}"""
    
    def _build_acceptance_criteria_section(self, task: dict) -> str:
        """Build acceptance criteria section."""
        criteria = task.get("acceptance_criteria", [])
        if not criteria:
            # Default criteria based on task type
            task_type = task.get("type", "")
            if "hdl" in task_type or "implement" in task_type:
                criteria = [
                    "GHDL compilation succeeds",
                    "Testbench passes",
                    "Entity ports match architecture",
                ]
            elif "synth" in task_type:
                criteria = [
                    "Vivado synthesis completes",
                    "No timing violations",
                    "Bitstream generated",
                ]
            elif "verify" in task_type:
                criteria = [
                    "All tests pass",
                    "No assertion failures",
                ]
        
        return f"""ACCEPTANCE CRITERIA
===================

{chr(10).join(f'- {c}' for c in criteria) if criteria else 'No specific criteria defined'}"""
    
    def _build_expected_artifacts_section(self, task: dict) -> str:
        """Build expected artifacts section."""
        artifacts = task.get("expected_artifacts", [])
        if not artifacts:
            # Default artifacts based on task type
            task_type = task.get("type", "")
            if "hdl" in task_type or "implement" in task_type:
                artifacts = ["src/*.vhd", "tests/*_tb.vhd"]
            elif "synth" in task_type:
                artifacts = ["build/bitstream/*.bit"]
        
        return f"""EXPECTED ARTIFACTS
==================

{chr(10).join(f'- {a}' for a in artifacts) if artifacts else 'No specific artifacts expected'}"""
    
    def _build_instructions_section(self, task: dict) -> str:
        """Build instructions section."""
        return """INSTRUCTIONS
=============

Implement the task in the existing project.
Reuse existing code where appropriate.
Do not modify unrelated modules.
Run the available tests.
If compilation/simulation fails, diagnose and repair the implementation.
Stop only when the acceptance criteria are satisfied or a genuine blocking issue remains.

IMPORTANT: Write complete, synthesizable VHDL code. Do not include explanatory text."""
