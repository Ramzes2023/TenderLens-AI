"""Authenticated VALYQON Support Center API."""

from __future__ import annotations

import asyncio
import os
from typing import Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app import __version__
from app.llm.base import LLMError

from app.support import (
    SupportMessage,
    SupportRepositoryError,
    SupportTicket,
    SupportTicketNotFound,
)

from .security import (
    current_account,
    require_same_origin_browser_request,
)


router = APIRouter(
    prefix="/api/v1/support",
    tags=["support"],
)


Category = Literal[
    "technical_problem",
    "tender_data",
    "account_access",
    "company_profile",
    "discovery_matching",
    "billing",
    "feature_request",
    "other",
]


Priority = Literal[
    "low",
    "normal",
    "high",
    "urgent",
]


class TicketCreate(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid"
    )

    first_name: str = Field(
        min_length=1,
        max_length=80,
    )

    last_name: str = Field(
        min_length=1,
        max_length=80,
    )

    email: str = Field(
        min_length=3,
        max_length=254,
    )

    category: Category

    subject: str = Field(
        min_length=3,
        max_length=160,
    )

    description: str = Field(
        min_length=10,
        max_length=8000,
    )

    priority: Priority = "normal"

    page_path: str = Field(
        default="",
        max_length=300,
    )


class TicketResponse(
    BaseModel,
):
    public_id: str

    first_name: str
    last_name: str
    email: str

    category: str

    subject: str
    description: str

    priority: str
    status: str

    organization_id: int | None
    company_id: int | None

    page_path: str
    app_version: str

    created_at: str
    updated_at: str


async def _account(
    request: Request,
):
    account = await current_account(
        request,
        touch=False,
    )

    if account is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication required."
            ),
        )

    return account


def _repository(
    request: Request,
):
    repository = getattr(
        request.app.state.runtime,
        "support_repository",
        None,
    )

    if repository is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support Center "
                "is unavailable."
            ),
        )

    return repository


def _response(
    ticket: SupportTicket,
) -> TicketResponse:

    return TicketResponse(
        public_id=ticket.public_id,
        first_name=ticket.first_name,
        last_name=ticket.last_name,
        email=ticket.email,
        category=ticket.category,
        subject=ticket.subject,
        description=ticket.description,
        priority=ticket.priority,
        status=ticket.status,
        organization_id=(
            ticket.organization_id
        ),
        company_id=(
            ticket.company_id
        ),
        page_path=ticket.page_path,
        app_version=(
            ticket.app_version
        ),
        created_at=(
            ticket.created_at
        ),
        updated_at=(
            ticket.updated_at
        ),
    )




Status = Literal[
    "open",
    "in_progress",
    "resolved",
    "closed",
]


class TicketMessageCreate(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid"
    )

    body: str = Field(
        min_length=1,
        max_length=8000,
    )


class TicketMessageResponse(
    BaseModel,
):
    id: int
    author_type: Literal[
        "user",
        "support",
    ]
    body: str
    created_at: str


class TicketConversationResponse(
    BaseModel,
):
    ticket: TicketResponse
    messages: list[
        TicketMessageResponse
    ]


class TicketStatusUpdate(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid"
    )

    status: Status


def _message_response(
    message: SupportMessage,
) -> TicketMessageResponse:

    return TicketMessageResponse(
        id=message.id,
        author_type=message.author_type,
        body=message.body,
        created_at=message.created_at,
    )


def _support_operator_emails() -> set[str]:

    raw = os.getenv(
        "VALYQON_SUPPORT_OPERATOR_EMAILS",
        "",
    )

    return {
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    }


def _require_support_operator(
    account,
) -> None:

    allowed = (
        _support_operator_emails()
    )

    email = str(
        getattr(
            account,
            "email",
            "",
        )
        or ""
    ).strip().lower()

    if (
        not allowed
        or email not in allowed
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Support operator "
                "access required."
            ),
        )


class SupportAssistantHistoryItem(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid"
    )

    role: Literal[
        "user",
        "assistant",
    ]

    content: str = Field(
        min_length=1,
        max_length=2000,
    )


class SupportAssistantRequest(
    BaseModel,
):
    model_config = ConfigDict(
        extra="forbid"
    )

    message: str = Field(
        min_length=1,
        max_length=2000,
    )

    history: list[
        SupportAssistantHistoryItem
    ] = Field(
        default_factory=list,
        max_length=8,
    )

    page_path: str = Field(
        default="",
        max_length=300,
    )


class SupportAssistantResponse(
    BaseModel,
):
    answer: str
    provider: str
    model: str | None = None


