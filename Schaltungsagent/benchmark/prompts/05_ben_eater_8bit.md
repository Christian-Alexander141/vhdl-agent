Erstelle in VHDL-2008 einen originalgetreuen Nachbau des 8-Bit-Breadboard-Computers von Ben Eater (SAP-1-Architektur, Endversion mit Flags-Register und bedingten Sprüngen) für das Arty S7-50. Architektur, Register und Mikroprogramm folgen dem Original (Video-Reihe „Build an 8-bit computer“, Mikrocode aus `microcode-eeprom-with-flags`); angepasst sind nur Takterzeugung, Programmierung und Anzeige. Programme lassen sich zusätzlich über die USB-UART laden; die Ausgaben gehen dann über die UART zurück.

Ports der Top-Level-Entity ben_eater_cpu:
- clk (in std_logic): 100-MHz-Takt des Boards.
- rst (in std_logic): Taster BTN0, synchroner Reset, active high.
- btn_step (in std_logic): Taster BTN1, Einzeltakt (ein Mikroschritt je Druck).
- sw (in std_logic_vector(3 downto 0)): Schalter SW0–SW3.
  - sw(0) wählt die LED-Anzeige: '0' unteres Halbbyte von OUT, '1' oberes Halbbyte.
  - sw(1) wählt den Takt: '0' automatisch (ein Mikroschritt je Tick), '1' Einzeltakt über btn_step.
  - sw(3 downto 2) wählt das feste Programm, das beim Reset in den Speicher geladen wird.
- led (out std_logic_vector(3 downto 0)): led(0) = LD2 … led(3) = LD5.
- uart_rx (in std_logic): Empfangsleitung der USB-UART (Daten vom PC, Pin V12).
- uart_tx (out std_logic): Sendeleitung der USB-UART (Daten zum PC, Pin R12).
- Generic TICK_CYCLES (positive, Standard 4_000_000, also 25 Mikroschritte pro Sekunde bei 100 MHz; mindestens 2).
- Generic DEBOUNCE_CYCLES (positive, Standard 1_000_000, also 10 ms).
- Generic CLKS_PER_BIT (positive, Standard 868, also 115 200 Baud bei 100 MHz; mindestens 4).

Architektur wie im Original:
- Ein 8 Bit breiter Bus verbindet alle Baugruppen. Er wird als Multiplexer umgesetzt (keine Tri-State-Treiber): Den Bus treibt genau die Quelle, deren Ausgangssignal im Steuerwort aktiv ist: CO (Befehlszähler, oben mit 0 aufgefüllt), RO (RAM[MAR]), IO (unteres Halbbyte des Befehlsregisters, oben 0), AO (Register A) oder EO (ALU-Ergebnis). Ist keine Quelle aktiv, ist der Bus 0.
- Register A, Register B und Ausgaberegister OUT (je 8 Bit), Befehlsregister IR (8 Bit; oberes Halbbyte Opcode, unteres Operand), Befehlszähler PC (4 Bit), Speicheradressregister MAR (4 Bit), RAM 16 × 8 Bit.
- ALU: Addierer/Subtrahierer aus A und B. Ohne SU: Ergebnis = (A + B) mod 256, Carry = Übertrag aus Bit 7. Mit SU: Ergebnis = (A + (not B) + 1) mod 256, Carry = Übertrag aus Bit 7 dieser Summe (Carry = '1' genau dann, wenn A ≥ B, also kein Borgen). Zero = '1', wenn das Ergebnis 0 ist.
- Flags-Register mit C und Z: übernimmt bei FI Carry und Zero der ALU.
- Steuerwerk: Mikroschrittzähler T0 … T4; nach T4 folgt wieder T0. Das Steuerwort ergibt sich aus Opcode (IR(7 downto 4)), Mikroschritt und den Flags.

Steuersignale (16, Bedeutung wie im Original):
HLT Takt anhalten; MI MAR := Bus(3..0); RI RAM[MAR] := Bus; RO RAM[MAR] auf den Bus; IO IR(3..0) auf den Bus; II IR := Bus; AI A := Bus; AO A auf den Bus; EO ALU-Ergebnis auf den Bus; SU ALU subtrahiert; BI B := Bus; OI OUT := Bus; CE PC := PC + 1 (mod 16); CO PC auf den Bus; J PC := Bus(3..0); FI Flags := Carry, Zero der ALU.

