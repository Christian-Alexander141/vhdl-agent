vhdl-autogen



Prototypische Entwicklung eines CAD-Tools zur autonomen Erzeugung, Validierung und Implementierung von VHDL-Code



📌 Beschreibung

Agenten-Orchestrator für die autonome Erzeugung kleiner bis mittlerer Schaltungen in VHDL. Das System koordiniert LLM-basierte Agenten, um den vollständigen FPGA-Entwurfsprozess zu durchlaufen:





Planung



Codegenerierung



Testbench-Erstellung



Simulation



Synthese

Ziel: Fehlertolerante und reproduzierbare Automatisierung des Workflows durch Orchestrierung spezialisierter Agenten.



📚 Gliederung der Arbeit





Einleitung





1.1 Motivation und Problemstellung



1.2 Zielsetzung der Arbeit



1.3 Abgrenzung und Forschungslücke



1.4 Aufbau der Arbeit



Grundlagen





2.1 Digitale Systeme und FPGA-basierter Entwurf



2.2 Hardwarebeschreibungssprachen (Verilog/VHDL)



2.3 EDA-Toolchains und der FPGA-Synthese-Flow



2.4 Large Language Models und Codegenerierung



2.5 Multi-Agenten-Systeme und Agenten-Orchestrierung



2.6 Architekturmuster der Agentenkoordination



Stand der Forschung





3.1 LLM-basierte HDL-Codegenerierung



3.2 Multi-Agenten-Systeme für EDA und Hardware-Design



3.3 Agenten-Orchestrierungs-Frameworks



3.4 FPGA-spezifische Automatisierungsansätze



3.5 Zusammenfassung und Forschungslücke



Konzept und Architektur des Agenten-Orchestrators





4.1 Anforderungsanalyse



4.2 Architekturmuster-Auswahl und Begründung



4.3 Agentenrollen und Verantwortlichkeiten



4.4 Kommunikations- und Koordinationsdesign



4.5 Workflow-Definition



4.6 Fehlertoleranz und Recovery-Strategien



Implementierung





5.1 Technologie-Stack und Frameworks



5.2 Implementierung der Agenten



5.3 Integration von EDA-Tools (Vivado/Quartus)



5.4 State-Management und Blackboard-Architektur



5.5 Feedback-Schleifen und iterative Korrektur



Evaluierung





6.1 Test-Design und Benchmarks



6.2 Fallstudien



6.3 Ergebnisse



6.4 Limitationen und kritische Diskussion



Zusammenfassung und Ausblick





7.1 Zusammenfassung der Ergebnisse



7.2 Limitationen



7.3 Ausblick auf zukünftige Forschung



🎯 Forschungslücke

Bestehende Multi-Agenten-Systeme (z. B. ASIC-Agent, Spec2RTL-Agent, ARCADE) decken vor allem:





ASIC-Design-Flows (RTL-to-GDSII) oder



isolierte Phasen (nur RTL-Generierung oder Verifikation).

Fehlend: Systematische Orchestrierung des vollständigen FPGA-Workflows von der Spezifikation bis zur Bitstream-Generierung.

Lösungsansatz: Hybride Architektur aus hierarchischer Koordination und Blackboard-basiertem State-Management.



📖 Referenzen (Auszug)

LLM-basierte HDL-Codegenerierung





ChipNeMo – Domain-adaptierte LLMs für Chip-Design (NVIDIA, 2023)



VerilogEval – Benchmark für Verilog-Codegenerierung



AutoChip – Iterative Generierung mit Simulations-Feedback

Multi-Agenten-Systeme für EDA





ASIC-Agent – Autonomes System für ASIC-Design



Spec2RTL-Agent – Spezifikation → RTL-Code (NVIDIA)



ARCADE – Closed-Loop-Reparatur für Hardware-Design

Orchestrierungs-Frameworks





Nexus – Design-Blueprint für skalierbare EDA-Agenten (DATE 2026)



HALO – Hierarchische Multi-Agenten-Orchestrierung

FPGA-spezifische Ansätze





Autonomes FPGA-System – Vivado-Integration für Bitstream-Generierung



RTL Designer – End-to-End-Workflow für FPGAs



📜 Lizenz

MIT-Lizenz



Bachelorarbeit: Erzeugung digitaler Systeme durch autonome Agenten
