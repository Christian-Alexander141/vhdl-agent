class WorkflowError(Exception):
    pass


class RAGError(WorkflowError):
    pass


class LLMError(WorkflowError):
    pass


class ArtifactError(WorkflowError):
    pass


class WorkspaceError(WorkflowError):
    pass


class AgentExecutionError(WorkflowError):
    pass


class StateMachineError(WorkflowError):
    pass


class ConfigurationError(WorkflowError):
    pass
