import re
import logging
from src.domain.ports import ArtifactGenerator
from src.domain.models import KnowledgeBundle, ArtifactBundle, FileArtifact
from src.domain_plugins.vhdl.templates import VHDLTemplates

logger = logging.getLogger(__name__)


class VHDLArtifactGenerator(ArtifactGenerator):
    def __init__(self):
        self._templates = VHDLTemplates()

    def generate(
        self,
        request: str,
        analysis: str,
        knowledge: KnowledgeBundle,
        domain: str = "vhdl",
    ) -> ArtifactBundle:
        logger.info("Generating artifacts for request (domain=%s)", domain)
        request_lower = request.lower()

        # 1. Bevorzugt die strukturierten Felder aus KnowledgeBundle
        matched_template = knowledge.matched_template
        template_status = knowledge.template_status
        template_score = knowledge.template_score

        # 2. Fallback: Alte raw_context-Suche (Kompatibilitaet)
        if not matched_template:
            for ctx in knowledge.raw_context:
                if ctx.startswith("matched_template:"):
                    matched_template = ctx.split(":", 1)[1].strip()
                    template_status = "matched"
                    break

        # 3. Template verwenden wenn:
        #    - matched_template gesetzt
        #    - Template existiert in TEMPLATES
        #    - status ist "matched" (nicht "rejected" oder "unsuitable")
        if (
            matched_template
            and matched_template in self._templates.TEMPLATES
            and template_status in ("matched", "injected")
        ):
            logger.info(
                "Using template '%s' (score=%.2f, status=%s)",
                matched_template, template_score, template_status,
            )
            result = self._generate_from_template(matched_template, request)
            # Template-Metadaten im ArtifactBundle protokollieren
            result.metadata["template_used"] = True
            result.metadata["matched_template"] = matched_template
            result.metadata["template_score"] = template_score
            result.metadata["template_status"] = "injected"
            return result

        # 4. Template gefunden aber nicht verwendbar
        if matched_template and template_status in ("rejected", "unsuitable"):
            logger.info(
                "Template '%s' found but not suitable (status=%s, score=%.2f)",
                matched_template, template_status, template_score,
            )
        elif matched_template:
            logger.warning(
                "Template '%s' matched but not in TEMPLATES dict", matched_template
            )

        # 5. Fallback: Minimaler VHDL-Skelett
        return self._generate_fallback(request, analysis)

    def _generate_from_template(
        self, template_name: str, request: str
    ) -> ArtifactBundle:
        files: list[FileArtifact] = []

        if template_name == "counter":
            name = self._extract_entity_name(request, "counter")
            width = self._extract_width(request, 8)

            files.append(FileArtifact(
                name=f"{name}.vhd",
                content=self._templates.render(
                    "counter", "entity", name=name, msb=width - 1, additional_ports=""
                )
                + "\n"
                + self._templates.render(
                    "counter", "architecture", name=name, msb=width - 1
                ),
                path=f"src/{name}.vhd",
                description=f"{name} entity and architecture",
            ))
            files.append(FileArtifact(
                name=f"{name}_tb.vhd",
                content=(
                    self._templates.render("counter", "tb_entity", name=name)
                    + "\n"
                    + self._templates.render(
                        "counter", "tb_architecture", name=name, msb=width - 1
                    )
                ),
                path=f"tests/{name}_tb.vhd",
                description=f"Testbench for {name}",
            ))

        elif template_name == "hamming":
            files.append(FileArtifact(
                name="hamming_decoder.vhd",
                content=self._templates.render("hamming", "decoder"),
                path="src/hamming_decoder.vhd",
                description="Hamming decoder entity and architecture",
            ))
            files.append(FileArtifact(
                name="hamming_decoder_tb.vhd",
                content=self._templates.render("hamming", "testbench"),
                path="tests/hamming_decoder_tb.vhd",
                description="Testbench for hamming decoder",
            ))

        elif template_name == "arty_running_light":
            files.append(FileArtifact(
                name="led_running_light.vhd",
                content=self._templates.render("arty_running_light", "entity")
                + "\n"
                + self._templates.render("arty_running_light", "architecture"),
                path="src/led_running_light.vhd",
                description="Arty S7-50 LED running light with clock divider",
            ))
            files.append(FileArtifact(
                name="led_running_light_tb.vhd",
                content=self._templates.render("arty_running_light", "testbench"),
                path="tests/led_running_light_tb.vhd",
                description="Testbench for Arty S7-50 LED running light",
            ))
            files.append(FileArtifact(
                name="arty_s7_50.xdc",
                content=self._templates.render("arty_running_light", "xdc"),
                path="constraints/arty_s7_50.xdc",
                description="XDC constraints for Arty S7-50 (100 MHz clock, 4 LEDs, reset)",
            ))

        logger.info("Generated %d files from template '%s'", len(files), template_name)
        return ArtifactBundle(files=files, status="generated",
                              metadata={"template": template_name})

    def _generate_fallback(self, request: str, analysis: str) -> ArtifactBundle:
        """Generiert ein minimales VHDL-Skelett wenn kein Template passt.

        Statt ein leeres Bundle zurueckzugeben, wird ein funktionierendes
        Grundgeruest erzeugt, das der OpenCode-Agent dann anpassen kann.
        """
        logger.info("No template matched, generating minimal VHDL skeleton")

        name = self._extract_entity_name(request, "my_component")
        width = self._extract_width(request, 8)
        
        # Detect common patterns and generate appropriate interface
        request_lower = request.lower()
        
        # Comparator pattern
        if any(w in request_lower for w in ["vergleich", "compare", "equal"]):
            entity_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {name} is
    Generic ( WIDTH : positive := {width} );
    Port (
        CLK      : in  STD_LOGIC;
        RESET    : in  STD_LOGIC;
        A        : in  STD_LOGIC_VECTOR(WIDTH-1 downto 0);
        B        : in  STD_LOGIC_VECTOR(WIDTH-1 downto 0);
        EQ       : out STD_LOGIC;
        GT       : out STD_LOGIC;
        LT       : out STD_LOGIC
    );
