"""apv term constants, generated from vocab/apv-0.2.ttl. Do not edit by hand.

Regenerate with ``uv run python tools/gen_vocab_py.py``; ``--check`` fails when this file is stale
(docs/architecture EF E.4). The module is pure constants: it never imports rdflib. Names are local
names in the ``apv`` namespace; :func:`term` returns the QName used in PROV-JSON.
"""

from __future__ import annotations

__all__ = ["APV_NS", "CLASSES", "INDIVIDUALS", "PROPERTIES", "VOCAB_VERSION", "term"]

APV_NS = "https://w3id.org/agentprov/ns#"
VOCAB_VERSION = "0.2.0"

CLASSES: frozenset[str] = frozenset(
    {
        "Adapter", "AgentInvocation", "AgentSystem", "Annotation", "Assessment", "AssessmentBundle",
        "AssessmentClaim", "AssistantMessage", "Assumption", "AttackPlan", "Attacker", "AttestingParty",
        "Benchmark", "BlobPart", "CacheRead", "CallStatus", "Capability", "CaptureProfile", "CaptureSession",
        "CheckerRun", "ContextWindow", "CoreBundle", "Decision", "Defence", "DerivationType",
        "DeveloperMessage", "DispatchStatus", "EnvironmentActor", "EnvironmentSeed", "EnvironmentState",
        "EpistemicStatus", "EvidenceClass", "ExecutionDescription", "ExecutionProvenance", "ExecutionRecord",
        "ExecutionStatus", "FilePart", "Fixture", "Gap", "Generator", "GenericActivity", "GenericArtefact",
        "GroundTruth", "Harness", "HarnessRuleEvaluation", "InferenceBundle", "InjectionPayload",
        "IntegrityValue", "Judge", "LegacyProjection", "Mapping", "MarkerStatus", "Message", "MessagePart",
        "Model", "ModelInvocation", "ModelService", "OtherPart", "OtherRoleMessage", "Outcome",
        "OutcomeOrigin", "Pass", "Planner", "PolicyEvaluation", "ProfileStatus", "ProvDerivation",
        "ProvEngine", "RawSourceArtefact", "ReasoningPart", "RefusalPart", "RuleCatalogue", "Run",
        "SandboxState", "SecurityRole", "SemanticAnnotationSet", "SemanticsProfile", "SentTransform",
        "SimulatedUser", "State", "Step", "StoreState", "SubagentInvocation", "SystemMessage", "SystemPrompt",
        "TaskPrompt", "TextPart", "ToolCallRequest", "ToolDefinitions", "ToolExecution", "ToolMessage",
        "ToolResult", "ToolRuntime", "UriPart", "User", "UserMessage", "Verdict",
    }
)

PROPERTIES: frozenset[str] = frozenset(
    {
        "about", "accounting", "activityStatus", "activityStatusStatus", "activityType", "activityTypeStatus",
        "actorRole", "actorRoleStatus", "adapterAssumption", "aerVersion", "afterCausal",
        "afterEvidenceClass", "afterPos", "afterProto", "afterTime", "annotationId", "annotationType",
        "annotationValue", "args", "argsEffective", "argsRawSha256", "argsRawStatus", "artefactRole",
        "artefactType", "artefactTypeStatus", "asSentSha256", "assumption", "attackId", "attackIdStatus",
        "attackTargetId", "attackTargetIdStatus", "attestedBy", "authorName", "basisRule", "benchmark",
        "benchmarkStatus", "bytes", "callRole", "callRoleStatus", "callStatus", "catalogueId", "claim",
        "confidence", "contentLength", "contentSha256", "contentStatus", "contextEncoding", "contextIndex",
        "contextStatus", "corpusVersion", "decisionSubject", "declaredSender", "defenceId", "defenceIdStatus",
        "derivationKey", "derivedAttribute", "dispatchStatus", "durationSeconds", "effectiveArgsStatus",
        "endTimeLexical", "endTimeStatus", "environment", "environmentStatus", "error", "errorStatus",
        "evidenceClass", "exception", "execStatus", "executionId", "executionUnit", "finishReason",
        "finishReasonStatus", "flattenedFrom", "index", "indexStatus", "inputIndex", "instrumentation",
        "integrity", "issue", "markerStatus", "matchedArg", "mediaType", "mediaTypeStatus", "messageRole",
        "method", "mode", "name", "nameStatus", "notObservable", "notProvided", "object", "orderStatus",
        "originBlob", "originContainer", "originKind", "originLabel", "originPath", "originRepository",
        "originRevision", "outcomeClaim", "outcomeHolds", "outcomeName", "outcomeNameStatus", "outcomeOrigin",
        "outcomeScale", "outcomeScore", "outcomeValue", "outcomeValueStatus", "outputStatus",
        "paramsConfigured", "paramsStatus", "paramsTransmitted", "partCount", "partIndex", "partOf",
        "patchSha256", "policy", "premise", "profile", "profileOptions", "property", "provPrimary",
        "provider", "providerCallId", "providerCallIdStatus", "providerStatus", "provides", "reason",
        "reasonStatus", "requestBlob", "requestStatus", "requestedArgsStatus", "requestedModel",
        "requestedModelStatus", "responseBlob", "responseId", "responseIdStatus", "responseStatus", "retryOf",
        "rule", "rulePointer", "scopeStatus", "scopeStatusStatus", "scored", "scoredStatus", "securityRole",
        "semVersion", "sentTransform", "servedModel", "servedModelStatus", "sha256", "softwareName",
        "softwareVersion", "sourceChannel", "sourceKey", "sourcePointer", "spanEnd", "spanStart",
        "startTimeLexical", "startTimeStatus", "stateSha256", "status", "subject", "subtype", "subtypeStatus",
        "taskId", "taskIdStatus", "text", "thread", "threshold", "toolName", "toolNameStatus", "truncated",
        "truncatedStatus", "usage", "usageStatus", "vector", "vectorStatus", "verdict", "version",
        "versionStatus", "viaEntity", "vocabularyVersion",
    }
)

