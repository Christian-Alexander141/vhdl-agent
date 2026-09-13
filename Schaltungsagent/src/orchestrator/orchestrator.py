import os
import re
import json
import shutil
import zipfile
import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.domain.ports import (
    LLMService,
    RAGService,
    ArtifactGenerator,
    FileSystemService,
    OpenCodeService,
    EventPublisher,
    ValidationService,
    PlannerService,
    BitstreamService,
    FlashService,
)
from src.domain.models import (
    TaskState,
    EventType,
    Event,
    KnowledgeBundle,
    ArtifactBundle,
)
from src.domain.state_machine import StateMachine, WorkflowState
from src.domain.exceptions import (
    WorkflowError,
    RAGError,
    LLMError,
    ArtifactError,
    WorkspaceError,
    AgentExecutionError,
)
from src.domain.workflow.workflow import Workflow
from src.services.project_namer import make_unique
from src.services.project_memory import ProjectMemoryService
from src.config import load_fpga_registry

logger = logging.getLogger(__name__)


class AsyncAgentOrchestrator:
    def __init__(
        self,
        llm_service: LLMService,
        rag_service: RAGService,
        artifact_generator: ArtifactGenerator,
        filesystem_service: FileSystemService,
        opencode_service: OpenCodeService,
        event_publisher: EventPublisher,
        validation_service: ValidationService | None = None,
        planner_service: PlannerService | None = None,
        bitstream_service: BitstreamService | None = None,
        flash_service: FlashService | None = None,
        flash_services: dict[str, FlashService] | None = None,
        fpga_registry: dict | None = None,
        max_repair_iterations: int = 5,
    ):
        self._llm = llm_service
        self._rag = rag_service
        self._artifact_generator = artifact_generator
        self._fs = filesystem_service
        self._opencode = opencode_service
        self._events = event_publisher
        self._validation_service = validation_service
        self._planner_service = planner_service
        self._bitstream_service = bitstream_service
        self._flash_service = flash_service
        self._flash_services = flash_services or {}
        self._fpga_registry = fpga_registry or load_fpga_registry()
        self._max_repair_iterations = max_repair_iterations

        self._workflow = Workflow(
            llm_service=llm_service,
            rag_service=rag_service,
            artifact_generator=artifact_generator,
            filesystem_service=filesystem_service,
            opencode_service=opencode_service,
            validation_service=validation_service,
            planner_service=planner_service,
            max_repair_iterations=max_repair_iterations,
        )

        # Approval-Registry: task_id -> threading.Event
        self._approval_events: dict[str, threading.Event] = {}
        self._approval_results: dict[str, tuple[bool, str]] = {}
        self._approval_lock = threading.Lock()

        self._memory = ProjectMemoryService(filesystem_service)
        self._running_tasks: dict[str, dict] = {}

    # --- Approval Registry ---

    def _create_approval_event(self, task_id: str) -> threading.Event:
        """Erstellt ein Event für die User-Freigabe und registriert es."""
        event = threading.Event()
        with self._approval_lock:
            self._approval_events[task_id] = event
            self._approval_results[task_id] = (False, "")
        return event

    def _wait_for_approval(self, task_id: str) -> tuple[bool, str]:
        """Wartet blockierend auf die User-Entscheidung (approve/reject).
        
        Returns:
            Tuple (approved: bool, feedback: str)
        """
        event = self._approval_events.get(task_id)
        if not event:
            return False, "No approval event registered"
        
        # Die Freigabe bleibt offen, bis der Benutzer explizit entscheidet.
        event.wait()
        
        with self._approval_lock:
            result = self._approval_results.get(task_id)
            if result is None:
                result = (False, "No approval result")
            # Cleanup
            self._approval_events.pop(task_id, None)
            self._approval_results.pop(task_id, None)
        
        return result

    def approve_task(self, task_id: str, feedback: str = "") -> bool:
        """Wird vom API-Endpunkt aufgerufen, wenn der User genehmigt."""
        with self._approval_lock:
            event = self._approval_events.get(task_id)
            if not event:
                return False
            self._approval_results[task_id] = (True, feedback)
            event.set()
        return True

    def reject_task(self, task_id: str, feedback: str = "") -> bool:
        """Wird vom API-Endpunkt aufgerufen, wenn der User ablehnt."""
        with self._approval_lock:
            event = self._approval_events.get(task_id)
            if not event:
                return False
            self._approval_results[task_id] = (False, feedback)
            event.set()
        return True

    def execute(
        self,
        request: str,
        domain: str = "vhdl",
        task_id: str | None = None,
        upload_dir: str | None = None,
    ) -> dict:
        state = TaskState(request=request, domain=domain)
        if task_id:
            state.task_id = task_id
        else:
            state.task_id = make_unique(self._llm.generate_project_name(request))
        sm = StateMachine(WorkflowState.CREATED)

        self._emit(state, EventType.TASK_CREATED, {"request": request, "domain": domain})

        try:
            self._analyze(state, sm)
            knowledge = self._search_rag(state, sm)
            artifacts = self._generate_artifacts(state, sm, knowledge)
            workspace = self._prepare_workspace(state, sm, artifacts, upload_dir)
            self._run_agent(state, sm, workspace)
            self._test_and_repair(state, sm, workspace)
            
            if state.status != WorkflowState.FAILED:
                # Neuer Flow: Synthese -> Freigabe -> Flash
                self._synthesize_and_approve(state, sm, workspace)

        except WorkflowError as e:
            self._handle_failure(state, sm, str(e))
        except Exception as e:
            logger.exception("Unexpected error in workflow")
            self._handle_failure(state, sm, f"Unexpected error: {e}")
        finally:
            self._cleanup_uploads(upload_dir)

        self._emit(state, EventType.LOG_MESSAGE, {
            "message": f"Workflow finished with status {state.status}",
            "files": state.generated_files,
        })

        self._save_state(state)
        self._running_tasks.pop(state.task_id, None)

        self._append_memory(state, request, "new_project")

        return state.to_dict()

    def execute_async(
        self,
        request: str,
        domain: str = "vhdl",
        callback: Callable[[dict], None] | None = None,
    ) -> str:
        task_id = make_unique(self._llm.generate_project_name(request))
        result_holder: dict = {}

        def run():
            nonlocal task_id
            result = self.execute(request, domain, task_id=task_id)
            task_id = result.get("task_id", "")
            result_holder["result"] = result
            if callback:
                try:
                    callback(result)
                except Exception:
                    logger.exception("Async callback failed")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        self._running_tasks[task_id] = {
            "thread": thread,
            "status": "running",
            "request": request,
            "domain": domain,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return task_id

    def get_task_status(self, task_id: str) -> dict | None:
        return self._running_tasks.get(task_id)

    def handle_chat(
        self,
        request: str,
        domain: str = "vhdl",
        current_project: str | None = None,
        upload_dir: str | None = None,
    ) -> dict:
        """Eingangspunkt für Chat-Nachrichten.

        Unterscheidet anhand des LLM zwischen:
        - new_project: voller Workflow für ein neues Projekt
        - resume:      bestehendes Projekt erneut bauen/fortführen
        - question:    Rückfrage zum Projekt beantworten (ohne neuen Build)
        """
        projects = self._list_projects()
        decision = self._llm.classify_request(request, projects, domain, current_project)
        ctype = decision.get("type", "new_project")
        pid = decision.get("project_id")

        if ctype == "resume":
            if not pid:
                logger.warning("Resume requested but no project found; treating as new")
                result = self.execute(request, domain, upload_dir=upload_dir)
                result["type"] = "new_project"
            else:
                result = self.resume_project(request, pid, domain, upload_dir=upload_dir)
                result["type"] = "resume"
            result["project_id"] = pid
            result["reason"] = decision.get("reason", "")
            return result

        if ctype == "question":
            self._cleanup_uploads(upload_dir)
            result = self.answer_question(request, pid, domain)
            result["project_id"] = pid
            result["reason"] = decision.get("reason", "")
            return result

        result = self.execute(request, domain, upload_dir=upload_dir)
        result["type"] = "new_project"
        result["project_id"] = None
        result["reason"] = decision.get("reason", "")
        return result

    def handle_chat_async(
        self,
        request: str,
        domain: str = "vhdl",
        current_project: str | None = None,
        upload_dir: str | None = None,
        callback: Callable[[dict], None] | None = None,
    ) -> dict:
        """Asynchrone Variante für den Chat: neue Projekte und Fortsetzungen laufen
        im Hintergrund (WebSocket-Streaming), Rückfragen werden direkt beantwortet."""
        projects = self._list_projects()
        decision = self._llm.classify_request(request, projects, domain, current_project)
        ctype = decision.get("type", "new_project")
        pid = decision.get("project_id")

        if ctype == "question":
            self._cleanup_uploads(upload_dir)
            result = self.answer_question(request, pid, domain)
            result["type"] = "question"
            result["project_id"] = pid
            result["reason"] = decision.get("reason", "")
            if callback:
                try:
                    callback(result)
                except Exception:
                    logger.exception("Async chat callback failed")
            return result

        if ctype == "resume" and pid:
            task_id = pid

            def run():
                result = self.resume_project(request, pid, domain, upload_dir=upload_dir)
                result["type"] = "resume"
                result["project_id"] = pid
                result["reason"] = decision.get("reason", "")
                if callback:
                    try:
                        callback(result)
                    except Exception:
                        logger.exception("Async chat callback failed")
        else:
            ctype = "new_project"
            task_id = make_unique(self._llm.generate_project_name(request))

            def run():
                result = self.execute(request, domain, task_id=task_id, upload_dir=upload_dir)
                result["type"] = "new_project"
                result["project_id"] = None
                result["reason"] = decision.get("reason", "")
                if callback:
                    try:
                        callback(result)
                    except Exception:
                        logger.exception("Async chat callback failed")

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self._running_tasks[task_id] = {
            "thread": thread,
            "status": "running",
            "request": request,
            "domain": domain,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "task_id": task_id,
            "type": ctype,
            "project_id": pid if ctype == "resume" else None,
            "status": "QUEUED",
            "reason": decision.get("reason", ""),
        }

    def resume_project(
        self,
        request: str,
        project_id: str,
        domain: str = "vhdl",
        upload_dir: str | None = None,
    ) -> dict:
        """Führt ein bestehendes Projekt fort: baut/tests erneut im selben Workspace,
        ohne neue Artefakte zu generieren und ohne neues Projekt anzulegen."""
        workspace = self._fs.workspace_path(project_id)
        state_path = os.path.join(workspace, "state.json")
        prior: dict = {}

        if self._fs.file_exists(state_path):
            try:
                prior = json.loads(self._fs.read_file(state_path))
            except Exception as e:
                raise WorkspaceError(f"Projektzustand {project_id} unlesbar: {e}") from e
        elif not os.path.isdir(workspace):
            raise WorkspaceError(f"Projekt {project_id} nicht gefunden")
        else:
            # Workspace existiert ohne state.json (Legacy-Projekt).
            # Sammle vorhandene VHDL-Dateien aus src/ als generated_files.
            logger.info("No state.json for %s – reconstructing from workspace", project_id)
            src_dir = os.path.join(workspace, "src")
            if os.path.isdir(src_dir):
                prior["generated_files"] = [
                    os.path.join("src", f)
                    for f in os.listdir(src_dir)
                    if f.endswith((".vhd", ".vhdl"))
                ]
            prior["request"] = request

        state = TaskState(request=request, domain=domain)
        state.task_id = project_id
        state.workspace = workspace
        state.generated_files = prior.get("generated_files", [])
        state.metadata["original_request"] = prior.get("request", "")
        sm = StateMachine(WorkflowState.WORKSPACE_READY)

        self._emit(state, EventType.TASK_CREATED, {
            "request": request,
            "domain": domain,
            "resume": project_id,
        })

        try:
            if upload_dir:
                self._integrate_uploads(state, workspace, upload_dir)
            self._run_agent(state, sm, workspace, extra_instruction=self._resume_context(state))
            self._test_and_repair(state, sm, workspace)
            if state.status != WorkflowState.FAILED:
                self._synthesize_and_approve(state, sm, workspace)
        except WorkflowError as e:
            self._handle_failure(state, sm, str(e))
        except Exception as e:
            logger.exception("Unexpected error in resume workflow")
            self._handle_failure(state, sm, f"Unexpected error: {e}")
        finally:
            self._cleanup_uploads(upload_dir)

        self._emit(state, EventType.LOG_MESSAGE, {
            "message": f"Resume workflow finished with status {state.status}",
            "files": state.generated_files,
        })
        self._save_state(state)
        self._running_tasks.pop(state.task_id, None)

        self._append_memory(state, request, "resume")
        return state.to_dict()

    def answer_question(
        self,
        request: str,
        project_id: str | None = None,
        domain: str = "vhdl",
    ) -> dict:
        """Beantwortet eine Rückfrage zum Projekt unter Nutzung von Gedächtnis und
        Projektzustand. Erzeugt keinen neuen Build."""
        state_data: dict = {}
        memory = ""
        workspace = ""
        if project_id:
            workspace = self._fs.workspace_path(project_id)
            state_path = os.path.join(workspace, "state.json")
            if self._fs.file_exists(state_path):
                try:
                    state_data = json.loads(self._fs.read_file(state_path))
                except Exception:
                    state_data = {}
            memory = self._memory.load(workspace)

        answer = self._llm.answer_question(
            request,
            {"memory": memory, "state": state_data},
            domain,
        )

        if workspace:
            try:
                self._memory.append(workspace, "user", request)
                self._memory.append(workspace, "assistant", answer)
            except Exception as e:
                logger.warning("Failed to persist question memory: %s", e)

        return {
            "task_id": project_id or "",
            "type": "question",
            "project_id": project_id,
            "status": "ANSWERED",
            "workspace": workspace,
            "answer": answer,
        }

    def _wants_integration(self, request: str) -> bool:
        """Erkennt den expliziten Wunsch „ex" im Prompt: hochgeladene VHDL-Dateien
        sollen direkt in das Projekt integriert und bei Bedarf vervollständigt werden."""
        return bool(re.search(r"\bex\b", request.lower()))

    def _list_uploaded(self, upload_dir: str) -> list[str]:
        try:
            return [p.name for p in Path(upload_dir).iterdir() if p.is_file()]
        except OSError:
            return []

    def _integrate_uploads(self, state: TaskState, workspace: str, upload_dir: str) -> list[str]:
        """Kopiert hochgeladene Dateien in den Workspace.

        - .vhd-Dateien landen bei aktivem „ex"-Wunsch direkt in src/ (Integration),
          sonst im Referenzordner uploads/.
        - ZIP-Archive werden nach uploads/ entpackt; enthaltene .vhd-Dateien werden
          bei aktivem „ex"-Wunsch ebenfalls nach src/ übernommen.
        - Bilder, Markdown- und Textdateien liegen im Referenzordner uploads/.
        """
        source = Path(upload_dir)
        if not source.is_dir():
            return []
        uploads_root = Path(workspace) / "uploads"
        uploads_root.mkdir(parents=True, exist_ok=True)
        src_root = Path(workspace) / "src"
        src_root.mkdir(parents=True, exist_ok=True)
        integrate = bool(state.metadata.get("integrate_uploads"))
        integrated: list[str] = []
        added: list[str] = []

        for file in sorted(source.iterdir()):
            if not file.is_file():
                continue
            ext = file.suffix.lower()
            if ext == ".vhd":
                dest = (src_root if integrate else uploads_root) / file.name
                shutil.copy2(file, dest)
                integrated.append(str(dest))
                added.append(file.name)
            elif ext == ".zip":
                dest = uploads_root / file.name
                shutil.copy2(file, dest)
                integrated.append(str(dest))
                added.append(file.name)
                extract_dir = uploads_root / file.stem
                extract_dir.mkdir(parents=True, exist_ok=True)
                try:
                    with zipfile.ZipFile(file) as zf:
                        base = extract_dir.resolve()
                        for member in zf.namelist():
                            target = (extract_dir / member).resolve()
                            if not str(target).startswith(str(base) + os.sep):
                                logger.warning("ZIP-Slip-Versuch ignoriert: %s", member)
                                continue
                            zf.extract(member, extract_dir)
                            if integrate and member.lower().endswith(".vhd") and target.is_file():
                                shutil.copy2(target, src_root / target.name)
                                integrated.append(str(src_root / target.name))
                except (zipfile.BadZipFile, OSError) as e:
                    logger.warning("ZIP-Extraktion fehlgeschlagen für %s: %s", file.name, e)
            else:
                dest = uploads_root / file.name
                shutil.copy2(file, dest)
                integrated.append(str(dest))
                added.append(file.name)

        if integrated:
            state.add_log(f"Hochgeladene Dateien integriert ({len(integrated)} Datei(en))")
        return integrated

    def _upload_instruction(self, state: TaskState) -> str:
        uploaded = state.metadata.get("uploaded_files", [])
        if not uploaded:
            return ""
        if state.metadata.get("integrate_uploads"):
            return (
                "Der Nutzer hat mit dem Kürzel \"ex\" explizit gewünscht, dass die "
                "hochgeladenen VHDL-Dateien direkt in das Projekt integriert und bei "
                "Bedarf vervollständigt werden. Die Dateien liegen bereits in src/ des "
                "Projekts. Vervollständige fehlende Entities, Architekturen, Ports oder "
                "Testbenches, integriere sie vollständig in das Gesamtdesign und stelle "
                "sicher, dass das Projekt kompiliert und alle Tests bestehen."
            )
        return (
            "Hochgeladene Referenzdateien liegen im Ordner uploads/ des Projekts: "
            + ", ".join(uploaded)
            + ". Nutze sie bei Bedarf als Kontext."
        )

    def _cleanup_uploads(self, upload_dir: str | None) -> None:
        if not upload_dir:
            return
        try:
            shutil.rmtree(upload_dir, ignore_errors=True)
            logger.info("Upload-Staging bereinigt: %s", upload_dir)
        except Exception as e:
            logger.warning("Upload-Staging konnte nicht bereinigt werden: %s", e)

    def _resume_context(self, state: TaskState) -> str:
        original = state.metadata.get("original_request", "")
        memory = self._memory.load(state.workspace)
        parts = []
        if original:
            parts.append(f"Ursprüngliche Anforderung des Projekts: {original}")
        parts.append(f"Neue Anweisung: {state.request}")
        if memory:
            parts.append(f"Projekt-Gedächtnis (memory.md):\n{memory}")
        return "\n\n".join(parts)

    def _append_memory(self, state: TaskState, request: str, chat_type: str) -> None:
        if not state.workspace:
            return
        try:
            self._memory.append(state.workspace, "user", request)
            summary = state.metadata.get("summary", "")
            answer = (
                f"Status: {state.status}"
                + (f"\nZusammenfassung: {summary}" if summary else "")
                + (f"\nWorkspace: {state.workspace}" if state.workspace else "")
                + (f"\nFehler: {state.error_message}" if state.error_message else "")
            )
            self._memory.append(state.workspace, "assistant", answer)
            self._memory.update_header(
                state.workspace,
                Status=state.status,
                Anfrage=(request or "")[:200],
            )
        except Exception as e:
            logger.warning("Failed to update project memory for %s: %s", state.task_id, e)

    def _list_projects(self) -> list[dict]:
        projects = []
        for name in self._fs.list_workspaces():
            if name.startswith("_"):
                continue
            state_path = os.path.join(self._fs.workspace_path(name), "state.json")
            info = {"id": name, "request": "", "status": "UNKNOWN"}
            if self._fs.file_exists(state_path):
                try:
                    state = json.loads(self._fs.read_file(state_path))
                    info["request"] = state.get("request", "")
                    info["status"] = state.get("status", "UNKNOWN")
                except Exception:
                    pass
            projects.append(info)
        return projects

    def list_tasks(self) -> list[dict]:
        return [
            {"task_id": tid, **{k: v for k, v in info.items() if k != "thread"}}
            for tid, info in self._running_tasks.items()
        ]

    def _emit(
        self,
        state: TaskState,
        event_type: EventType,
        payload: dict | None = None,
    ) -> None:
        p = payload or {}
        p.setdefault("task_id", state.task_id)
        p.setdefault("status", state.status)
        self._events.publish_event(event_type, state.task_id, p)

    def _transition(
        self, state: TaskState, sm: StateMachine, new_state: str
    ) -> None:
        old_status = state.status
        sm.transition_to(new_state)
        state.set_status(new_state)
        self._emit(state, EventType.STATE_CHANGED, {
            "from": old_status,
            "to": new_state,
        })

    def _analyze(self, state: TaskState, sm: StateMachine) -> str:
        self._transition(state, sm, WorkflowState.ANALYZING)
        self._emit(state, EventType.ANALYSIS_STARTED)

        state.add_log("Analyzing request...")
        try:
            analysis = self._llm.analyze_request(state.request, state.domain)
        except Exception as e:
            raise LLMError(f"Analysis failed: {e}") from e

        state.metadata["analysis"] = analysis
        state.add_log(f"Analysis complete: {analysis}")
        self._emit(state, EventType.ANALYSIS_FINISHED, {"analysis": analysis})
        return analysis

    def _search_rag(self, state: TaskState, sm: StateMachine) -> KnowledgeBundle:
        self._transition(state, sm, WorkflowState.RAG_SEARCH)
        self._emit(state, EventType.RAG_STARTED)

        state.add_log("Searching RAG knowledge base...")
        try:
            knowledge = self._rag.retrieve_knowledge(state.request, state.domain)
        except Exception as e:
            raise RAGError(f"RAG search failed: {e}") from e

        state.metadata["knowledge"] = knowledge.to_dict()
        state.add_log(
            f"RAG found {len(knowledge.coding_rules)} rules, "
            f"{len(knowledge.reference_designs)} designs"
        )
        self._emit(state, EventType.RAG_FINISHED, {
            "rule_count": len(knowledge.coding_rules),
            "design_count": len(knowledge.reference_designs),
        })
        return knowledge

    def _generate_artifacts(
        self,
        state: TaskState,
        sm: StateMachine,
        knowledge: KnowledgeBundle,
    ) -> ArtifactBundle:
        self._transition(state, sm, WorkflowState.GENERATING_ARTIFACTS)
        self._emit(state, EventType.ARTIFACT_GENERATION_STARTED)

        state.add_log("Generating artifacts...")
        analysis = state.metadata.get("analysis", "")

        try:
            artifacts = self._artifact_generator.generate(
                state.request, analysis, knowledge, state.domain
            )
        except Exception as e:
            raise ArtifactError(f"Artifact generation failed: {e}") from e

        state.artifacts = [f.to_dict() for f in artifacts.files]
        state.add_log(f"Generated {len(artifacts.files)} file(s)")

        # Template-Informationen in state.metadata protokollieren
        template_used = artifacts.metadata.get("template_used", False)
        matched_template = artifacts.metadata.get("matched_template")
        template_score = artifacts.metadata.get("template_score", 0.0)
        template_status = artifacts.metadata.get("template_status", "none")

        state.metadata["template_used"] = template_used
        state.metadata["matched_template"] = matched_template
        state.metadata["template_score"] = template_score
        state.metadata["template_status"] = template_status

        if template_used and matched_template:
            state.add_log(
                f"Template '{matched_template}' used (score={template_score:.2f})"
            )
        else:
            state.add_log("No template used (fallback skeleton generated)")

        self._emit(state, EventType.ARTIFACT_GENERATION_FINISHED, {
            "file_count": len(artifacts.files),
            "template_used": template_used,
            "matched_template": matched_template,
            "template_score": template_score,
            "template_status": template_status,
        })
        return artifacts

    def _prepare_workspace(
        self,
        state: TaskState,
        sm: StateMachine,
        artifacts: ArtifactBundle,
        upload_dir: str | None = None,
    ) -> str:
        self._transition(state, sm, WorkflowState.WORKSPACE_READY)

        state.add_log("Preparing workspace...")
        try:
            workspace = self._fs.create_workspace(state.task_id, state.domain)
        except Exception as e:
            raise WorkspaceError(f"Workspace creation failed: {e}") from e

        state.workspace = workspace
        written_files = []

        for file_artifact in artifacts.files:
            file_path = f"{workspace}/{file_artifact.path}"
            try:
                actual_path = self._fs.write_file(file_path, file_artifact.content)
                written_files.append(actual_path)
            except Exception as e:
                raise WorkspaceError(
                    f"Failed to write {file_artifact.name}: {e}"
                ) from e

        if upload_dir:
            state.metadata["uploaded_files"] = self._list_uploaded(upload_dir)
            state.metadata["integrate_uploads"] = self._wants_integration(state.request)
            integrated = self._integrate_uploads(state, workspace, upload_dir)
            written_files.extend(integrated)

        state.generated_files = written_files
        state.add_log(f"Workspace ready at {workspace}")
        self._emit(state, EventType.FILES_CREATED, {
            "workspace": workspace,
            "files": written_files,
        })
        return workspace

    def _run_agent(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace: str,
        extra_instruction: str = "",
    ) -> None:
        self._transition(state, sm, WorkflowState.RUNNING_AGENT)
        self._emit(state, EventType.AGENT_STARTED)

        state.add_log("Running OpenCode agent...")
        instruction = (
            f"Implementiere die VHDL-Komponente im Projekt {workspace}. "
            f"Anforderung: {state.request}"
        )
        upload_hint = self._upload_instruction(state)
        if upload_hint:
            instruction += f"\n\n{upload_hint}"
        if extra_instruction:
            instruction += f"\n\n{extra_instruction}"

        try:
            result = self._opencode.execute(
                workspace, instruction
            )
        except AgentExecutionError:
            raise
        except Exception as e:
            raise AgentExecutionError(f"OpenCode execution failed: {e}") from e

        state.opencode_result = result.to_dict()
        state.add_log(
            f"OpenCode finished: returncode={result.returncode}"
        )
        self._emit(state, EventType.AGENT_FINISHED, {
            "agent": "OpenCode",
            "returncode": result.returncode,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
        })

    def _test_and_repair(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace: str,
    ) -> None:
        iteration = state.iterations
        while iteration < self._max_repair_iterations:
            self._transition(state, sm, WorkflowState.TESTING)
            self._emit(state, EventType.TEST_STARTED,
                       {"iteration": iteration + 1})

            state.add_log(f"Testing (iteration {iteration + 1})...")

            if self._validation_service:
                validation = self._validation_service.validate(workspace, state.domain)
                test_passed = validation.passed
                state.test_results = {
                    "passed": test_passed,
                    "message": validation.message,
                    "details": validation.details,
                    "iteration": iteration + 1,
                }
            else:
                result = self._opencode.execute(
                    workspace,
                    f"Teste und verifiziere die VHDL-Komponente. "
                    f"Anforderung: {state.request}",
                )
                test_passed = result.success
                state.test_results = {
                    "passed": test_passed,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "iteration": iteration + 1,
                }

            if test_passed:
                self._emit(state, EventType.TEST_PASSED,
                           {"iteration": iteration + 1})
                state.add_log("Tests passed!")
                state.iterations = iteration
                return

            self._emit(state, EventType.TEST_FAILED,
                       {"iteration": iteration + 1,
                        "error": state.test_results.get("stderr", "")[:500]})
            state.add_log(f"Tests failed: {state.test_results.get('stderr', '')[:200]}")

            iteration += 1
            if iteration >= self._max_repair_iterations:
                state.add_log("Max repair iterations reached")
                state.iterations = iteration
                self._transition(state, sm, WorkflowState.FAILED)
                return

            self._transition(state, sm, WorkflowState.REPAIRING)
            self._emit(state, EventType.REPAIR_STARTED,
                       {"iteration": iteration})

            state.add_log(f"Repairing (iteration {iteration})...")
            if self._validation_service:
                repair_instruction = validation.build_repair_instruction(
                    original_request=state.request,
                    iteration=iteration,
                )
            else:
                error_detail = state.test_results.get("stderr") or state.test_results.get("message", "")
                repair_instruction = (
                    f"Repariere die VHDL-Komponente. Fehler: {error_detail[:500]}"
                )
            repair_result = self._opencode.execute(
                workspace, repair_instruction,
            )

            state.iterations = iteration
            self._emit(state, EventType.REPAIR_FINISHED,
                       {"iteration": iteration,
                        "returncode": repair_result.returncode})

            # Nach der Reparatur direkt erneut testen. Ein erneutes Ausfuehren
            # des Implementierungs-Agenten wuerde die Reparatur ueberschreiben.
        state.iterations = iteration
        self._transition(state, sm, WorkflowState.FAILED)

    def _synthesize_and_approve(
        self,
        state: TaskState,
        sm: StateMachine,
        workspace: str,
    ) -> None:
        """Führt Synthese durch, wartet auf User-Freigabe, dann Flash.
        
        Verwendet einen flachen Loop statt Rekursion, um das
        max_repair_iterations-Limit korrekt zu respektieren.
        """
        if not self._bitstream_service:
            self._handle_failure(state, sm, "Bitstream service not configured")
            return

        if not self._bitstream_service.toolchain_available():
            self._handle_failure(state, sm, "Vivado toolchain not available (binary not found in PATH)")
            return

        # Flacher Loop: Test -> Synthese -> (Repair -> Test -> Synthese)* -> Approval -> Flash
        for syn_iter in range(self._max_repair_iterations):
            # Prüfen ob durch vorherigen _test_and_repair Aufruf bereits max erreicht
            if state.iterations >= self._max_repair_iterations:
                state.add_log("Max repair iterations reached")
                self._handle_failure(state, sm, "Max repair iterations reached during synthesis repair loop")
                return

            # TESTING → VALIDATING → SYNTHESIZING
            if sm.current in (WorkflowState.TESTING, WorkflowState.REPAIRING):
                self._transition(state, sm, WorkflowState.VALIDATING)
            self._transition(state, sm, WorkflowState.SYNTHESIZING)
            self._emit(state, EventType.SYNTHESIS_STARTED)

            state.add_log(f"Starting Vivado bitstream generation (attempt {syn_iter + 1})...")

            target_fpga = state.metadata.get("target_fpga", "arty_s7_50")
            bitstream_result = self._bitstream_service.build_bitstream(
                workspace, target=target_fpga, domain=state.domain
            )

            if bitstream_result.passed:
                # Synthese erfolgreich -> Approval + Flash
                break

            # Synthese fehlgeschlagen -> Repair
            self._emit(state, EventType.SYNTHESIS_FINISHED, {
                "passed": False,
                "message": bitstream_result.message,
            })
            state.add_log(f"Synthesis failed: {bitstream_result.message}")

            repair_instruction = bitstream_result.build_repair_instruction(
                original_request=state.request,
                iteration=state.iterations + 1,
            )

            self._transition(state, sm, WorkflowState.REPAIRING)
            self._emit(state, EventType.REPAIR_STARTED, {"iteration": state.iterations + 1})
            state.add_log("Repairing after synthesis failure...")

            repair_result = self._opencode.execute(workspace, repair_instruction)
            state.iterations += 1
            self._emit(state, EventType.REPAIR_FINISHED, {
                "iteration": state.iterations,
                "returncode": repair_result.returncode,
            })

            # Nach Reparatur: erneut testen
            self._test_and_repair(state, sm, workspace)
            if state.status == WorkflowState.FAILED:
                return
        else:
            # Loop durchlaufen ohne break -> alle Versuche aufgebraucht
            state.add_log("Max synthesis repair iterations reached")
            self._handle_failure(state, sm, "Max synthesis repair iterations reached")
            return

        # Synthese erfolgreich
        bitstream_path = bitstream_result.bitstream_path
        state.metadata["bitstream_path"] = bitstream_path
        state.metadata["bitstream_details"] = bitstream_result.details

        self._emit(state, EventType.SYNTHESIS_FINISHED, {
            "passed": True,
            "bitstream_path": bitstream_path,
            "message": bitstream_result.message,
        })
        state.add_log(f"Synthesis succeeded: {bitstream_path}")

        # Auf User-Freigabe warten (AWAITING_APPROVAL)
        self._transition(state, sm, WorkflowState.AWAITING_APPROVAL)
        self._emit(state, EventType.APPROVAL_REQUESTED, {
            "bitstream_path": bitstream_path,
            "bitstream_details": bitstream_result.details,
            "test_results": state.test_results,
            "generated_files": state.generated_files,
            "vhdl_code": self._collect_vhdl_code(workspace),
        })

        state.add_log("Awaiting user approval for flashing...")

        self._create_approval_event(state.task_id)
        approved, feedback = self._wait_for_approval(state.task_id)

        if not approved:
            self._emit(state, EventType.APPROVAL_REJECTED, {"feedback": feedback})
            state.add_log(f"User rejected: {feedback or 'No feedback provided'}")

            if feedback:
                if state.iterations >= self._max_repair_iterations:
                    state.add_log("Max repair iterations reached after rejection")
                    self._transition(state, sm, WorkflowState.FAILED)
                    return
                # User-Feedback als Repair-Instruktion, dann erneut testen+synthetisieren
                self._transition(state, sm, WorkflowState.REPAIRING)
                self._emit(state, EventType.REPAIR_STARTED, {"iteration": state.iterations + 1})
                state.add_log("Repairing based on user feedback...")
                repair_result = self._opencode.execute(workspace, feedback)
                state.iterations += 1
                self._emit(state, EventType.REPAIR_FINISHED, {
                    "iteration": state.iterations,
                    "returncode": repair_result.returncode,
                })
                # Erneut testen und synthetisieren (iterativer Aufruf, nicht rekursiv)
                self._test_and_repair(state, sm, workspace)
                if state.status != WorkflowState.FAILED:
                    self._synthesize_and_approve(state, sm, workspace)
            else:
                self._transition(state, sm, WorkflowState.FAILED)
            return

        # User hat genehmigt -> FLASHING
        self._emit(state, EventType.APPROVAL_GRANTED, {"feedback": feedback})
        state.add_log("User approved. Starting flash...")
        self._flash_bitstream(state, sm, bitstream_path)

    def _flash_bitstream(
        self,
        state: TaskState,
        sm: StateMachine,
        bitstream_path: str,
    ) -> None:
        """Flasht den Bitstream auf das FPGA-Board."""
        # Expected FPGA part aus Registry bestimmen
        target_fpga = state.metadata.get("target_fpga", "arty_s7_50")
        fpga_config = self._fpga_registry.get(target_fpga)
        expected_part = fpga_config.part if fpga_config else ""
        board_name = fpga_config.board_name if fpga_config else ""
        programmer = fpga_config.programmer if fpga_config else "vivado"
        
        # Richtigen Flash-Service basierend auf Board-Profil auswählen
        flash_service = self._flash_services.get(programmer, self._flash_service)
        
        if not flash_service:
            self._handle_failure(
                state, sm, f"Flash service not configured for programmer '{programmer}'"
            )
            return

        if not flash_service.toolchain_available():
            self._handle_failure(
                state, sm, f"Flash toolchain not available: {programmer} (binary not found in PATH)"
            )
            return

        self._transition(state, sm, WorkflowState.FLASHING)
        self._emit(state, EventType.FLASH_STARTED, {"bitstream_path": bitstream_path})

        state.add_log(f"Flashing bitstream to FPGA via {programmer}...")
        
        # Flash-Service aufrufen mit expected_part für Board-Matching
        # workspace übergeben damit Vivado-Logs sauber abgelegt werden
        flash_result = flash_service.flash(
            bitstream_path,
            board=board_name,
            expected_part=expected_part,
            workspace=state.workspace or "",
        )

        if not flash_result.passed:
            # Flash fehlgeschlagen -> zurück zu AWAITING_APPROVAL (erneuter Versuch möglich)
            self._emit(state, EventType.FLASH_FINISHED, {
                "passed": False,
                "message": flash_result.message,
                "board_detected": flash_result.board_detected,
                "board_count": flash_result.board_count,
            })
            state.add_log(f"Flash failed: {flash_result.message}")
            
            # Kein Code-Problem, sondern Hardware-Problem -> zurück zu AWAITING_APPROVAL
            # User kann Board anschließen und erneut versuchen
            self._transition(state, sm, WorkflowState.AWAITING_APPROVAL)
            self._emit(state, EventType.APPROVAL_REQUESTED, {
                "bitstream_path": bitstream_path,
                "bitstream_details": state.metadata.get("bitstream_details", {}),
                "test_results": state.test_results,
                "generated_files": state.generated_files,
                "vhdl_code": self._collect_vhdl_code(state.workspace),
                "flash_error": flash_result.message,
                "board_detected": flash_result.board_detected,
                "board_count": flash_result.board_count,
            })
            state.add_log("Awaiting user retry (fix hardware connection)...")
            
            # Erneut auf Freigabe warten
            self._create_approval_event(state.task_id)
            approved, feedback = self._wait_for_approval(state.task_id)
            if approved:
                self._flash_bitstream(state, sm, bitstream_path)
            else:
                self._transition(state, sm, WorkflowState.FAILED)
            return

        # Flash erfolgreich
        self._emit(state, EventType.FLASH_FINISHED, {
            "passed": True,
            "message": flash_result.message,
            "board_detected": flash_result.board_detected,
        })
        state.add_log("Flash successful!")
        
        # Finale Validierung und COMPLETED
        self._transition(state, sm, WorkflowState.FLASHED)
        self._complete_flashed(state, sm)

    def _collect_vhdl_code(self, workspace: str) -> str:
        """Sammelt alle VHDL-Dateien im Workspace für die Freigabe-Ansicht."""
        ws_path = Path(workspace)
        src_dir = ws_path / "src"
        blocks = []
        if src_dir.exists():
            for f in sorted(src_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in (".vhd", ".vhdl"):
                    try:
                        blocks.append(f"--- {f.name} ---\n{f.read_text(errors='replace')}")
                    except OSError:
                        continue
        return "\n".join(blocks)

    def _complete_flashed(self, state: TaskState, sm: StateMachine) -> None:
        """Finaler Abschluss nach erfolgreichem Flash. State bleibt FLASHED."""
        self._emit(state, EventType.VALIDATION_STARTED)

        state.add_log("Validating final result...")
        summary = self._llm.summarize_result(state.to_dict())
        state.metadata["summary"] = summary

        self._emit(state, EventType.VALIDATION_FINISHED, {"summary": summary})
        self._emit(state, EventType.TASK_COMPLETED, {
            "task_id": state.task_id,
            "summary": summary,
            "bitstream_path": state.metadata.get("bitstream_path", ""),
            "flashed": True,
        })
        state.add_log("Task completed successfully - bitstream flashed to FPGA")

    def _complete(self, state: TaskState, sm: StateMachine) -> None:
        """Legacy-Methode für Kompatibilität (Resume ohne Synthese/Flash)."""
        self._transition(state, sm, WorkflowState.VALIDATING)
        self._emit(state, EventType.VALIDATION_STARTED)

        state.add_log("Validating final result...")
        summary = self._llm.summarize_result(state.to_dict())
        state.metadata["summary"] = summary

        self._emit(state, EventType.VALIDATION_FINISHED, {"summary": summary})
        self._transition(state, sm, WorkflowState.COMPLETED)
        self._emit(state, EventType.TASK_COMPLETED, {
            "task_id": state.task_id,
            "summary": summary,
        })
        state.add_log("Task completed successfully")

    def _handle_failure(
        self, state: TaskState, sm: StateMachine, error_message: str
    ) -> None:
        state.error_message = error_message
        state.add_log(f"Workflow failed: {error_message}")
        sm.transition_to(WorkflowState.FAILED)
        state.set_status(WorkflowState.FAILED)
        self._emit(state, EventType.TASK_FAILED, {"error": error_message})

    def _save_state(self, state: TaskState) -> None:
        if not state.workspace:
            return
        try:
            state_path = os.path.join(state.workspace, "state.json")
            with open(state_path, "w") as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning("Failed to save state: %s", e)


AgentOrchestrator = AsyncAgentOrchestrator
