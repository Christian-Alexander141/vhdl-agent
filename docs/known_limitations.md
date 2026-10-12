# Bekannte Grenzen von Schaltungsagent

> Grundlage für die Diskussionskapitel der Abschlussarbeit.
> Stand 2026-10-12. Einzelbefunde mit Anlass und Maßnahme: `docs/doku.html`, Abschnitt 15 (#1–#47);
> Entwicklungsverlauf: `docs/architecture/AENDERUNGSPROTOKOLL.drawio`.

## Erreicht

Am 2026-10-11 lief eine Aufgabe mit sieben Modulen (`led-patterns-display-5816ba`,
muse-spark-1.3) ohne Reparatur von der Anforderung über Planung, Implementierung, alle
Prüfungen und Vivado bis zum Flashen auf das Arty S7-50 durch. Das Ergebnis ist durch die Gates
belegt: Referenzmodell, Mutationsquote 1,0, 39 von 39 Anforderungen, Timing erfüllt. Ob die LEDs
am Board richtig reagieren, prüft das System selbst nicht.

Am 2026-10-12 liefen zwei Läufe der Benchmark-Aufgabe 04 (4-Bit-Akkumulator-CPU mit Rechenwerk,
Steuerwerk und Speicher, 10 Module) ohne Reparatur bis zum Flashen durch; beide Entwürfe bestehen
die unabhängige Referenz-Testbench, die LED-Ausgabe am Board hat der Benutzer bestätigt.

## Weiterhin offene Grenzen

### 1. Kein automatischer Hardwaretest ohne UART
Ohne `hardware_test.uart_port` wird kein Hardwaretest ausgeführt; der Workflow endet dann mit
dem Hinweis, dass die Board-Funktion nicht validiert ist. Testvektoren müssen im Manifest
(`hardware_tests`) oder in `tests/hardware_tests.yaml` stehen. GPIO-Beobachtung (LEDs, Schalter)
gibt es nicht. Ein Lauf mit einer 8-Bit-CPU steht noch aus.

### 2. Prüfungen mit begrenzter Aussagekraft
- Die Abdeckung ist strukturell (jedes Modul von einer Testbench erreicht), keine Code- oder
  Funktionsabdeckung.
- Das Referenzmodell ist eine zweite Auslegung derselben Spezifikation durch ein Sprachmodell.
  Bei mehrdeutigen Prompts kann es abweichen. Widerspricht die Reparatur begründet, wird der
  Vergleich nach einer Neuerzeugung des Modells abgeschaltet (#40).
- Die Abschlussprüfung der Anforderungen und die Vollständigkeit der Anforderungsliste sind
  Urteile eines Sprachmodells (#29).

### 3. Contracts ohne Protokollsemantik
Der `ContractChecker` prüft Existenz, Richtung, Basistyp und Bitbreite der Ports (auch mit
Generics) sowie das Top-Level. Latenz, Handshake, Durchsatz und Clock-Domain-Übergänge sind
nicht maschinenprüfbar.

### 4. Ressourcen- und Board-Fehler brauchen den Benutzer
Constraint- und Bitstream-Konfigurationsfehler gehen an die FPGA-Reparatur. Ressourcen-
überschreitung, fehlendes Board oder Kabel, fehlende Werkzeuge und Anbieterausfälle gehen an den
Benutzer.

### 5. Kein automatisches Resume nach Neustart
`task_graph.json` und `design_state.yaml` erlauben eine Wiederaufnahme
(`SupervisorOrchestrator.resume_project`), sie wird aber nicht automatisch angestoßen. Ereignisse
werden nicht gespeichert.

### 6. Parallelität teilt einen Workspace
HDL-Worker laufen parallel (`limits.max_parallel_workers`, Standard 2). Dateien gehören je einem
Modul-Task, die OpenCode-Prozesse arbeiten aber im selben Workspace.

### 7. Isolation nur nativ
OpenCode läuft nativ mit Verzeichnissperre und eigenem Git-Repo je Workspace (#41). Die
Docker-Isolation ist zurückgestellt, bis das MAS einen einzelnen OpenCode-Lauf messbar schlägt (#15).

### 8. Freie Modelle
Alle Läufe nutzen freie OpenCode-Zen-Modelle mit Rate-Limits und gelegentlichen Hängern; das
Zeitlimit je Aufruf ist 900 s. Ergebnisse sind daher modellabhängig und schwanken zwischen Läufen.

### 9. Ungeprüftes Board-Wissen
UART- und Pmod-Pins im Board-Wissen sind nicht gegen die offizielle Master-XDC geprüft (#38).
