"""Gegenprobe der Referenz-Testbench von Aufgabe 05 mit absichtlich fehlerhaften Varianten der eigenen Umsetzung.

Aufruf aus einem leeren Arbeitsordner: python3 gegenprobe_varianten.py <pfad>/05_ben_eater_8bit_ref_tb.vhd
"""
import subprocess, sys, shutil
from pathlib import Path
ref = sys.argv[1]
src = Path(__file__).with_name("eigene_umsetzung_ben_eater_cpu.vhd").read_text()
STEP = "if step = 4 then step <= 0; else step <= step + 1; end if;"
mutants = {
    "Original (muss bestehen)": [],
    "JC prüft Z statt C": [('if step = 2 and c = \'1\' then return bit_of(C_IO) or bit_of(C_J); end if;',
                            'if step = 2 and z = \'1\' then return bit_of(C_IO) or bit_of(C_J); end if;')],
    "SUB-Carry invertiert": [("alu_c <= sum(8);", "alu_c <= sum(8) xor cw(C_SU);")],
    "6 statt 5 Mikroschritte": [(STEP, "if step = 5 then step <= 0; else step <= step + 1; end if;"),
                                ("signal step : natural range 0 to 4", "signal step : natural range 0 to 5")],
    "Lader löscht den RAM-Rest nicht": [("if i < ld_len then ram(i) <= ld_buf(i); else ram(i) <= (others => '0'); end if;",
                                         "if i < ld_len then ram(i) <= ld_buf(i); end if;")],
    "UART-Ausgabe auch im Board-Modus": [("if uart_mode = '1' then\n                tx_busy", "if true then\n                tx_busy")],
    "HLT wirkt wie NOP": [("            halted <= '1';\n          else", "            " + STEP + "\n          else")],
    "keine Entprellung": [("elsif db_cnt = DEBOUNCE_CYCLES - 1 then", "elsif true then")],
    "LED-Halbbytes vertauscht": [("if sw_s2(0) = '1' then led_r", "if sw_s2(0) = '0' then led_r")],
    "Länge 17 angenommen": [("unsigned(byte_in) <= 16", "unsigned(byte_in) <= 17"),
                            ("signal ld_len, ld_idx : natural range 0 to 16", "signal ld_len, ld_idx : natural range 0 to 17")],
    "RI schreibt an Busadresse": [("if cw(C_RI) = '1' then ram(to_integer(mar)) <= bus_v; end if;",
                                   "if cw(C_RI) = '1' then ram(to_integer(unsigned(bus_v(3 downto 0)))) <= bus_v; end if;")],
    "OUT-Stall fehlt (sendet über laufendes Zeichen)": [("(not receiving and not (cw(C_OI) and tx_busy))", "(not receiving)")],
}
for name, edits in mutants.items():
    text = src
    for old, new in edits:
        assert text.count(old) == 1, (name, old[:40])
        text = text.replace(old, new)
    d = Path("mut"); shutil.rmtree(d, ignore_errors=True); d.mkdir()
    (d / "m.vhd").write_text(text)
    out = ""
    for c in (["ghdl", "-a", "--std=08", "--workdir=mut", "mut/m.vhd", ref],
              ["ghdl", "-e", "--std=08", "--workdir=mut", "ref_ben_eater_cpu_tb"],
              ["ghdl", "-r", "--std=08", "--workdir=mut", "ref_ben_eater_cpu_tb", "--stop-time=10ms"]):
        p = subprocess.run(c, capture_output=True, text=True, timeout=600)
        out += p.stdout + p.stderr
        if p.returncode and c[1] != "-r":
            break
    fails = [l.split("REF_FAIL ", 1)[1] for l in out.splitlines() if "REF_FAIL" in l]
    complete = "TB_COMPLETE" in out
    caught = bool(fails) or not complete
    detail = fails[0][:85] if fails else ("Abbruch: " + next((l for l in out.splitlines() if "error" in l.lower()), "")[-80:] if not complete else "")
    print(f"{'ERKANNT' if caught else 'NICHT  '} | {name}: {detail}")
