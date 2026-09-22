"""HTTP Pydantic schemas. These are the backend source for OpenAPI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterRequest(StrictSchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)


class AcceptInvitationRequest(StrictSchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(StrictSchema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotPasswordRequest(StrictSchema):
    email: EmailStr


class ResetPasswordRequest(StrictSchema):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UserOut(StrictSchema):
    id: str
    email: EmailStr
    full_name: str
    created_at: datetime


class WorkspaceOut(StrictSchema):
    id: str
    name: str
    slug: str
    industry: str | None = None
    role: Literal["owner", "editor", "viewer"]
    permissions: list[str]
    created_at: datetime


class LoginResponse(StrictSchema):
    user: UserOut
    workspaces: list[WorkspaceOut]
    active_workspace_id: str | None
    access_token: str
    expires_at: datetime


class SessionResponse(StrictSchema):
    user: UserOut
    workspaces: list[WorkspaceOut]
    active_workspace_id: str | None
    expires_at: datetime


class SelectWorkspaceRequest(StrictSchema):
    workspace_id: str


class InviteMemberRequest(StrictSchema):
    email: EmailStr
    role: Literal["editor", "viewer"]


class MemberOut(StrictSchema):
    id: str
    user: UserOut | None = None
    role: Literal["owner", "editor", "viewer"]
    status: Literal["active", "invited", "suspended"]
    invited_email: EmailStr | None = None
    invited_by: str | None = None
    invitation_expires_at: datetime | None = None
    joined_at: datetime | None = None


class InviteMemberResponse(StrictSchema):
    member: MemberOut
    outcome: Literal["sent", "email_failed", "already_member", "already_invited"]
    invite_url: str | None = None


class UploadLimits(StrictSchema):
    max_file_size_bytes: int
    max_files_per_request: int
    accepted_kinds: list[str]
    accepted_mime_types: list[str]


class DocumentError(StrictSchema):
    code: str
    message: str
    hint: str | None = None


class DocumentOut(StrictSchema):
    id: str
    workspace_id: str
    filename: str
    kind: str
    mime_type: str
    size: int
    status: str
    progress: int | None
    job_id: str | None = None
    error: DocumentError | None = None
    extracted: dict[str, Any] | None = None
    uploaded_by: str
    uploaded_at: datetime
    processed_at: datetime | None = None


class JobStepOut(StrictSchema):
    key: str
    label: str
    status: str
    progress: int | None = None
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: DocumentError | None = None


class JobErrorOut(StrictSchema):
    code: str
    message: str
    hint: str | None = None
    retryable: bool = False


class JobOut(StrictSchema):
    id: str
    kind: str
    status: str
    title: str
    progress: int | None
    steps: list[JobStepOut]
    result: dict[str, Any] | None = None
    error: JobErrorOut | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancellable: bool


class AcceptedResponse(StrictSchema):
    job_id: str
    job: JobOut


class JobEventOut(StrictSchema):
    id: str
    job_id: str
    at: datetime
    type: str
    message: str
    progress: int | None = None
