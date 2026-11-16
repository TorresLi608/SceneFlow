"""Provider-neutral contracts. Importing this module has no application side effects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Generic, Literal, Mapping, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError, model_validator
from pydantic.alias_generators import to_camel


NonEmptyStr = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Milliseconds = Annotated[int, Field(strict=True, ge=0)]
AspectRatio = Annotated[str, Field(pattern=r"^(auto|adaptive|[1-9]\d*:[1-9]\d*)$")]

# How many field problems one INVALID_INPUT reports, and how long a field path may be.
MAX_ERROR_DETAILS = 12
MAX_ERROR_PATH_CHARS = 120


class SkillModel(BaseModel):
    # Do not import the application's CamelModel: it imports SQLModel table constants.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid",
        str_strip_whitespace=True, allow_inf_nan=False, hide_input_in_errors=True,
        ser_json_bytes="base64", val_json_bytes="base64", revalidate_instances="always",
    )


def _reject_url_credentials(url: HttpUrl | None, label: str) -> None:
    # `https://user:key@host` puts a secret into inputs, tool arguments and job payloads.
    if url is not None and (url.username or url.password):
        raise ValueError(f"{label} must not contain login credentials")


class ModelSettings(SkillModel):
    """Resolved provider configuration, without account IDs, prices, or secrets."""

    provider: NonEmptyStr
    model: NonEmptyStr
    base_url: HttpUrl | None = None
    timeout_seconds: PositiveInt = 900

    @model_validator(mode="after")
    def no_embedded_credentials(self) -> Self:
        _reject_url_credentials(self.base_url, "base URL")
        return self


class MediaArtifact(SkillModel):
    """Caller-owned bytes or an external URL; never a SceneFlow storage path.

    Python callers pass bytes; JSON uses URL-safe base64. Consumers choose where
    to store results. Remote URL validation here is syntax-only, not an SSRF guard.
    """

    media_type: Annotated[str, Field(pattern=r"^(image|video|audio)/[^\s;]+$")]
    data: bytes | None = Field(default=None, min_length=1, repr=False)
    url: HttpUrl | None = Field(default=None, repr=False)
    name: NonEmptyStr | None = None
    duration_ms: PositiveInt | None = None
    width: PositiveInt | None = None
    height: PositiveInt | None = None

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if (self.data is None) == (self.url is None):
            raise ValueError("media requires exactly one of data or url")
        _reject_url_credentials(self.url, "media URL")
        return self


def require_media_kind(media: MediaArtifact | None, kind: str) -> None:
    if media is not None and not media.media_type.startswith(f"{kind}/"):
        raise ValueError(f"expected {kind} media")


def require_unique(values: list[str], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")


class SkillUsage(SkillModel):
    """Provider facts only. None means unreported; zero means a reported zero.

    Pricing and balance deductions belong to the host. Decimal quantities are
    JSON strings, so a future SDK never needs a float price round-trip.
    """

    provider: NonEmptyStr
    model: NonEmptyStr
    input_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    output_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    cache_read_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    cache_write_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    quantity: Annotated[Decimal, Field(ge=0)] | None = None
    unit: Literal["token", "image", "second", "request", "character"] | None = None

    @model_validator(mode="after")
    def quantity_has_unit(self) -> Self:
        # A bare number cannot be metered, and a unit with no amount reports nothing.
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("quantity and unit must be reported together")
        return self


class SkillError(SkillModel):
    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool = False
    # `field.path: error_type` entries naming what was wrong, never the offending value.
    details: list[NonEmptyStr] = Field(default_factory=list)


def validation_details(exc: ValidationError) -> list[str]:
    """Where an input failed and why, without any of the input itself.

    A `ValidationError` carries the raw prompt, script or URL in `errors()[..]["input"]`
    even with `hide_input_in_errors`, so it must never be logged or returned whole. The
    field path and Pydantic's error type are enough for a caller — an agent especially —
    to correct the call. `value_error` also keeps its message: those come from this
    package's own validators, which is why their wording must stay free of input values.
    """
    details: list[str] = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False)[:MAX_ERROR_DETAILS]:
        path = ".".join(str(part) for part in error.get("loc") or ())[:MAX_ERROR_PATH_CHARS] or "(input)"
        kind = str(error.get("type") or "invalid")
        reason = str(error.get("msg") or "").removeprefix("Value error, ") if kind == "value_error" else kind
        details.append(f"{path}: {reason or kind}")
    return details


def invalid_input_error(exc: ValidationError) -> SkillError:
    return SkillError(
        code="INVALID_INPUT", message="Input does not match the skill schema",
        details=validation_details(exc),
    )


class SkillExecutionError(Exception):
    """Expected, sanitized failure. Never put provider payloads or keys in message."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        # Blank text would turn a reported failure into a ValidationError raised from here.
        self.error = SkillError(
            code=str(code or "").strip() or "SKILL_FAILED",
            message=str(message or "").strip() or "Skill execution failed",
            retryable=retryable,
        )
        super().__init__(self.error.message)

    def __reduce__(self) -> tuple[Any, ...]:
        # The keyword-only signature breaks the default exception copy/pickle protocol.
        return (_rebuild_execution_error, (self.error.code, self.error.message, self.error.retryable))


