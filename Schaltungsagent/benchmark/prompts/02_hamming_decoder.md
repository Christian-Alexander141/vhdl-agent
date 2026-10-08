Entwirf einen kombinatorischen Hamming(7,4)-Decoder mit Einzelfehlerkorrektur in VHDL-2008.
- Eingang: codeword (std_logic_vector(6 downto 0)) in der Bitreihenfolge p1 p2 d1 p3 d2 d3 d4 (Bit 6 = p1, Bit 0 = d4), gerade Parität.
- Ausgänge: data (std_logic_vector(3 downto 0)) = d1 d2 d3 d4 (Bit 3 = d1) nach Korrektur, error (std_logic) = '1', wenn ein Einzelbitfehler erkannt und korrigiert wurde.
- Entity-Name: hamming_decoder. Datei: src/hamming_decoder.vhd. Testbench: tests/hamming_decoder_tb.vhd, die alle 16 Datenwörter fehlerfrei und mit jedem möglichen Einzelbitfehler prüft.
