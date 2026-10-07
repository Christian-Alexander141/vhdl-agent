"""Tests für _run_via_pty: PTY statt Pipes für den OpenCode-Subprozess.

Hintergrund: ``subprocess.run(capture_output=True)`` (Pipes, kein TTY) –
der Mechanismus, den jeder Aufruf vorher verwendet hat – konnte einen
echten OpenCode-Lauf auf unbestimmte Zeit ohne jede Ausgabe hängen lassen,
selbst bei einem Fehler, der an einem echten Terminal sofort sichtbar ist
(reproduziert mit einer Rate-Limit-Antwort des Providers: mit Pipes 240s
Stille, mit einem echten PTY erschien dieselbe Fehlermeldung in < 2s).
Diese Tests verwenden ein Fake-Programm statt des echten (aktuell
ratenbegrenzten) ``opencode``-Kommandos, um den Mechanismus unabhängig vom
Provider zu verifizieren.
"""
import subprocess
import sys
import time

import pytest

from src.services.opencode_service import _run_via_pty

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="pty ist POSIX-spezifisch")


def _write_fake(tmp_path, body: str):
    script = tmp_path / "fake_opencode.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def test_child_sees_a_real_tty_via_run_via_pty(tmp_path):
    cmd = _write_fake(tmp_path, "import sys; print(sys.stdout.isatty())")
    result = _run_via_pty(cmd, cwd=None, timeout=10)
    assert result.returncode == 0
    assert "True" in result.stdout


def test_plain_subprocess_run_shows_no_tty_for_the_same_script(tmp_path):
    """Dokumentiert den Unterschied: derselbe Fake-Prozess sieht über
    subprocess.run(capture_output=True) (Pipes) kein TTY – genau der
    Zustand, der den echten Bug ausgelöst hat."""
    cmd = _write_fake(tmp_path, "import sys; print(sys.stdout.isatty())")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert "False" in result.stdout


def test_stdout_and_stderr_are_merged_into_one_stream(tmp_path):
    cmd = _write_fake(tmp_path, "import sys; print('from-stdout'); print('from-stderr', file=sys.stderr)")
    result = _run_via_pty(cmd, cwd=None, timeout=10)
    assert "from-stdout" in result.stdout
    assert "from-stderr" in result.stdout  # zusammengeführt, nicht getrennt
    assert result.stderr == ""


def test_returncode_is_propagated(tmp_path):
    cmd = _write_fake(tmp_path, "import sys; sys.exit(7)")
    result = _run_via_pty(cmd, cwd=None, timeout=10)
    assert result.returncode == 7


def test_cwd_is_respected(tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir()
    (workdir / "marker.txt").write_text("hi")
    cmd = _write_fake(tmp_path, "import os; print(sorted(os.listdir('.')))")
    result = _run_via_pty(cmd, cwd=str(workdir), timeout=10)
    assert "marker.txt" in result.stdout


def test_timeout_raises_and_includes_output_so_far(tmp_path):
    cmd = _write_fake(tmp_path, """
import sys, time
print("working...")
sys.stdout.flush()
time.sleep(30)
""")
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as info:
        _run_via_pty(cmd, cwd=None, timeout=2)
    duration = time.monotonic() - start
    assert duration < 10  # kein Warten auf das volle 30s-Sleep
    assert "working..." in info.value.stdout


def test_timeout_kills_child_processes_too(tmp_path):
    """Ein haengender Node-Prozess kann eigene Kindprozesse gestartet haben
    (z. B. npm install beim ersten Start) - die Prozessgruppe muss
    vollstaendig beendet werden, sonst laufen sie verwaist weiter."""
    marker = tmp_path / "child_still_running.marker"
    cmd = _write_fake(tmp_path, f"""
import subprocess, time
p = subprocess.Popen(["sh", "-c", "sleep 20; touch {marker}"])
time.sleep(30)
""")
    with pytest.raises(subprocess.TimeoutExpired):
        _run_via_pty(cmd, cwd=None, timeout=2)
    # Waere die Prozessgruppe NICHT beendet worden, liefe "sleep 20" weiter
    # und wuerde die Marker-Datei nach 20s doch noch anlegen.
    time.sleep(3)
    assert not marker.exists()


def test_no_output_hang_is_fixed_end_to_end(tmp_path):
    """Reproduktion des konkreten Fehlerbilds: ohne TTY druckt das Fake-
    Programm aus Designgruenden (isatty-Check) absichtlich NICHTS und haengt;
    mit echtem PTY (_run_via_pty) gibt es die Meldung sofort aus und beendet
    sich - exakt das beobachtete Verhalten von OpenCode ohne vs. mit TTY."""
    cmd = _write_fake(tmp_path, """
import sys, time
if sys.stdout.isatty():
    print("Error from provider: Rate limit exceeded. Please try again later.")
    sys.exit(1)
else:
    time.sleep(60)  # haengt: druckt bewusst nichts ohne TTY
""")
    start = time.monotonic()
    result = _run_via_pty(cmd, cwd=None, timeout=10)
    duration = time.monotonic() - start
    assert duration < 5
    assert result.returncode == 1
    assert "Rate limit exceeded" in result.stdout
