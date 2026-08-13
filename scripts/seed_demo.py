"""Seed a DEMO dataset: users, companies, contacts, follow-ups and meetings.

Run against a fresh database so a visitor can log in and immediately see a
populated dashboard (Today + Needs Attention).

    alembic upgrade head
    python scripts/seed_demo.py

The demo passwords below are intentionally public and weak — they are for a
throwaway local demo ONLY. Production uses real accounts configured via .env;
this script refuses to run when APP_ENV=production.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from greenlead.core.config import get_settings
from greenlead.models.schemas import (
    CompanyCreate,
    ContactCreate,
    FollowUpCreate,
    MeetingCreate,
    User,
    UserCreate,
)
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    get_followup_repository,
    get_meeting_repository,
    get_user_repository,
)
from greenlead.services.companies import CompanyService, DuplicateDomainError
from greenlead.services.contacts import ContactService
from greenlead.services.followups import FollowUpService
from greenlead.services.meetings import MeetingService
from greenlead.services.users import UserService

# (username, password, name, role) — documented in the README demo table.
DEMO_USERS = [
    ("admin", "Admin@123", "System Administrator", "admin"),
    ("manager", "Manager@123", "Sales Manager", "manager"),
    ("sara", "Sara@123", "Sara — BDR", "employee"),
    ("omar", "Omar@123", "Omar — BDR", "employee"),
]


def _today_offset(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def _ensure_user(
    users: UserService, username: str, password: str, name: str, role: str
) -> User:
    existing = users.get_by_username(username)
    if existing is not None:
        return existing
    return users.create_user(
        UserCreate(username=username, password=password, name=name, role=role)
    )


def main() -> int:
    settings = get_settings()
    if settings.app_env == "production":
        print("Refusing to seed demo data while APP_ENV=production.")
        return 1

    users = UserService(get_user_repository())
    companies = CompanyService(get_company_repository())
    contacts = ContactService(get_contact_repository(), get_company_repository())
    followups = FollowUpService(get_followup_repository(), get_company_repository())
    meetings = MeetingService(
        get_meeting_repository(), get_company_repository(), get_contact_repository()
    )

    accounts = {
        username: _ensure_user(users, username, password, name, role)
        for username, password, name, role in DEMO_USERS
    }
    sara, omar = accounts["sara"], accounts["omar"]

    # Companies (owned by the two BDRs), spanning several data-quality states.
    specs = [
        (sara, "Falcon Retail Group", "فالكون للتجزئة", "falconretail.com", "Retail"),
        (sara, "NileTech Solutions", "نايل تك", "niletech.io", "Technology"),
        (omar, "Cedar Health", "الأرز الصحية", "cedarhealth.co", "Healthcare"),
        (omar, "Atlas Logistics", "أطلس اللوجستية", "atlaslogistics.net", "Logistics"),
    ]
    made: dict[str, str] = {}
    for owner, name_en, name_ar, domain, sector in specs:
        try:
            company = companies.create_company_for(
                owner,
                CompanyCreate(
                    name_en=name_en, name_ar=name_ar, domain=domain, sector=sector
                ),
            )
            made[name_en] = company.id
        except DuplicateDomainError:
            continue

    if "Falcon Retail Group" in made:
        cid = made["Falcon Retail Group"]
        contacts.create_contact_for(
            sara,
            ContactCreate(
                company_id=cid,
                name="Layla Hassan",
                title="CISO",
                email="layla@falconretail.com",
                relationship_level="Decision Maker",
                is_decision_maker=True,
                source_url="https://falconretail.com/about",
            ),
        )
        followups.create_followup_for(
            sara,
            FollowUpCreate(
                company_id=cid,
                title="Send Managed-SOC proposal",
                due_date=_today_offset(-2),  # overdue
                priority="High",
            ),
        )
        meetings.create_meeting_for(
            sara,
            MeetingCreate(
                company_id=cid,
                subject="SOC discovery call",
                meeting_type="Online",
                meeting_url="https://meet.example.com/falcon-soc",
                meeting_date=_today_offset(0),  # today
                start_time="14:00",
                end_time="14:45",
            ),
        )

    if "NileTech Solutions" in made:
        # Company with a follow-up due today but no contacts -> Needs Attention.
        followups.create_followup_for(
            sara,
            FollowUpCreate(
                company_id=made["NileTech Solutions"],
                title="Identify decision maker",
                due_date=_today_offset(0),
                priority="Medium",
            ),
        )

    if "Cedar Health" in made:
        cid = made["Cedar Health"]
        contacts.create_contact_for(
            omar,
            ContactCreate(
                company_id=cid,
                name="Karim Nabil",
                title="Head of IT",
                relationship_level="Influencer",
            ),
        )
        meetings.create_meeting_for(
            omar,
            MeetingCreate(
                company_id=cid,
                subject="Compliance review",
                meeting_type="Phone",
                meeting_date=_today_offset(3),  # upcoming
                start_time="11:00",
                end_time="11:30",
            ),
        )

    print("Demo data seeded.\n")
    print(f"{'username':<10}{'password':<14}role")
    print("-" * 34)
    for username, password, _name, role in DEMO_USERS:
        print(f"{username:<10}{password:<14}{role}")
    print(f"\nCompanies: {len(made)} | open http://127.0.0.1:8000 and sign in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
