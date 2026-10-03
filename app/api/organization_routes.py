"""Authenticated organization and membership HTTP API for Phase 18B."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.organizations import OrganizationError, Role

from .security import current_account, require_same_origin_browser_request


router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
)


class OrganizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    id: int
    name: str
    personal: bool
    created_at: str
    updated_at: str


class MembershipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: int = Field(gt=0)
    role: Role


class MembershipRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    role: Role


class InvitationResponse(BaseModel):
    id: int
    organization_id: int
    email: str
    role: Role
    expires_at: str
    created_at: str


class InvitationCreatedResponse(InvitationResponse):
    token: str
    accept_path: str


class InvitationPreviewResponse(BaseModel):
    organization_id: int
    organization_name: str
    email_hint: str
    role: Role
    expires_at: str


class MembershipResponse(BaseModel):
    organization_id: int
    account_id: int
    role: Role
    created_at: str


def _service(request: Request):
    service = getattr(
        request.app.state.runtime,
        "organization_service",
        None,
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Organizations are unavailable.",
        )
    return service


async def _account(request: Request):
    account = await current_account(request)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return account


def _organization_response(organization):
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        personal=organization.personal_account_id is not None,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


def _invitation_response(invitation):
    return InvitationResponse(
        id=invitation.id,
        organization_id=invitation.organization_id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


def _email_hint(email):
    local, _, domain = email.partition("@")

    if len(local) <= 1:
        masked = "*"
    else:
        masked = (
            local[0]
            + "*" * min(
                max(len(local) - 1, 1),
                8,
            )
        )

    return (
        f"{masked}@{domain}"
        if domain
        else masked
    )


def _membership_response(membership):
    return MembershipResponse(
        organization_id=membership.organization_id,
        account_id=membership.account_id,
        role=membership.role,
        created_at=membership.created_at,
    )


def _raise_org_error(error: OrganizationError):
    detail = str(error)
    lowered = detail.lower()

    if (
        "access denied" in lowered
        or "does not match signed-in account" in lowered
    ):
        code = status.HTTP_403_FORBIDDEN
    elif "invalid or expired" in lowered:
        code = status.HTTP_410_GONE
    elif "not found" in lowered:
        code = status.HTTP_404_NOT_FOUND
    elif (
        "already exists" in lowered
        or "last organization owner" in lowered
        or "must remain an owner" in lowered
        or "only an organization owner" in lowered
    ):
        code = status.HTTP_409_CONFLICT
    elif "storage operation failed" in lowered:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_422_UNPROCESSABLE_CONTENT

    raise HTTPException(
        status_code=code,
        detail=detail,
    ) from None


@router.get(
    "",
    response_model=list[OrganizationResponse],
)
async def list_organizations(
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        organizations = await asyncio.to_thread(
            service.list_for_account,
            account,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return [
        _organization_response(item)
        for item in organizations
    ]


@router.get(
    "/default",
    response_model=OrganizationResponse,
)
async def default_organization(
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        organization = await asyncio.to_thread(
            service.default_for_account,
            account,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _organization_response(organization)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    payload: OrganizationCreateRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        organization = await asyncio.to_thread(
            service.create,
            account,
            payload.name,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _organization_response(organization)




@router.get(
    "/invitations/{token}",
    response_model=InvitationPreviewResponse,
)
async def preview_invitation(
    token: str,
    request: Request,
    response: Response,
):
    service = _service(request)

    try:
        invitation, organization_name = (
            await asyncio.to_thread(
                service.preview_invitation,
                token,
            )
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"

    return InvitationPreviewResponse(
        organization_id=invitation.organization_id,
        organization_name=organization_name,
        email_hint=_email_hint(
            invitation.email
        ),
        role=invitation.role,
        expires_at=invitation.expires_at,
    )


@router.post(
    "/invitations/{token}/accept",
    response_model=MembershipResponse,
)
async def accept_invitation(
    token: str,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(request)
    service = _service(request)

    try:
        membership = await asyncio.to_thread(
            service.accept_invitation,
            account,
            token,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"

    return _membership_response(
        membership
    )


@router.get(
    "/{organization_id}/invitations",
    response_model=list[InvitationResponse],
)
async def list_invitations(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        invitations = await asyncio.to_thread(
            service.list_invitations,
            account,
            organization_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"

    return [
        _invitation_response(item)
        for item in invitations
    ]


@router.post(
    "/{organization_id}/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    organization_id: int,
    payload: InvitationCreateRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(request)
    service = _service(request)

    try:
        invitation, token = await asyncio.to_thread(
            service.create_invitation,
            account,
            organization_id,
            payload.email,
            payload.role,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"

    return InvitationCreatedResponse(
        **_invitation_response(
            invitation
        ).model_dump(),
        token=token,
        accept_path=(
            f"/api/v1/organizations/"
            f"invitations/{token}/accept"
        ),
    )


@router.delete(
    "/{organization_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    organization_id: int,
    invitation_id: int,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(request)
    service = _service(request)

    try:
        await asyncio.to_thread(
            service.revoke_invitation,
            account,
            organization_id,
            invitation_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return None


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def get_organization(
    organization_id: int,
    request: Request,
    response: Response,
):
    if organization_id <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "organization_id must be positive.",
        )

    account = await _account(request)
    service = _service(request)

    try:
        organization = await asyncio.to_thread(
            service.get,
            account,
            organization_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _organization_response(organization)


@router.get(
    "/{organization_id}/membership/me",
    response_model=MembershipResponse,
)
async def own_membership(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        membership = await asyncio.to_thread(
            service.require_membership,
            account,
            organization_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"

    return _membership_response(
        membership
    )


@router.get(
    "/{organization_id}/members",
    response_model=list[MembershipResponse],
)
async def list_members(
    organization_id: int,
    request: Request,
    response: Response,
):
    account = await _account(request)
    service = _service(request)

    try:
        members = await asyncio.to_thread(
            service.list_memberships_for_manager,
            account,
            organization_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return [
        _membership_response(item)
        for item in members
    ]


@router.post(
    "/{organization_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    organization_id: int,
    payload: MembershipCreateRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        membership = await asyncio.to_thread(
            service.add_member,
            account,
            organization_id,
            payload.account_id,
            payload.role,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _membership_response(membership)


@router.patch(
    "/{organization_id}/members/{account_id}",
    response_model=MembershipResponse,
)
async def update_member_role(
    organization_id: int,
    account_id: int,
    payload: MembershipRoleRequest,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        membership = await asyncio.to_thread(
            service.update_member_role,
            account,
            organization_id,
            account_id,
            payload.role,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return _membership_response(membership)


@router.delete(
    "/{organization_id}/members/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    organization_id: int,
    account_id: int,
    request: Request,
    response: Response,
):
    require_same_origin_browser_request(request)

    account = await _account(request)
    service = _service(request)

    try:
        await asyncio.to_thread(
            service.remove_member,
            account,
            organization_id,
            account_id,
        )
    except OrganizationError as error:
        _raise_org_error(error)

    response.headers["Cache-Control"] = "no-store"
    return None
