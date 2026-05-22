class PipelineGuardError(Exception):
    pass

class ContractNotFound(PipelineGuardError):
    pass

class ContractVersionExists(PipelineGuardError):
    pass

class InvalidSemverBump(PipelineGuardError):
    # Reserved for Phase 1: registry.register() currently warns instead of raising.
    pass