INDIVIDUALS: frozenset[str] = frozenset(
    {
        "ActivityInput", "AgentActsForUser", "AgentSystemRole", "Ambiguous", "AutoExecution", "ByBenchmark",
        "ByCapture", "ByConfig", "ByProvider", "ByReplay", "BySource", "Cached", "CallRequestInput",
        "CapAgentIdentity", "CapContextAttribution", "CapDiscardedReplies", "CapEarlierPasses",
        "CapEnvironmentState", "CapModelCallTimes", "CapOutcome", "CapParams", "CapPerCallState",
        "CapPreDefenceOutput", "CapReasoning", "CapRequestPayload", "CapRequestedArgs", "CapServedModel",
        "CapSystemPrompt", "CapToolDefinitions", "CapToolTimes", "CapUsage", "CheckedCallTrace",
        "CheckedInput", "CheckedOutput", "CheckedPreState", "CheckedState", "CheckerRole",
        "CheckerUsesCallTrace", "CheckerUsesOutput", "CheckerUsesPostState", "CheckerUsesPreState",
        "ContainsPayload", "ContentSource", "ContextMessage", "ContextWindowRole", "DeciderRole",
        "DecisionSubject", "DefenceModification", "DefenceRedaction", "DefenceRole", "Denied", "Derived",
        "Discarded", "EgressRead", "Endorser", "EnvironmentCarriedOver", "EnvironmentDigestCanonical",
        "Error", "ErrorSubstitution", "ExecuteSink", "ExecutingRuntime", "ExposedTo", "Formatting",
        "FreshMessagesPerPass", "FullContextResend", "InferenceProvider", "Inferred", "InitialState",
        "InjectionPlacement", "InjectionPlacementDerivation", "InstrumentationUntruncated",
        "IntegrityUnknown", "Invalid", "Kept", "Labelled", "LastPassOnlyLogging", "Lost", "MethodProvider",
        "ModelInput", "Neutral", "NotApplicable", "NotCaptured", "NotDispatched", "NotObservable",
        "NotRecorded", "Observed", "Ok", "OneCallPerAssistantMessage", "OrderedAfter", "OriginChecker",
        "OriginHarnessDefault", "OriginHarnessRule", "OriginRecomputed", "OtherTransform", "Overwritten",
        "PerformerRole", "PotentiallyInfluencedBy", "QuotesAuthoredContent", "ReasoningPassback",
        "RecordedNull", "RegressionOracle", "ReplayFaithful", "RerunOnEmptyReply", "ResponseSink",
        "RoleRewrite", "RoleUnknown", "RuleInput", "ScriptedUser", "SendSink", "SentTransformed",
        "SequentialToolExecution", "SingleModelPerActor", "ToolDefinitionsInput", "Truncation", "Trusted",
        "Untrusted", "VerdictAllow", "VerdictDeny", "VerdictEscalate", "VerdictModify", "VerdictOther",
        "VerdictRedact", "VerdictTerminate", "Withheld", "WriteSink",
    }
)

_ALL = CLASSES | PROPERTIES | INDIVIDUALS


def term(local: str) -> str:
    """Return ``"apv:" + local`` for a declared term; raise :class:`KeyError` for an undeclared one."""
    if local not in _ALL:
        raise KeyError(f"apv:{local} is not declared in apv {VOCAB_VERSION}")
    return "apv:" + local