def _support_ai_prompt(
    *,
    message: str,
    history: list[
        SupportAssistantHistoryItem
    ],
    page_path: str,
) -> str:
    history_text = "\n".join(
        (
            "USER: "
            if item.role == "user"
            else "ASSISTANT: "
        )
        + item.content.strip()
        for item in history[-8:]
    )

    return f"""
You are VALYQON Support Assistant.

ROLE
You are the in-product AI support assistant for
VALYQON AI, a Global Procurement Intelligence platform.

You help users understand the product and troubleshoot
normal product workflows.

RESPONSE RULES
- Reply in the same language as the user's latest message
  unless the user explicitly requests another language.
- Be concise, practical and professional.
- Do not invent product features.
- Do not claim an action succeeded unless the available
  context proves that it succeeded.
- Do not claim that a human operator is online.
- Never ask the user to send passwords, session cookies,
  API keys, authentication tokens or other secrets.
- Never expose implementation secrets or credentials.
- If a question requires account-specific investigation,
  private data inspection, manual intervention, or an
  unsupported action, tell the user to create a Support
  request in the Support Center.
- If you do not know something from the product context,
  say that clearly.
- Preliminary company fit is NOT win probability.
- Procurement outcomes are never guaranteed.
- Discovery source availability can depend on source
  health, configuration and credentials.
- Do not imply that discovery automatically imports
  tender documents.
- Do not pretend future functionality is already live.

CURRENT VALYQON PRODUCT CONTEXT
- Product positioning:
  Global Procurement Intelligence powered by AI.
- Main workflow:
  Find -> Analyze -> Score -> Win.
- Users can create organizations and company profiles.
- Company profiles can include products/services,
  search keywords, target markets, currencies,
  contract constraints and capabilities.
- An active company can be used for procurement
  discovery and preliminary matching.
- Discovery aggregates supported procurement sources.
- Supported source adapters include:
  TED / EU,
  UK Find a Tender,
  CanadaBuys,
  AusTender,
  New Zealand GETS,
  South Africa eTenders,
  India CPPP,
  EIS,
  SAM.gov,
  Kazakhstan Goszakup.
- Some sources are public.
- Some sources require configured credentials.
- Discovery can show metadata preview scoring and
  data completeness.
- Metadata preview scoring is preliminary only.
- Full tender/PDF analysis is a separate workflow.
- Existing document workflows can use AI and RAG.
- Monitoring exists for supported configured workflows.
- Telegram is a companion interface and can support
  configured alerts/workflows.
- Team workspaces, organizations, memberships and
  invitations exist.
- Support Center can create persistent support tickets.
- Support tickets have IDs such as VAL-2026-000001.
- Users can review their own support requests.
- Billing / paid-plan workflow is not currently enabled.
- Saved opportunities are not currently implemented.
- The notifications inbox is not currently implemented.
- Automatic discovery-to-document import is not
  currently enabled.
- Do not promise email delivery for support tickets.

SUPPORT ESCALATION
Recommend creating a support ticket when:
- the user reports a bug;
- a specific tender appears incorrect;
- account access needs investigation;
- organization/company state appears inconsistent;
- a repeated technical failure requires manual review.

CURRENT PAGE
{page_path or "(not supplied)"}

RECENT CONVERSATION
{history_text or "(none)"}

LATEST USER MESSAGE
{message.strip()}

Answer the user's latest message now.
""".strip()


@router.post(
    "/assistant",
    response_model=SupportAssistantResponse,
)
async def support_assistant(
    payload: SupportAssistantRequest,
    request: Request,
):
    await _account(request)

    runtime = request.app.state.runtime

    provider = getattr(
        runtime,
        "provider",
        None,
    )

    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI Support Assistant "
                "is not configured."
            ),
        )

    prompt = _support_ai_prompt(
        message=payload.message,
        history=payload.history,
        page_path=payload.page_path,
    )

    try:
        response = await provider.generate(
            prompt,
            max_tokens=700,
        )

    except LLMError:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI Support Assistant "
                "is temporarily unavailable."
            ),
        ) from None

    answer = (
        response.text
        or ""
    ).strip()

    if not answer:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI Support Assistant "
                "returned an empty response."
            ),
        )

    return SupportAssistantResponse(
        answer=answer,
        provider=(
            getattr(
                response,
                "provider",
                None,
            )
            or "configured"
        ),
        model=getattr(
            response,
            "model",
            None,
        ),
    )


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=201,
)
async def create_ticket(
    payload: TicketCreate,
    request: Request,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
    )

    repository = _repository(
        request
    )

    try:
        ticket = await asyncio.to_thread(
            repository.create_ticket,
            owner_user_id=int(
                account.owner_user_id
            ),
            account_id=int(
                account.id
            ),
            first_name=(
                payload.first_name.strip()
            ),
            last_name=(
                payload.last_name.strip()
            ),
            email=(
                payload.email
                .strip()
                .lower()
            ),
            category=payload.category,
            subject=(
                payload.subject.strip()
            ),
            description=(
                payload.description.strip()
            ),
            priority=payload.priority,
            organization_id=None,
            company_id=None,
            page_path=(
                payload.page_path.strip()
            ),
            app_version=__version__,
            browser=(
                request.headers.get(
                    "user-agent"
                )
                or ""
            )[:512],
        )

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support request "
                "could not be saved."
            ),
        ) from None

    return _response(
        ticket
    )


