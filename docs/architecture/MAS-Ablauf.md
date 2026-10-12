# Ablauf des VHDL-Multiagentensystems

Stand: 2026-10-12 (Branch `mas-verbesserungen-2026-10-11`, Commit `63a4752`). Klassen und
Zuständigkeiten: [MAS-UML.md](MAS-UML.md). Beschrieben ist der Modus
`opencode.repair_policy: persistent` (echte Läufe); Unterschiede zu `standard` (Benchmark) sind
markiert.

## 1. Gesamtablauf eines Laufs

```mermaid
flowchart TD
    U(["Anforderung im Dashboard"]) --> R{"ChatRouter:<br/>neues Projekt?"}
    R -- "Frage zum Projekt" --> Q["OpenCodeProjectChat<br/>beantwortet im Workspace"]
    R -- "Änderungswunsch" --> C["_continue_project:<br/>Plan mit change_request"]
    R -- "neu" --> B["Bootstrap: PlanService.plan()<br/>Manifest, Namen, Einzelanforderungen,<br/>reset_concept"]
    B --> PV{"Plan gültig?"}
    PV -- "nein, Versuch < 3<br/>(standard: 1)" --> PK["Korrekturauftrag mit<br/>konkreten Verstößen"] --> B
    PV -- "nein, nur Anforderungen" --> PR["Sammelanforderung R0 ergänzen"] --> W
    PV -- "ja" --> W["Workspace anlegen:<br/>PROMPT.md, Skills, Board-Daten,<br/>eigenes Git-Repo, OpenCode-Sperre"]
    C --> W
    W --> A1["ANALYZING:<br/>Ziel-FPGA, Toolchain-Prüfung"]
    A1 --> A2["ARCHITECTING:<br/>Architektur aus Manifest,<br/>plan/requirements.md"]
    A2 --> A3["UART_INTEGRATION:<br/>UART-Brücke nur bei Bedarf"]
    A3 --> RM["Referenzmodell (VerificationAgent):<br/>Python-Modell aus PROMPT.md + GENERICS"]
    RM --> IM["IMPLEMENTING: TaskGraph,<br/>Module + Testbenches parallel (HDLAgent)"]
    IM --> SC["STATIC_CHECK: Port-Contracts,<br/>Vergleichs-Testbench mit generic map,<br/>GHDL-Analyse und -Simulation"]
    SC --> SI["SIMULATING: alle Testbenches"]
    SI --> VA["VALIDATING: Abdeckung, REQ-Gate,<br/>Mutationsanalyse,<br/>Abschlussprüfung der Anforderungen"]
    VA --> SY["SYNTHESIZING (FPGAAgent):<br/>Cache-Prüfung, GHDL-Synthese des Top-Levels,<br/>Vivado mit -vhdl2008, XDC aus Top-Level-Ports,<br/>Board-Konfiguration, Timing-/Ressourcen-Gate"]
    SY --> FL["FPGA_PROGRAMMING:<br/>JTAG/SRAM + QSPI-Flash,<br/>ohne Benutzerfreigabe"]
    FL --> HW{"echte UART-<br/>Schnittstelle?"}
    HW -- "ja" --> HT["HARDWARE_TESTING"] --> OK(["COMPLETED"])
    HW -- "nein" --> OK

    IM -. Fehler .-> F
    SC -. Fehler .-> F
    SI -. Fehler .-> F
    VA -. Fehler .-> F
    SY -. Fehler .-> F
    FL -. Fehler .-> F
    HT -. Fehler .-> F
    F[["Fehlerbehandlung<br/>(Abschnitt 2)"]] -. "Reparatur erfolgreich:<br/>zurück zur passenden Phase" .-> SC
    F -. "Leiter erschöpft oder<br/>Werkzeug/Board fehlt" .-> H(["BLOCKED: Eingriff erforderlich,<br/>mit letztem Befund"])
```

## 2. Fehlerbehandlung: Vorfilter, Weitergabe, Eskalation

