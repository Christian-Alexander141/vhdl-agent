"""Einzelanforderungen vom Prompt bis zur Abschlussprüfung (docs/doku.html, #29).

Anlass: Lauf gray-countdown 2026-10-10. Der Prompt verlangte rote RGB-LEDs bei 0,
der Plan enthielt keinen RGB-Port, alle Prüfungen waren trotzdem grün.
"""
import json
from pathlib import Path

from src.domain.agents import requirements as reqs
from src.domain.agents.repair_routing import RepairTarget, route_repair
from src.domain.agents import AgentResult, AgentStatus
from src.domain.models import DesignStage

from tests.test_multi_agent_gates import make_supervisor, run, set_architecture

PROMPT = (
    "schrebe mir einen Digitaler Countdown-Timer dieser soll im gray code von 15 auf 0 herunterzählen "
    "und dann wieder von vorn anfangen wenn der zähler bei 0 ist sollen die RGB leds rot läuchten "
    "für die zahlen nutze die normalen leds"
)


def _manifest(requirements, rgb_port=True):
    ports = [{"name": "clk", "direction": "in", "type": "std_logic"},
             {"name": "led", "direction": "out", "type": "std_logic_vector(3 downto 0)"}]
    if rgb_port:
        ports.append({"name": "rgb_r", "direction": "out", "type": "std_logic"})
    return {"project_name": "gray-countdown", "top_entity": "gray_countdown",
            "modules": [{"entity": "gray_countdown", "file": "src/gray_countdown.vhd", "depends_on": [], "ports": ports}],
            "requirements": requirements}


RGB = {"id": "R2", "text": "Bei Zählerstand 0 leuchten die RGB-LEDs rot",
       "quote": "wenn der zähler bei 0 ist sollen die RGB leds rot läuchten",
       "modules": ["gray_countdown"], "ports": ["gray_countdown.rgb_r"], "check": "simulation"}
COUNT = {"id": "R1", "text": "Zählt im Gray-Code von 15 auf 0", "quote": "im gray code von 15 auf 0 herunterzählen",
         "modules": ["gray_countdown"], "ports": ["gray_countdown.led"], "check": "simulation"}


# --- Plan ---------------------------------------------------------------------

def test_valid_requirements_are_accepted():
    valid, problems = reqs.check_requirements(_manifest([COUNT, RGB]), PROMPT)
    assert problems == [] and [r["id"] for r in valid] == ["R1", "R2"]


def test_requirement_needing_a_port_the_plan_lacks_is_rejected():
    """Genau der gray-countdown-Fehler: RGB verlangt, aber kein RGB-Port geplant."""
    _, problems = reqs.check_requirements(_manifest([COUNT, RGB], rgb_port=False), PROMPT)
    assert any("gray_countdown.rgb_r" in p and "does not exist" in p for p in problems)


def test_invented_quote_and_unknown_module_are_rejected():
    bad = {**RGB, "quote": "die LEDs blinken grün", "modules": ["nope"]}
    _, problems = reqs.check_requirements(_manifest([bad]), PROMPT)
    assert any("exact excerpt" in p for p in problems) and any("unknown modules" in p for p in problems)


def test_quote_matching_ignores_case_whitespace_and_punctuation():
    assert reqs.quote_in_prompt("Wenn der Zähler bei 0 ist,  sollen die RGB-LEDs rot läuchten", PROMPT)


def test_missing_requirements_go_back_to_the_planner(tmp_path):
    from src.services.plan_service import PlanService
    from tests.test_mas_improvements import _PlanRunner

    runner = _PlanRunner([_manifest([COUNT, RGB], rgb_port=False), _manifest([COUNT, RGB])])
    manifest = PlanService(runner, name_resolver=None).plan(str(tmp_path), PROMPT, task_id="t")
    assert len(runner.instructions) == 2 and "gray_countdown.rgb_r" in runner.instructions[1]
    assert [r["id"] for r in manifest["requirements"]] == ["R1", "R2"]
    assert "RGB LED" in runner.instructions[0]


def test_incomplete_requirements_do_not_end_a_single_attempt_run(tmp_path):
    """Benchmark-Modus (ein Versuch): Sammelanforderung R0 statt Abbruch."""
    from src.services.plan_service import PlanService
    from tests.test_mas_improvements import _PlanRunner

    runner = _PlanRunner([_manifest([COUNT, RGB], rgb_port=False)])
    manifest = PlanService(runner, name_resolver=None, max_attempts=1).plan(str(tmp_path), PROMPT, task_id="t")
    assert [r["id"] for r in manifest["requirements"]] == ["R1", "R0"]
    assert manifest["requirements"][-1]["text"] == PROMPT and manifest["requirements_warnings"]