end {name};
"""
            architecture_code = f"""\
architecture Behavioral of {name} is
begin
    process(CLK)
    begin
        if rising_edge(CLK) then
            if RESET = '1' then
                EQ <= '0';
                GT <= '0';
                LT <= '0';
            else
                if A = B then
                    EQ <= '1'; GT <= '0'; LT <= '0';
                elsif A > B then
                    EQ <= '0'; GT <= '1'; LT <= '0';
                else
                    EQ <= '0'; GT <= '0'; LT <= '1';
                end if;
            end if;
        end if;
    end process;
end Behavioral;
"""
        # Counter pattern
        elif any(w in request_lower for w in ["counter", "zähler", "zaehler", "count"]):
            entity_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity {name} is
    Generic ( WIDTH : positive := {width} );
    Port (
        CLK    : in  STD_LOGIC;
        RESET  : in  STD_LOGIC;
        ENABLE : in  STD_LOGIC;
        COUNT  : out STD_LOGIC_VECTOR(WIDTH-1 downto 0)
    );
end {name};
"""
            architecture_code = f"""\
architecture Behavioral of {name} is
    signal count_reg : unsigned(WIDTH-1 downto 0);
begin
    process(CLK)
    begin
        if rising_edge(CLK) then
            if RESET = '1' then
                count_reg <= (others => '0');
            elsif ENABLE = '1' then
                count_reg <= count_reg + 1;
            end if;
        end if;
    end process;
    COUNT <= std_logic_vector(count_reg);
end Behavioral;
"""
        # Default: simple register
        else:
            entity_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {name} is
    Generic ( WIDTH : positive := {width} );
    Port (
        CLK      : in  STD_LOGIC;
        RESET    : in  STD_LOGIC;
        DATA_IN  : in  STD_LOGIC_VECTOR(WIDTH-1 downto 0);
        DATA_OUT : out STD_LOGIC_VECTOR(WIDTH-1 downto 0)
    );
end {name};
"""
            architecture_code = f"""\
architecture Behavioral of {name} is
begin
    process(CLK)
    begin
        if RESET = '1' then
            DATA_OUT <= (others => '0');
        elsif rising_edge(CLK) then
            DATA_OUT <= DATA_IN;
        end if;
    end process;