Mikroprogramm (Befehl, Opcode: Steuerwort in T0, T1, T2, T3, T4; nicht genannte Schritte haben kein aktives Signal):
- Alle Befehle holen in T0: MI CO und in T1: RO II CE.
- NOP 0000: –
- LDA a 0001: T2 IO MI; T3 RO AI
- ADD a 0010: T2 IO MI; T3 RO BI; T4 EO AI FI
- SUB a 0011: T2 IO MI; T3 RO BI; T4 EO AI SU FI
- STA a 0100: T2 IO MI; T3 AO RI
- LDI n 0101: T2 IO AI
- JMP t 0110: T2 IO J
- JC t 0111: T2 IO J, wenn C = '1', sonst nichts
- JZ t 1000: T2 IO J, wenn Z = '1', sonst nichts
- Opcodes 1001 bis 1101: wie NOP
- OUT 1110: T2 AO OI
- HLT 1111: T2 HLT

Ausführung eines Mikroschritts:
- Ein Mikroschritt wird mit der steigenden Taktflanke ausgeführt, an der die Schrittfreigabe (siehe unten) '1' ist. Alle Register übernehmen gleichzeitig; Bus, ALU und Flags-Eingänge verwenden die Werte vor der Flanke. RI schreibt an die Adresse im MAR vor der Flanke.
- Danach geht der Mikroschrittzähler einen Schritt weiter (T4 → T0).
- Enthält das Steuerwort HLT, ändert sich kein Register, auch nicht der Mikroschrittzähler, und es folgen keine weiteren Mikroschritte, bis zum Reset oder bis ein Programm über die UART geladen wird.

Takt und Eingänge:
- sw, btn_step und uart_rx werden mit je zwei Flipflops einsynchronisiert. Diese Synchronisierer werden nicht zurückgesetzt und laufen immer; Startwert '0', bei uart_rx '1'. Alle Regeln verwenden die einsynchronisierten Werte.
- Entpreller für btn_step: Register dout und Zähler. Ist der Eingang gleich dout, wird der Zähler 0. Sonst zählt er um eins hoch; steht er dabei schon auf DEBOUNCE_CYCLES−1, übernimmt dout stattdessen den Eingang und der Zähler wird 0. Der Impuls rise ist ein Register: Er wird mit derselben Flanke '1', mit der dout von '0' auf '1' wechselt, und ist genau einen Takt lang '1'.
- Tick-Generator: zählt von 0 bis TICK_CYCLES−1 und liefert beim Zählerstand TICK_CYCLES−1 einen Tick von genau einem Takt; er läuft immer.
- Schrittfreigabe im Board-Modus: Tick, wenn sw(1) = '0'; rise, wenn sw(1) = '1'. Im UART-Modus: jeder Takt. In beiden Modi keine Freigabe, solange die CPU angehalten ist (HLT), und im UART-Modus keine Freigabe, solange der Lader einen Rahmen empfängt oder solange das aktuelle Steuerwort OI enthält und der UART-Sender noch ein Zeichen sendet.
- led ist ein Register und übernimmt mit jeder steigenden Taktflanke das mit sw(0) gewählte Halbbyte von OUT.

Reset und feste Programme:
- Solange rst = '1': PC, MAR, IR, A, B, OUT, C, Z, Mikroschrittzähler, Haltezustand, Tick-Zähler, Entpreller, Lader, UART-Empfänger und -Sender (uart_tx = '1') und led werden 0 bzw. Ruhezustand, die CPU ist im Board-Modus, und das RAM übernimmt in jedem Takt das mit sw(3 downto 2) gewählte feste Programm.
- Nach dem Laden des Bitstreams entspricht der Zustand dem Reset mit Programm 0.
- Feste Programme (RAM-Inhalt Adresse 0 bis 15, hexadezimal):
  - "00" Fibonacci (Original-Programm): 51 4E 50 E0 2E 4F 1E 4D 1F 4E 1D 70 63 00 00 00. OUT zeigt 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144 und beginnt nach dem Überlauf von vorn.
  - "01" Zählen: E0 2F 74 60 3F E0 80 64 00 00 00 00 00 00 00 01. OUT zählt von 0 bis 255, dann zurück bis 0, und wieder hinauf.
  - "10" Multiplikation 3 × 5: 1E 3C 76 1D E0 F0 4E 1D 2F 4D 60 00 01 00 03 05. OUT zeigt 15, dann hält die CPU an.
  - "11" Countdown: 5A E0 00 3F 86 61 E0 F0 00 00 00 00 00 00 00 01. OUT zeigt 10, 9, …, 1, 0, dann hält die CPU an.

