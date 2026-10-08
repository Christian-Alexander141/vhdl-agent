Entwirf einen synchronen 4-Bit-Aufwärtszähler in VHDL-2008.
- Ports: clk (in std_logic), rst (in std_logic, synchron, active high), en (in std_logic), count (out std_logic_vector(3 downto 0)).
- Bei rst = '1' wird der Zähler auf 0 gesetzt; bei en = '1' zählt er mit jeder steigenden Flanke um 1 weiter und läuft von 15 auf 0 über; bei en = '0' hält er den Wert.
- Entity-Name: counter4. Datei: src/counter4.vhd. Testbench: tests/counter4_tb.vhd.
