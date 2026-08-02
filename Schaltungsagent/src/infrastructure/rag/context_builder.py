class ContextBuilder:
    def build(self, query: str, memory_text: str, context_chunks: list[str]) -> str:
        context_text = "\n\n".join(context_chunks) if context_chunks else ""
        return (
            f"Du bist ein hilfreicher Assistent. Nutze das verfügbare Gedächtnis "
            f"und den relevanten Kontext, um die Frage zu beantworten.\n\n"
            f"Gedächtnis:\n{memory_text or 'Kein vorheriges Gedächtnis verfügbar.'}\n\n"
            f"Kontext:\n{context_text or 'Kein weiterer Kontext verfügbar.'}\n\n"
            f"Nutzerfrage: {query}\n\n"
            f"Antworte auf Deutsch, präzise und hilfreich."
        )