def _rebuild_execution_error(code: str, message: str, retryable: bool) -> SkillExecutionError:
    return SkillExecutionError(code, message, retryable=retryable)


InputT = TypeVar("InputT", bound=SkillModel)
OutputT = TypeVar("OutputT", bound=SkillModel)


class SkillResult(SkillModel, Generic[OutputT]):
    """Parametrize with the output type whenever the result carries data.

    Bare `SkillResult(...)` can only validate `data` against the empty `SkillModel` bound,
    so it is for data-less errors. Skills build results with `BaseSkill.success()` /
    `BaseSkill.failure()`, which pick the right parametrization.
    """

    status: Literal["success", "error"]
    data: OutputT | None = None
    error: SkillError | None = None
    usage: list[SkillUsage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def parametrized_when_carrying_data(cls, value: Any) -> Any:
        if cls is SkillResult and isinstance(value, Mapping) and value.get("data") is not None:
            # Otherwise the failure reads as "extra inputs are not permitted" on every
            # output field, which says nothing about the actual mistake.
            raise ValueError("a result carrying data must be SkillResult[Output]; use BaseSkill.success()")
        return value

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "success" and (self.data is None or self.error is not None):
            raise ValueError("success requires data and no error")
        if self.status == "error" and self.error is None:
            raise ValueError("error requires an error description")
        return self


class SkillMetadata(SkillModel):
    # Also a tool/MCP name, so it is limited to what every tool-calling API accepts.
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    description: NonEmptyStr
    version: NonEmptyStr
    implemented: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class BaseSkill(ABC, Generic[InputT, OutputT]):
    """Stateless async capability; credentials are never part of input/tool schemas."""

    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "0.1.0"
    implemented: ClassVar[bool] = False
    input_schema: type[InputT]
    output_schema: type[OutputT]

    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name=self.name, description=self.description, version=self.version,
            implemented=self.implemented,
            input_schema=self.input_schema.model_json_schema(by_alias=True),
            # Serialization mode describes what callers receive: a Decimal quantity is
            # always a string on the wire, though validation would also accept a number.
            output_schema=SkillResult[self.output_schema].model_json_schema(
                by_alias=True, mode="serialization",
            ),
        )

    def success(
        self, data: OutputT | Mapping[str, Any], *,
        usage: list[SkillUsage] | None = None, warnings: list[str] | None = None,
    ) -> SkillResult[OutputT]:
        return SkillResult[self.output_schema](
            status="success", data=data, usage=usage or [], warnings=warnings or [],
        )

    def failure(
        self, code: str, message: str, *, retryable: bool = False,
        data: OutputT | Mapping[str, Any] | None = None,
        usage: list[SkillUsage] | None = None, warnings: list[str] | None = None,
    ) -> SkillResult[OutputT]:
        """A reported failure that may keep partial output and usage already incurred."""
        return SkillResult[self.output_schema](
            status="error", data=data, error=SkillError(code=code, message=message, retryable=retryable),
            usage=usage or [], warnings=warnings or [],
        )

    async def run(
        self, inputs: InputT | Mapping[str, Any], *, api_key: SecretStr | None = None,
    ) -> SkillResult[OutputT]:
        try:
            validated = self.input_schema.model_validate(inputs)
        except ValidationError as exc:
            return SkillResult(status="error", error=invalid_input_error(exc))
        try:
            result = await self.execute(validated, api_key=api_key)
        except SkillExecutionError as exc:
            return SkillResult(status="error", error=exc.error)
        # Output contract defects and unexpected failures propagate for host diagnosis.
        # Cancellation propagates too; the core never retries a potentially paid call.
        return SkillResult[self.output_schema].model_validate(result.model_dump())

    @abstractmethod
    async def execute(self, inputs: InputT, *, api_key: SecretStr | None = None) -> SkillResult[OutputT]:
        """Implement with pure parameters and provider SDKs, without persistence."""