@router.get(
    "/tickets",
    response_model=list[
        TicketResponse
    ],
)
async def list_tickets(
    request: Request,
    limit: int = Query(
        50,
        ge=1,
        le=100,
    ),
):
    account = await _account(
        request
    )

    repository = _repository(
        request
    )

    try:
        tickets = (
            await asyncio.to_thread(
                repository.list_tickets,
                int(
                    account.owner_user_id
                ),
                limit,
            )
        )

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support requests "
                "could not be loaded."
            ),
        ) from None

    return [
        _response(ticket)
        for ticket in tickets
    ]


@router.get(
    "/tickets/{public_id}",
    response_model=TicketResponse,
)
async def get_ticket(
    public_id: str,
    request: Request,
):
    account = await _account(
        request
    )

    repository = _repository(
        request
    )

    try:
        ticket = await asyncio.to_thread(
            repository.get_ticket,
            int(
                account.owner_user_id
            ),
            public_id,
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support request "
                "could not be loaded."
            ),
        ) from None

    return _response(
        ticket
    )


@router.get(
    "/tickets/{public_id}/conversation",
    response_model=TicketConversationResponse,
)
async def get_ticket_conversation(
    public_id: str,
    request: Request,
):
    account = await _account(
        request
    )

    repository = _repository(
        request
    )

    try:
        ticket = await asyncio.to_thread(
            repository.get_ticket,
            int(
                account.owner_user_id
            ),
            public_id,
        )

        messages = await asyncio.to_thread(
            repository.list_ticket_messages,
            int(
                account.owner_user_id
            ),
            public_id,
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support conversation "
                "could not be loaded."
            ),
        ) from None

    return TicketConversationResponse(
        ticket=_response(ticket),
        messages=[
            _message_response(message)
            for message in messages
        ],
    )


@router.post(
    "/tickets/{public_id}/messages",
    response_model=TicketMessageResponse,
    status_code=201,
)
async def add_ticket_message(
    public_id: str,
    payload: TicketMessageCreate,
    request: Request,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
    )

    repository = _repository(
        request
    )

    try:
        message = await asyncio.to_thread(
            repository.add_ticket_message,
            owner_user_id=int(
                account.owner_user_id
            ),
            public_id=public_id,
            account_id=int(
                account.id
            ),
            email=str(
                account.email
            ),
            body=payload.body.strip(),
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support message "
                "could not be saved."
            ),
        ) from None

    return _message_response(
        message
    )


@router.get(
    "/operator/tickets",
    response_model=list[
        TicketResponse
    ],
)
async def operator_list_tickets(
    request: Request,
    status: Status | None = Query(
        default=None
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
    ),
):
    account = await _account(
        request
    )

    _require_support_operator(
        account
    )

    repository = _repository(
        request
    )

    try:
        tickets = await asyncio.to_thread(
            repository.list_all_tickets_for_support,
            limit,
            status,
        )

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support queue "
                "could not be loaded."
            ),
        ) from None

    return [
        _response(ticket)
        for ticket in tickets
    ]


@router.get(
    "/operator/tickets/{public_id}/conversation",
    response_model=TicketConversationResponse,
)
async def operator_get_conversation(
    public_id: str,
    request: Request,
):
    account = await _account(
        request
    )

    _require_support_operator(
        account
    )

    repository = _repository(
        request
    )

    try:
        ticket = await asyncio.to_thread(
            repository.get_ticket_for_support,
            public_id,
        )

        messages = await asyncio.to_thread(
            repository.list_ticket_messages_for_support,
            public_id,
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support conversation "
                "could not be loaded."
            ),
        ) from None

    return TicketConversationResponse(
        ticket=_response(ticket),
        messages=[
            _message_response(message)
            for message in messages
        ],
    )


@router.post(
    "/operator/tickets/{public_id}/messages",
    response_model=TicketMessageResponse,
    status_code=201,
)
async def operator_add_message(
    public_id: str,
    payload: TicketMessageCreate,
    request: Request,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
    )

    _require_support_operator(
        account
    )

    repository = _repository(
        request
    )

    try:
        message = await asyncio.to_thread(
            repository.add_support_message,
            public_id=public_id,
            account_id=int(
                account.id
            ),
            email=str(
                account.email
            ),
            body=payload.body.strip(),
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support reply "
                "could not be saved."
            ),
        ) from None

    return _message_response(
        message
    )


@router.patch(
    "/operator/tickets/{public_id}/status",
    response_model=TicketResponse,
)
async def operator_update_status(
    public_id: str,
    payload: TicketStatusUpdate,
    request: Request,
):
    require_same_origin_browser_request(
        request
    )

    account = await _account(
        request
    )

    _require_support_operator(
        account
    )

    repository = _repository(
        request
    )

    try:
        ticket = await asyncio.to_thread(
            repository.update_ticket_status_for_support,
            public_id,
            payload.status,
        )

    except SupportTicketNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                "Support request "
                "not found."
            ),
        ) from None

    except SupportRepositoryError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Support status "
                "could not be updated."
            ),
        ) from None

    return _response(
        ticket
    )


__all__ = [
    "router",
]