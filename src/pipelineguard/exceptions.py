class PipelineGuardError(Exception):
    pass

class ContractNotFound(PipelineGuardError):
    pass

class ContractVersionExists(PipelineGuardError):
    pass

class InvalidSemverBump(PipelineGuardError):
    pass
