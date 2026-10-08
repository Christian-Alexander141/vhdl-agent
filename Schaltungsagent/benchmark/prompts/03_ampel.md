Erstelle eine hierarchische Ampelsteuerung in VHDL-2008.
- Hauptstraße und Nebenstraße: je Rot, Gelb, Grün; Grünphase GREEN_CYCLES Takte, Gelbphase YELLOW_CYCLES Takte (Generics, Standard 30 und 4); zwischen den Richtungen eine Allrot-Phase von 1 Takt.
- Synchroner Reset (rst, active high): beide Richtungen Rot, danach beginnt die Hauptstraße mit Grün.
- Module: timer (generischer Abwärtszähler mit load/enable und done-Ausgang), control (Moore-Automat), ampel (Top-Level, instanziiert timer und control).
- Ports von ampel: clk, rst (in std_logic); main_red, main_yellow, main_green, side_red, side_yellow, side_green (out std_logic).
- Dateien: src/timer.vhd, src/control.vhd, src/ampel.vhd; Testbench: tests/ampel_tb.vhd, die einen vollständigen Zyklus prüft und dass nie beide Richtungen gleichzeitig Grün oder Gelb haben.