end Behavioral;
"""

        # Generate testbench based on interface type
        if any(w in request_lower for w in ["vergleich", "compare", "equal"]):
            tb_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {name}_tb is
end {name}_tb;

architecture Behavioral of {name}_tb is
    constant WIDTH : positive := {width};
    signal CLK      : STD_LOGIC := '0';
    signal RESET    : STD_LOGIC := '0';
    signal A        : STD_LOGIC_VECTOR(WIDTH-1 downto 0) := (others => '0');
    signal B        : STD_LOGIC_VECTOR(WIDTH-1 downto 0) := (others => '0');
    signal EQ       : STD_LOGIC;
    signal GT       : STD_LOGIC;
    signal LT       : STD_LOGIC;
    constant CLK_PERIOD : time := 10 ns;
begin
    uut: entity work.{name}
        generic map (WIDTH => WIDTH)
        port map (
            CLK => CLK,
            RESET => RESET,
            A => A,
            B => B,
            EQ => EQ,
            GT => GT,
            LT => LT
        );

    CLK_GEN: process
    begin
        CLK <= '0';
        wait for CLK_PERIOD / 2;
        CLK <= '1';
        wait for CLK_PERIOD / 2;
    end process;

    STIMULUS: process
    begin
        RESET <= '1';
        wait for CLK_PERIOD * 2;
        RESET <= '0';
        wait for CLK_PERIOD;

        -- Test equal
        A <= X"A5"; B <= X"A5";
        wait for CLK_PERIOD;
        assert EQ = '1' report "EQ should be 1" severity error;

        -- Test A > B
        A <= X"FF"; B <= X"00";
        wait for CLK_PERIOD;
        assert GT = '1' report "GT should be 1" severity error;

        -- Test A < B
        A <= X"00"; B <= X"FF";
        wait for CLK_PERIOD;
        assert LT = '1' report "LT should be 1" severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end Behavioral;
"""
        elif any(w in request_lower for w in ["counter", "zähler", "zaehler", "count"]):
            tb_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity {name}_tb is
end {name}_tb;

architecture Behavioral of {name}_tb is
    constant WIDTH : positive := {width};
    signal CLK    : STD_LOGIC := '0';
    signal RESET  : STD_LOGIC := '0';
    signal ENABLE : STD_LOGIC := '0';
    signal COUNT  : STD_LOGIC_VECTOR(WIDTH-1 downto 0);
    constant CLK_PERIOD : time := 10 ns;
begin
    uut: entity work.{name}
        generic map (WIDTH => WIDTH)
        port map (
            CLK => CLK,
            RESET => RESET,
            ENABLE => ENABLE,
            COUNT => COUNT
        );

    CLK_GEN: process
    begin
        CLK <= '0';
        wait for CLK_PERIOD / 2;
        CLK <= '1';
        wait for CLK_PERIOD / 2;
    end process;

    STIMULUS: process
    begin
        RESET <= '1';
        wait for CLK_PERIOD * 2;
        RESET <= '0';
        ENABLE <= '1';
        wait for CLK_PERIOD * 5;
        assert unsigned(COUNT) = 5
            report "Count should be 5" severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end Behavioral;
"""
        else:
            tb_code = f"""\
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {name}_tb is
end {name}_tb;

architecture Behavioral of {name}_tb is
    constant WIDTH : positive := {width};
    signal CLK      : STD_LOGIC := '0';
    signal RESET    : STD_LOGIC := '0';
    signal DATA_IN  : STD_LOGIC_VECTOR(WIDTH-1 downto 0) := (others => '0');
    signal DATA_OUT : STD_LOGIC_VECTOR(WIDTH-1 downto 0);
    constant CLK_PERIOD : time := 10 ns;
begin
    uut: entity work.{name}
        generic map (WIDTH => WIDTH)
        port map (
            CLK => CLK,
            RESET => RESET,
            DATA_IN => DATA_IN,
            DATA_OUT => DATA_OUT
        );

    CLK_GEN: process
    begin
        CLK <= '0';
        wait for CLK_PERIOD / 2;
        CLK <= '1';
        wait for CLK_PERIOD / 2;
    end process;

    STIMULUS: process
    begin
        RESET <= '1';
        wait for CLK_PERIOD * 2;
        RESET <= '0';
        wait for CLK_PERIOD;

        DATA_IN <= X"A5";
        wait for CLK_PERIOD;
        assert DATA_OUT = X"A5"
            report "Output mismatch" severity error;

        assert false report "TB_COMPLETE" severity note;
        wait;
    end process;