# --- Testbench-Kennzeichnung ----------------------------------------------------

def test_only_assertions_count_as_requirement_checks():
    sources = {"tb": 'assert led = "1000" report "REQ R1: 15" severity error;\n'}
    gaps = reqs.uncovered_simulation_requirements([COUNT, RGB, {**RGB, "id": "R10"}], sources)
    assert [r["id"] for r in gaps] == ["R2", "R10"]


def test_structure_requirements_need_no_testbench_marker():
    assert reqs.uncovered_simulation_requirements([{**RGB, "check": "structure"}], {}) == []


def test_every_task_after_planning_carries_the_requirements(tmp_path):
    assert reqs.task_instruction_suffix(str(tmp_path), "implement_module") == ""
    (tmp_path / "plan").mkdir()
    (tmp_path / reqs.REQUIREMENTS_FILE).write_text(reqs.render_markdown([COUNT, RGB]))
    assert reqs.REQUIREMENTS_FILE in reqs.task_instruction_suffix(str(tmp_path), "repair")
    assert "REQ <id>" in reqs.task_instruction_suffix(str(tmp_path), "implement_testbench")
    assert reqs.task_instruction_suffix(str(tmp_path), "plan") == ""


# --- Abschlussprüfung -------------------------------------------------------------

def test_review_needs_evidence_and_verbatim_quotes():
    text = json.dumps({
        "requirements": [{"id": "R1", "status": "met", "evidence": "src:12"},
                         {"id": "R2", "status": "not_met", "evidence": ""}],
        "missing": [{"text": "LEDs für Zahlen", "quote": "für die zahlen nutze die normalen leds"},
                    {"text": "erfunden", "quote": "blinkt im Sekundentakt"},
                    {"text": "doppelt", "quote": RGB["quote"]}],
    })
    review = reqs.parse_review(text, [COUNT, RGB], PROMPT)
    assert review["violations"] == []  # not_met ohne Begründung zählt nicht
    assert [m["text"] for m in review["missing"]] == ["LEDs für Zahlen"]
    assert review["met"] == ["R1"]


def test_routing_of_the_requirement_failures():
    assert route_repair("requirement_gap") == RepairTarget.VERIFICATION
    assert route_repair("requirement_violation") == RepairTarget.HDL
    assert route_repair("requirement_missing") == RepairTarget.ARCHITECTURE


# --- Supervisor ---------------------------------------------------------------------

class _Reviewer:
    def __init__(self, review=None, fail=False, touch=None):
        self.review, self.fail, self.touch, self.calls = review, fail, touch, []

    async def execute(self, task):
        self.calls.append(task)
        if self.touch:
            self.touch.write_text("-- vom Prüfer verändert\n")
        if self.fail:
            return AgentResult(task_id=task.id, status=AgentStatus.FAILED, error_message="timeout")
        return AgentResult(task_id=task.id, status=AgentStatus.COMPLETED, outputs={"review": self.review})


def _supervisor(tmp_path, reviewer):
    supervisor, fs, events = make_supervisor(tmp_path, verification_agent=reviewer)
    set_architecture(supervisor, [{"name": "gray_countdown", "type": "sequential"}], "gray_countdown")
    supervisor._design_state.metadata["request_full"] = PROMPT
    assert supervisor._adopt_plan_requirements(_manifest([COUNT, RGB]))
    src = Path(fs.workspace_path("proj")) / "src"
    src.mkdir(exist_ok=True)
    (src / "gray_countdown.vhd").write_text("-- entwurf\n")
    return supervisor, fs, events, src


def test_plan_requirements_are_adopted_and_written_for_all_agents(tmp_path):
    supervisor, fs, _, _ = _supervisor(tmp_path, _Reviewer())
    text = (Path(fs.workspace_path("proj")) / reqs.REQUIREMENTS_FILE).read_text()
    assert "R2" in text and "RGB" in text
    assert [r.id for r in supervisor._design_state.requirements] == ["R1", "R2"]


def test_gate_reports_requirements_without_testbench_check(tmp_path):
    supervisor, fs, _, _ = _supervisor(tmp_path, _Reviewer())
    tests = Path(fs.workspace_path("proj")) / "tests"
    tests.mkdir()
    (tests / "gray_countdown_tb.vhd").write_text(
        'entity gray_countdown_tb is end;\narchitecture a of gray_countdown_tb is begin\n'
        'assert true report "REQ R1: zählt" severity error;\n-- REQ R2 fehlt noch\nend;\n')
    gap = supervisor._requirement_gaps()
    assert gap["failure_type"] == "requirement_gap" and gap["requirements"] == ["R2"]
    assert gap["modules"] == ["gray_countdown"]