UART und Lader:
- UART 8N1, niederwertigstes Bit zuerst, jedes Bit CLKS_PER_BIT Takte; Ruhepegel '1'. Der Empfänger erkennt den Beginn eines Startbits an der fallenden Flanke des einsynchronisierten uart_rx, tastet jedes Bit in der Bitmitte ab und verwirft ein Zeichen, dessen Startbit in der Mitte nicht '0' oder dessen Stoppbit nicht '1' ist.
- Ladeprotokoll (wie der Hardwaretest des Systems sendet): 4 Bytes Länge n (little endian), n Programmbytes, dann die 6 Zeichen "START" und Zeilenvorschub (53 54 41 52 54 0A). n muss 1 bis 16 sein. Weicht ein Byte ab (Länge außerhalb 1..16, falsches Zeichen in START), wird der Rahmen verworfen und das nächste Byte wieder als erstes Längenbyte gelesen.
- Ist der Rahmen vollständig, gilt: RAM[0..n−1] := Programmbytes, RAM[n..15] := 0; PC, MAR, IR, A, B, OUT, C, Z, Mikroschrittzähler und Haltezustand werden 0; die CPU wechselt in den UART-Modus und läuft ab dem nächsten Takt mit einem Mikroschritt je Takt.
- Im UART-Modus sendet jeder ausgeführte Mikroschritt mit OI den neuen OUT-Wert als ein Zeichen über uart_tx. Im Board-Modus sendet die CPU nichts (uart_tx bleibt '1').
- Empfängt der Lader im UART-Modus das erste Byte eines neuen Rahmens, hält die CPU an, bis dieser Rahmen vollständig ist oder verworfen wurde. Der UART-Modus endet nur mit dem Reset.
- Die genaue Taktzahl von Empfang, Laden und Senden ist nicht vorgegeben; vorgegeben sind Reihenfolge und Inhalt der Zeichen.

Hardwaretests über die UART (Typ cpu_program, Programm und erwartete Antwort hexadezimal):
- fibonacci_halt: Programm E02E7B4F1E4D1F4E1D6000F000000100, Antwort 000101020305080d1522375990
- multiply_7x9: Programm 1E3C761DE0F04E1D2F4D600001000709, Antwort 3f
- countdown_5: Programm 55E03F8561E0F0000000000000000001, Antwort 050403020100
- borrow_3_minus_5: Programm 533F75E0F051E0F00000000000000005, Antwort fe

Module, je Entity eine Datei src/<entity>.vhd:
- input_sync: zweistufiger Synchronisierer mit Generics WIDTH und INIT (Startwert).
- debouncer: Entpreller mit Generic DEBOUNCE_CYCLES und den Ausgängen dout und rise.
- clock_ctrl: Tick-Generator (Generic TICK_CYCLES) und Schrittfreigabe aus Modus, Tick, rise, Haltezustand, Lader und Sender.
- program_counter: PC mit CE, J und Reset.
- register8: 8-Bit-Register mit Ladeeingang (für A, B, OUT und IR).
- alu: Addierer/Subtrahierer mit Carry und Zero sowie Flags-Register (FI).
- memory: MAR, RAM 16 × 8 und die vier festen Programme; Laden beim Reset und Übernahme eines geladenen Programms.
- control_unit: Mikroschrittzähler, Mikroprogramm und Haltezustand; liefert die 16 Steuersignale.
- uart_rx: UART-Empfänger mit Generic CLKS_PER_BIT.
- uart_tx: UART-Sender mit Generic CLKS_PER_BIT und Ausgang busy.
- loader: Ladeprotokoll, Programmpuffer und UART-Modus.
- ben_eater_cpu: Top-Level; Bus-Multiplexer, Verdrahtung aller Module und LED-Register.

Testbench tests/ben_eater_cpu_tb.vhd mit TICK_CYCLES = 2, DEBOUNCE_CYCLES = 2 und CLKS_PER_BIT = 8. Sie prüft:
- die Programme "10" (OUT = 15, danach Halt) und "11" (Folge 10 … 0) im automatischen Takt über beide LED-Halbbytes;
- im Einzeltakt, dass ohne Tastendruck nichts passiert und dass jeder Druck genau einen Mikroschritt ausführt (bei Programm "11" steht 10 nach genau 8 Drücken in OUT);
- das Laden über die UART mit den vier Hardwaretests oben (Antwortbytes über uart_tx);
- dass ein Rahmen mit Länge 17 verworfen wird und ein danach gesendeter gültiger Rahmen trotzdem läuft;
- dass im Board-Modus nichts gesendet wird und der Reset in den Board-Modus zurückführt.

Am Board (alle Schalter unten, BTN0 drücken) läuft Ben Eaters Fibonacci-Programm; die LEDs zeigen das untere Halbbyte von OUT, mit SW0 oben das obere. Mit SW1 oben führt jeder Druck auf BTN1 genau einen Mikroschritt aus. SW3/SW2 wählen beim Reset die anderen Programme. Über die USB-UART (115 200 Baud) lassen sich eigene Programme laden; die Ausgaben kommen als Bytes zurück.