end Behavioral;
"""

        files = [
            FileArtifact(
                name=f"{name}.vhd",
                content=entity_code + "\n" + architecture_code,
                path=f"src/{name}.vhd",
                description=f"{name} entity and architecture (fallback skeleton)",
            ),
            FileArtifact(
                name=f"{name}_tb.vhd",
                content=tb_code,
                path=f"tests/{name}_tb.vhd",
                description=f"Testbench for {name} (fallback skeleton)",
            ),
        ]

        logger.info("Generated fallback skeleton: %d files", len(files))
        return ArtifactBundle(
            files=files,
            status="fallback",
            metadata={
                "template_used": False,
                "matched_template": None,
                "template_score": 0.0,
                "template_status": "none",
                "request": request,
                "analysis": analysis,
            },
        )

    @staticmethod
    def _extract_entity_name(request: str, default: str = "counter") -> str:
        """Extrahiert einen sinnvollen Entity-Namen aus der Anfrage.
        
        Bevorzugt Komponentennamen (Nomen) statt Verben wie "entwickele", "erstelle".
        """
        request_lower = request.lower()
        
        # German verbs to exclude (imperative forms)
        exclude_verbs = {
            "entwickle", "entwickele", "erstelle", "baue", "implementiere",
            "generiere", "erzeuge", "erschaffe", "designe", "projektiere",
            "teste", "pruefe", "validiere", "synthetisiere", "kompiliere",
            "simuliere", "vergleiche", "berechne", "berechne", "leading",
        }
        
        # Common words to exclude
        exclude_words = {
            "vhdl", "counter", "a", "an", "the", "bit", "bits", "mit", "und",
            "oder", "fuer", "ein", "eine", "einen", "der", "die", "das",
            "soll", "sollen", "muss", "muessen", "wird", "werden", "einen",
            "eine", "ein", "4", "8", "16", "32", "bit", "bit-", "bits",
        }
        
        # Strategy 1: Look for noun after articles (einen/eine/ein + Noun)
        match = re.search(r'(?:einen|eine|ein)\s+(\w+)', request_lower)
        if match:
            candidate = match.group(1)
            if candidate not in exclude_verbs and candidate not in exclude_words:
                return candidate
        
        # Strategy 2: Look for known component names
        known_components = {
            "vergleicher": "vergleicher",
            "counter": "counter",
            "zähler": "counter",
            "register": "register",
            "speicher": "memory",
            "ram": "ram",
            "rom": "rom",
            "uart": "uart",
            "spi": "spi",
            "i2c": "i2c",
            " fifo": "fifo",
            "pwm": "pwm",
            "timer": "timer",
            "multiplexer": "multiplexer",
            "demultiplexer": "demultiplexer",
            "encoder": "encoder",
            "decoder": "decoder",
            "addierer": "adder",
            "addier": "adder",
            "subtrahier": "subtractor",
            "alu": "alu",
            "fsm": "fsm",
            "automat": "fsm",
            "lauflicht": "running_light",
            "blink": "blink",
            "takt": "clock",
        }
        
        for keyword, name in known_components.items():
            if keyword in request_lower:
                return name
        
        # Strategy 3: Take the first identifier that's not a verb or common word
        for word in request_lower.split():
            # Clean word from punctuation
            word_clean = re.sub(r'[^a-z0-9]', '', word)
            if (word_clean.isidentifier() and 
                word_clean not in exclude_verbs and 
                word_clean not in exclude_words and
                len(word_clean) > 2):
                return word_clean
        
        return default

    @staticmethod
    def _extract_width(request: str, default: int = 8) -> int:
        match = re.search(r'(\d+)\s*(?:bit|bits)', request.lower())
        if match:
            width = int(match.group(1))
            if width > 0:
                return width
        return default
