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


class SkillModel(BaseModel):
    # Do not import the application's CamelModel: it imports SQLModel table constants.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid",
        str_strip_whitespace=True, allow_inf_nan=False, hide_input_in_errors=True,
        ser_json_bytes="base64", val_json_bytes="base64", revalidate_instances="always",
    )


class ModelSettings(SkillModel):
    """Resolved provider configuration, without account IDs, prices, or secrets."""

    provider: NonEmptyStr
    model: NonEmptyStr
    base_url: HttpUrl | None = None
    timeout_seconds: PositiveInt = 900


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
        if self.url and (self.url.username or self.url.password):
            raise ValueError("media URL must not contain login credentials")
        return self


def require_media_kind(media: MediaArtifact | None, kind: str) -> None:
    if media is not None and not media.media_type.startswith(f"{kind}/"):
        raise ValueError(f"expected {kind} media")


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


class SkillError(SkillModel):
    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool = False


class SkillExecutionError(Exception):
    """Expected, sanitized failure. Never put provider payloads or keys in message."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.error = SkillError(code=code, message=message, retryable=retryable)
        super().__init__(message)


InputT = TypeVar("InputT", bound=SkillModel)
OutputT = TypeVar("OutputT", bound=SkillModel)


class SkillResult(SkillModel, Generic[OutputT]):
    status: Literal["success", "error"]
    data: OutputT | None = None
    error: SkillError | None = None
    usage: list[SkillUsage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "success" and (self.data is None or self.error is not None):
            raise ValueError("success requires data and no error")
        if self.status == "error" and self.error is None:
            raise ValueError("error requires an error description")
        return self


class SkillMetadata(SkillModel):
    name: NonEmptyStr
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
            output_schema=SkillResult[self.output_schema].model_json_schema(by_alias=True),
        )

    async def run(
        self, inputs: InputT | Mapping[str, Any], *, api_key: SecretStr | None = None,
    ) -> SkillResult[OutputT]:
        try:
            validated = self.input_schema.model_validate(inputs)
        except ValidationError:
            # ValidationError includes raw prompts/URLs even with hide_input_in_errors.
            return SkillResult(status="error", error=SkillError(
                code="INVALID_INPUT", message="Input does not match the skill schema",
            ))
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