def test_review_violation_and_missing_requirement_become_repairs(tmp_path):
    review = {"violations": [{**RGB, "evidence": "kein RGB-Ausgang in src/gray_countdown.vhd"}],
              "missing": [{"text": "Zahlen auf normalen LEDs", "quote": "für die zahlen nutze die normalen leds", "modules": []}],
              "unrated": [], "met": ["R1"]}
    supervisor, fs, events, _ = _supervisor(tmp_path, _Reviewer(review))
    problems = run(supervisor._requirements_review())
    kinds = {p["failure_type"] for p in problems}
    assert kinds == {"requirement_violation", "requirement_missing"}
    assert "kein RGB-Ausgang" in next(p for p in problems if p["failure_type"] == "requirement_violation")["message"]
    ids = [r.id for r in supervisor._design_state.requirements]
    assert ids == ["R1", "R2", "R3"] and supervisor._design_state.requirements[2].review == "added"
    assert "R3" in (Path(fs.workspace_path("proj")) / reqs.REQUIREMENTS_FILE).read_text()
    assert "REQUIREMENTS_REVIEW" in events.types()


def test_passed_review_is_not_repeated_for_unchanged_sources(tmp_path):
    reviewer = _Reviewer({"violations": [], "missing": [], "unrated": [], "met": ["R1", "R2"]})
    supervisor, _, _, _ = _supervisor(tmp_path, reviewer)
    assert run(supervisor._requirements_review()) == []
    assert run(supervisor._requirements_review()) == []
    assert len(reviewer.calls) == 1


def test_reviewer_changes_are_discarded_and_unavailable_review_only_warns(tmp_path):
    supervisor, fs, events, src = _supervisor(tmp_path, None)
    supervisor._verification_agent = _Reviewer(fail=True, touch=src / "gray_countdown.vhd")
    assert run(supervisor._requirements_review()) == []
    assert (src / "gray_countdown.vhd").read_text() == "-- entwurf\n"
    assert "REQUIREMENTS_WARNING" in events.types()
    assert supervisor._design_state.metadata["requirements_review"]["status"] == "unavailable"


# --- Prüfanleitung fürs Board wird mitgeprüft (#57) --------------------------------

SWAPPED = [
    {"setup": "Alle Schalter unten, BTN0", "expected": "0001, 0010, 0011, 0101, 1000, 1101", "requirements": ["R1"]},
    {"setup": "SW1 oben, SW0 unten (Anzeige ACC)", "expected": "nach Halt 0101", "requirements": []},
]
FIXED = [SWAPPED[0], {"setup": "SW1 unten, SW0 oben (Anzeige ACC)", "expected": "nach Halt 0101", "requirements": []}]


def test_review_returns_cleaned_board_checks_and_waits_for_them(tmp_path):
    requirements = [{**COUNT, "id": "R1"}]
    review = {"requirements": [{"id": "R1", "status": "met", "evidence": "tb"}], "missing": [],
              "board_checks": FIXED + [{"setup": "nur Aufbau"}]}
    assert reqs.parse_review(json.dumps(review), requirements, PROMPT)["board_checks"] == FIXED

    path = tmp_path / "review.json"
    path.write_text(json.dumps({"requirements": review["requirements"]}))
    assert reqs.review_complete(path, requirements)
    assert not reqs.review_complete(path, requirements, expect_board_checks=True)
    path.write_text(json.dumps(review))
    assert reqs.review_complete(path, requirements, expect_board_checks=True)


def test_review_corrects_the_board_checklist_in_the_completion_message(tmp_path):
    reviewer = _Reviewer({"violations": [], "missing": [], "unrated": [], "met": ["R1", "R2"], "board_checks": FIXED})
    supervisor, fs, events, _ = _supervisor(tmp_path, reviewer)
    supervisor._design_state.metadata["plan_manifest"] = {"board_checks": SWAPPED}

    assert run(supervisor._requirements_review()) == []
    handed = json.loads((Path(fs.workspace_path("proj")) / reqs.BOARD_CHECKS_FILE).read_text())
    assert handed == SWAPPED  # der Prüfer bekam die ungeprüfte Fassung
    assert supervisor._board_checks() == FIXED
    assert supervisor._design_state.metadata["requirements_review"]["board_checks_corrected"] == 1
    assert "2. SW1 unten, SW0 oben (Anzeige ACC)" in supervisor._completion_message()
    message = next(p for t, p in events.events if t == "REQUIREMENTS_REVIEW")["message"]
    assert "Prüfanleitung fürs Board: 1 Schritt(e) korrigiert" in message
