class PromptBuilder:
    def build_system_prompt(self, role: str = "assistant") -> str:
        return "Du bist ein hilfreicher Assistent."

    def build_rag_prompt(self, query: str, context: str, memory: str = "") -> str:
        return (
            f"{self.build_system_prompt()}\n\n"
            f"Gedächtnis:\n{memory or 'Kein Gedächtnis verfügbar.'}\n\n"
            f"Kontext:\n{context or 'Kein Kontext verfügbar.'}\n\n"
            f"Frage: {query}"
        )