```mermaid
flowchart TD
    E(["Phase meldet FAILED"]) --> RB{"Frühere Phase gescheitert<br/>als vor der letzten Reparatur?"}
    RB -- "ja" --> RBX["Reparatur zurücknehmen<br/>(src/, tests/ wiederherstellen)"] --> SCX(["weiter bei STATIC_CHECK"])
    RB -- "nein" --> CM["Diagnosen kompakt speichern<br/>(Kernzeilen statt Quelltext)"]
    CM --> ID{"standard: gleicher Fehler<br/>schon einmal?"}
    ID -- "ja (nur standard)" --> FA(["FAILED"])
    ID -- "nein / persistent" --> DG["DebugAgent = Vorfilter (triage):<br/>Kernzeilen aus Details,<br/>Fehlerklasse, Herkunft,<br/>Module nur über Dateiverweise"]
    DG --> RT["route_repair:<br/>Fehlerklasse → zuständige Rolle"]
    RT --> MM{"model_mismatch nach<br/>2 HDL-Reparaturen?"}
    MM -- "ja" --> RMOD["Referenzmodell neu erzeugen"]
    MM -- "nein" --> ES["_escalate: Leiter je Herkunft<br/>+ bisherige Versuche mit Ergebnis"]
    ES --> HUM{"Ziel Mensch?"}
    HUM -- "ja" --> BL(["BLOCKED mit Zusammenfassung<br/>und letztem Befund"])
    HUM -- "nein" --> DP["_dispatch_repair"]
    DP --> D1["bitstream_config_error, Versuch 1:<br/>Bitstream ohne Sprachmodell neu bauen"]
    DP --> D2["regenerate: Modul neu schreiben<br/>(nur Herkunft Entwurf)"]
    DP --> D3["ARCHITECTURE: Plan überarbeiten<br/>(Auftrag je Fehlerklasse)"]
    DP --> D4["VERIFICATION: Testbench überarbeiten<br/>(Datei, REQ-/Mutationshinweise)"]
    DP --> D5["HDL / FPGA: fix_hdl mit Kernzeilen,<br/>Versuchsverlauf, Vivado-Kontext,<br/>Anforderungen als Invariante"]
    D1 --> VR
    D2 --> VR
    D3 --> VR
    D4 --> VR
    D5 --> VR["Befund lesen:<br/>reports/repair_verdict.json"]
    VR --> DIS{"model_mismatch und Befund<br/>reference_model / generated_check /<br/>specification, src/ unverändert?"}
    DIS -- "ja, Modell noch nicht neu" --> RMOD
    DIS -- "ja, Modell schon neu" --> OFF["Vergleichstest für den Lauf<br/>abschalten (Warnung)"] --> SCX
    DIS -- "nein" --> TO{"OpenCode-Zeitlimit?"}
    TO -- "ja" --> RS["halbe Änderungen verwerfen"] --> NX
    TO -- "nein" --> CH{"Dateien geändert<br/>(ohne erzeugte Prüfdateien)?"}
    CH -- "ja / Reparatur erfolgreich" --> SCX
    CH -- "nein" --> NX["nächste Stufe sofort,<br/>keine erneute Pipeline/Synthese"] --> ES
    RMOD --> SCX
```

Eskalationsleitern (Versuch je Fehlerklasse und Modul → Maßnahme):

| Herkunft (Vorfilter) | Versuch 1–2 | 3–4 | 5 | 6–7 | danach |
|---|---|---|---|---|---|
| Entwurf (Syntax, Simulation, Modell, Synthese, Timing, Anforderung verletzt) | gezielte Reparatur | Modul neu schreiben | Architektur überarbeiten | Fallback-Modell, Reparatur | Mensch |
| Testbench / Abdeckung / REQ-Lücke | gezielte Reparatur | Fallback-Modell, Reparatur | – | – | Mensch |
| Anforderungen fehlen im Plan | Plan ergänzen | Fallback-Modell, Plan ergänzen | – | – | Mensch |
| Werkzeug / Konfiguration (Constraints, Bitstream-Konfiguration) | Neubau bzw. Reparatur mit Vivado-Kontext | Fallback-Modell | – | – | Mensch |
| Hardware / Infrastruktur (Board, Kabel, fehlendes Werkzeug, Anbieter) | sofort Mensch | | | | |

Im Modus `standard` gibt es keine Leiter: ein Reparaturversuch je Fehler, Abbruch bei
wiederholtem gleichem Fehler, ein Planungsversuch.

## 3. Zusammenspiel der Agenten (Sequenz eines erfolgreichen Laufs)

```mermaid
sequenceDiagram
    autonumber
    actor User as Benutzer
    participant API as Dashboard/API
    participant O as SupervisorOrchestrator
    participant P as PlanService
    participant S as SupervisorAgent
    participant AR as ArchitectureAgent
    participant V as VerificationAgent
    participant H as HDLAgent
    participant F as FPGAAgent
    participant OC as OpenCode (CLI)
    participant T as GHDL / Vivado / Board

    User->>API: Anforderung
    API->>O: handle_chat_async()
    O->>P: plan() (Bootstrap)
    P->>OC: Auftrag "plan" (PROMPT.md)
    OC-->>P: plan/manifest.json
    P-->>O: Manifest (geprüft, ggf. korrigiert)
    O->>S: execute(task) im Thread
    S->>AR: create_architecture (Manifest)
    AR-->>S: Architektur + Einzelanforderungen
    S->>V: reference_model
    V->>OC: Auftrag "reference_model" (mit Generics)
    OC-->>V: model/reference_model.py (+ GENERICS)
    loop TaskGraph-Batches (parallel)
        S->>H: implement_module / Testbench
        H->>OC: Auftrag mit Contract, Anforderungen, GHDL-Selbstprüfung
        OC-->>H: src/MODUL.vhd, tests/MODUL_tb.vhd
    end
    S->>T: Contracts + Vergleichs-Testbench + GHDL
    S->>V: verify (alle Testbenches)
    V->>T: GHDL-Simulation
    S->>T: Mutationsanalyse
    S->>V: review_requirements
    V->>OC: unabhängige Abschlussprüfung (endet bei vollständigem Urteil)
    OC-->>V: reports/requirements_review.json
    S->>F: synthesize (top_entity)
    F->>T: GHDL-Synthese, Vivado-Bitstream, Reports
    S->>F: flash
    F->>T: JTAG + QSPI-Flash
    S-->>O: COMPLETED
    O-->>API: Ergebnis + Ereignisse (WebSocket)
    API-->>User: Abschlussmeldung
```

Alle Agenten veröffentlichen Ereignisse über den `EventBus`; der API-Server leitet sie per
WebSocket an das Dashboard weiter (Phasen, OpenCode-Aufrufe, Eskalationen, Befunde der Agenten,
Warnungen).
