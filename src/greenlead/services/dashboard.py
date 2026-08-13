"""Dashboard consolidation business service.

Aggregates metrics and operational data across companies and contacts
for the GreenLead executive and operational dashboard.
Follows strict 4-state integration state tracking (Not Configured, Configured-Unverified, Live-Verified, Error).
"""

import logging
from datetime import UTC, date, datetime

from greenlead.core import policy
from greenlead.core.config import Settings, get_settings
from greenlead.models.schemas import (
    Company,
    Contact,
    DashboardSummary,
    FollowUp,
    Meeting,
    ResearchStatus,
    StorageStatus,
    User,
    WorkQueueItem,
)
from greenlead.repositories.base import (
    CompanyRepository,
    ContactRepository,
    FollowUpRepository,
    MeetingRepository,
)
from greenlead.services import followups as fu
from greenlead.services import meetings as mt

logger = logging.getLogger(__name__)


class DashboardService:
    def __init__(
        self,
        company_repo: CompanyRepository,
        contact_repo: ContactRepository,
        settings: Settings | None = None,
        sheets_verified: bool = False,
        tavily_verified: bool = False,
        ai_verified: bool = False,
        followup_repo: FollowUpRepository | None = None,
        meeting_repo: MeetingRepository | None = None,
        today: date | None = None,
        actor: "User | None" = None,
    ) -> None:
        self._company_repo = company_repo
        self._contact_repo = contact_repo
        self._settings = settings or get_settings()
        self._sheets_verified = sheets_verified
        self._tavily_verified = tavily_verified
        self._ai_verified = ai_verified
        self._followup_repo = followup_repo
        self._meeting_repo = meeting_repo
        self._today = today or datetime.now(UTC).date()
        # When set, every aggregate below counts ONLY records this user may see.
        self._actor = actor

    def _get_storage_status(self) -> StorageStatus:
        has_id = bool(self._settings.google_sheet_id)
        has_file = bool(self._settings.google_service_account_file)

        if not has_id or not has_file:
            return StorageStatus(
                state="not_configured",
                backend_type="in_memory",
                status_label_en="Not Configured (In-Memory Active)",
                status_label_ar="غير مُهيّأ (نموذج الذاكرة مفعّل)",
                details_en="Running isolated in-memory storage. Zero external credentials configured.",
                details_ar="يعمل باستخدام التخزين المؤقت المستقل. لم يتم تحديد بيانات اعتماد خارجية.",
            )

        if self._sheets_verified:
            return StorageStatus(
                state="live_verified",
                backend_type="google_sheets",
                status_label_en="Live — Verified",
                status_label_ar="مباشر — تم التحقق",
                details_en="Google Sheets spreadsheet connection verified successfully via smoke test.",
                details_ar="تم التحقق من اتصال جدول البيانات بنجاح عبر اختبار الاتصال.",
            )

        return StorageStatus(
            state="configured_unverified",
            backend_type="google_sheets",
            status_label_en="Configured — Not Verified",
            status_label_ar="مُهيّأ — لم يتم التحقق",
            details_en="Google Sheets credentials declared but live spreadsheet connection has not been verified.",
            details_ar="تم تقديم بيانات الاعتماد ولكن لم يتم التحقق من الاتصال المباشر بجدول البيانات بعد.",
        )

    def _get_tavily_status(self) -> ResearchStatus:
        has_key = bool(self._settings.tavily_api_key)

        if not has_key:
            return ResearchStatus(
                state="not_configured",
                provider_type="mock",
                status_label_en="Not Configured (Mock Active)",
                status_label_ar="غير مُهيّأ (البحث النموذجي مفعّل)",
                details_en="No API Key configured. Using deterministic mock search provider.",
                details_ar="لم يتم تحديد مفتاح API. يتم استخدام نتائج البحث النموذجية الثابتة.",
            )

        if self._tavily_verified:
            return ResearchStatus(
                state="live_verified",
                provider_type="tavily",
                status_label_en="Live — Verified",
                status_label_ar="مباشر — تم التحقق",
                details_en="Tavily live search API queries verified successfully.",
                details_ar="تم التحقق من الاستعلام المباشر عبر API لـ Tavily بنجاح.",
            )

        return ResearchStatus(
            state="configured_unverified",
            provider_type="tavily",
            status_label_en="Configured — Not Verified",
            status_label_ar="مُهيّأ — لم يتم التحقق",
            details_en="Tavily API key provided but live query execution has not been verified.",
            details_ar="تم تقديم مفتاح API ولكن لم يتم التحقق عبر طلب بحث مباشر بعد.",
        )

    def _get_ai_status(self) -> ResearchStatus:
        provider = (self._settings.ai_provider or "").strip().lower()
        has_key = bool(self._settings.openai_api_key) or bool(
            self._settings.gemini_api_key
        )
        configured = bool(provider) and has_key

        if not configured:
            return ResearchStatus(
                state="not_configured",
                provider_type="ai",
                status_label_en="Not Configured",
                status_label_ar="غير مُهيّأ",
                details_en="No AI provider/key configured. Set AI_PROVIDER and the matching API key to enable.",
                details_ar="لم يتم تحديد مزود أو مفتاح للذكاء الاصطناعي. حدّد AI_PROVIDER والمفتاح المناسب للتفعيل.",
            )

        if self._ai_verified:
            return ResearchStatus(
                state="live_verified",
                provider_type=provider,
                status_label_en="Live — Verified",
                status_label_ar="مباشر — تم التحقق",
                details_en="AI provider model calls verified.",
                details_ar="تم التحقق من استدعاء نموذج الذكاء الاصطناعي بنجاح.",
            )

        return ResearchStatus(
            state="configured_unverified",
            provider_type=provider,
            status_label_en="Configured — Not Verified",
            status_label_ar="مُهيّأ — لم يتم التحقق",
            details_en="AI provider key provided but a live model call has not been verified.",
            details_ar="تم تقديم مفتاح المزود ولكن لم يتم التحقق عبر استدعاء نموذج مباشر بعد.",
        )

    def get_dashboard_summary(self) -> DashboardSummary:
        """Compute all aggregated operational statistics."""
        companies: list[Company] = []
        try:
            companies = self._company_repo.list_companies()
            if self._actor is not None:
                companies = policy.filter_visible(self._actor, companies)
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to list companies for dashboard: %s", e)

        all_contacts: list[Contact] = []
        company_contacts_map: dict[str, list[Contact]] = {}

        for company in companies:
            try:
                c_list = self._contact_repo.list_contacts_by_company(company.id)
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Failed to list contacts for company %s: %s", company.id, e
                )
                c_list = []
            company_contacts_map[company.id] = c_list
            all_contacts.extend(c_list)

        total_companies = len(companies)
        total_contacts = len(all_contacts)

        # Decision makers count
        decision_makers_count = sum(
            1
            for c in all_contacts
            if c.is_decision_maker
            or c.relationship_level.strip().lower() == "decision maker"
        )

        # Verification breakdown
        verified_contacts = sum(
            1
            for c in all_contacts
            if c.verification_status.strip().lower() == "verified"
        )
        unverified_contacts = total_contacts - verified_contacts

        # Companies without contacts & without decision makers
        companies_without_contacts = sum(
            1 for c in companies if len(company_contacts_map.get(c.id, [])) == 0
        )
        companies_without_decision_maker = sum(
            1
            for c in companies
            if not any(
                ct.is_decision_maker
                or ct.relationship_level.strip().lower() == "decision maker"
                for ct in company_contacts_map.get(c.id, [])
            )
        )

        # Missing source URL count
        contacts_missing_source = sum(
            1 for c in all_contacts if not c.source_url.strip()
        )

        # Build Actionable Record-Level Work Queue
        work_queue: list[WorkQueueItem] = []

        # 1. Company level issues
        for company in companies:
            c_contacts = company_contacts_map.get(company.id, [])
            c_name = company.name_ar if company.name_ar else company.name_en

            if len(c_contacts) == 0:
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-comp-no-contact-{company.id}",
                        record_id=company.id,
                        record_name=c_name,
                        record_type="Company",
                        issue_title_en="Company Has No Contacts",
                        issue_title_ar="شركة بدون جهات اتصال",
                        explanation_en="No personnel or contact records registered for this target account.",
                        explanation_ar="لا يوجد موظفون أو سجلات اتصال مسجلة لهذا الحساب المستهدف.",
                        severity="high",
                        link_url=f"/companies/{company.id}/contacts/new",
                        action_label_en="+ Add Contact",
                        action_label_ar="+ إضافة جهة اتصال",
                    )
                )
            elif not any(
                ct.is_decision_maker
                or ct.relationship_level.strip().lower() == "decision maker"
                for ct in c_contacts
            ):
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-comp-no-dm-{company.id}",
                        record_id=company.id,
                        record_name=c_name,
                        record_type="Company",
                        issue_title_en="No Decision Maker Designated",
                        issue_title_ar="لم يتم تعيين صانع قرار",
                        explanation_en="Company has registered contacts but lacks a designated Decision Maker.",
                        explanation_ar="توجد جهات اتصال مسجلة للشركة ولكن يفتقر السجل لصانع قرار مُعيّن.",
                        severity="medium",
                        link_url=f"/companies/{company.id}",
                        action_label_en="Assign Decision Maker",
                        action_label_ar="تعيين صانع قرار",
                    )
                )

        # 2. Contact level issues
        for contact in all_contacts:
            if contact.verification_status.strip().lower() != "verified":
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-contact-unverified-{contact.id}",
                        record_id=contact.id,
                        record_name=contact.name,
                        record_type="Contact",
                        issue_title_en="Unverified Contact Details",
                        issue_title_ar="جهة اتصال غير موثقة",
                        explanation_en=f"Contact details for {contact.name} are pending verification.",
                        explanation_ar=f"بيانات جهة الاتصال {contact.name} قيد انتظار التحقق.",
                        severity="medium",
                        link_url=f"/companies/{contact.company_id}",
                        action_label_en="Verify Record",
                        action_label_ar="التحقق من السجل",
                    )
                )
            if not contact.source_url.strip():
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-contact-no-source-{contact.id}",
                        record_id=contact.id,
                        record_name=contact.name,
                        record_type="Contact",
                        issue_title_en="Missing Source Verification URL",
                        issue_title_ar="رابط المصدر مفقود",
                        explanation_en=f"Contact {contact.name} lacks a LinkedIn or web source link for audit compliance.",
                        explanation_ar=f"جهة الاتصال {contact.name} تفتقر إلى رابط المصدر الموثق للمراجعة.",
                        severity="low",
                        link_url=f"/companies/{contact.company_id}/contacts/{contact.id}/edit",
                        action_label_en="Add Source URL",
                        action_label_ar="إضافة رابط المصدر",
                    )
                )

        # 3. Follow-up derivations (Today view) + overdue work-queue items
        overdue_followups: list[FollowUp] = []
        due_today_followups: list[FollowUp] = []
        upcoming_followups: list[FollowUp] = []
        if self._followup_repo is not None:
            try:
                all_followups = self._followup_repo.list_followups()
                if self._actor is not None:
                    visible_ids = {c.id for c in companies}
                    all_followups = [
                        f
                        for f in all_followups
                        if f.company_id in visible_ids
                        or (f.owner_id and f.owner_id == self._actor.id)
                    ]
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to list follow-ups for dashboard: %s", e)
                all_followups = []
            for f in all_followups:
                if fu.is_overdue(f, self._today):
                    overdue_followups.append(f)
                elif fu.is_due_today(f, self._today):
                    due_today_followups.append(f)
                elif fu.is_upcoming(f, self._today):
                    upcoming_followups.append(f)

            for f in overdue_followups:
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-followup-overdue-{f.id}",
                        record_id=f.id,
                        record_name=f.title,
                        record_type="FollowUp",
                        issue_title_en="Overdue Follow-up",
                        issue_title_ar="متابعة متأخرة",
                        explanation_en=f"Follow-up '{f.title}' was due on {f.due_date}.",
                        explanation_ar=f"المتابعة '{f.title}' كانت مستحقة في {f.due_date}.",
                        severity="high",
                        link_url=f"/followups/{f.id}",
                        action_label_en="Complete Follow-up",
                        action_label_ar="إنهاء المتابعة",
                    )
                )

        # 4. Meeting derivations (Today view) + missing-outcome work-queue items
        meetings_today: list[Meeting] = []
        upcoming_meetings: list[Meeting] = []
        missing_outcome: list[Meeting] = []
        next_meeting: Meeting | None = None
        if self._meeting_repo is not None:
            try:
                all_meetings = self._meeting_repo.list_meetings()
                if self._actor is not None:
                    visible_ids = {c.id for c in companies}
                    all_meetings = [
                        m
                        for m in all_meetings
                        if m.company_id in visible_ids
                        or (m.owner_id and m.owner_id == self._actor.id)
                    ]
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to list meetings for dashboard: %s", e)
                all_meetings = []
            for m in all_meetings:
                if mt.is_today(m, self._today):
                    meetings_today.append(m)
                elif mt.is_upcoming(m, self._today):
                    upcoming_meetings.append(m)
                if mt.is_missing_outcome(m, self._today):
                    missing_outcome.append(m)

            ordered = sorted(
                meetings_today + upcoming_meetings,
                key=lambda m: (m.meeting_date or "9999-12-31", m.start_time or "99:99"),
            )
            next_meeting = ordered[0] if ordered else None
            meetings_today.sort(
                key=lambda m: (m.meeting_date or "", m.start_time or "99:99")
            )

            for m in missing_outcome:
                work_queue.append(
                    WorkQueueItem(
                        id=f"wq-meeting-no-outcome-{m.id}",
                        record_id=m.id,
                        record_name=m.subject,
                        record_type="Meeting",
                        issue_title_en="Meeting Missing Outcome",
                        issue_title_ar="اجتماع بدون نتيجة مسجلة",
                        explanation_en=f"Meeting '{m.subject}' on {m.meeting_date} has no recorded outcome.",
                        explanation_ar=f"الاجتماع '{m.subject}' بتاريخ {m.meeting_date} بدون نتيجة مسجلة.",
                        severity="medium",
                        link_url=f"/meetings/{m.id}",
                        action_label_en="Record Outcome",
                        action_label_ar="تسجيل النتيجة",
                    )
                )

        # Sort Work Queue by severity (high=0, medium=1, low=2)
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        work_queue.sort(key=lambda item: severity_rank.get(item.severity, 3))

        # Sector breakdown
        sectors: dict[str, int] = {}
        for company in companies:
            sec = company.sector.strip() or "Unspecified / غير محدد"
            sectors[sec] = sectors.get(sec, 0) + 1

        # Relationship breakdown
        relationship_counts: dict[str, int] = {}
        for contact in all_contacts:
            rel = contact.relationship_level.strip() or "Contact / جهة اتصال"
            relationship_counts[rel] = relationship_counts.get(rel, 0) + 1

        # Recent records
        sorted_companies = sorted(
            companies, key=lambda x: x.created_at or "", reverse=True
        )[:5]
        sorted_contacts = sorted(
            all_contacts, key=lambda x: x.created_at or "", reverse=True
        )[:5]

        return DashboardSummary(
            total_companies=total_companies,
            total_contacts=total_contacts,
            decision_makers_count=decision_makers_count,
            verified_contacts_count=verified_contacts,
            unverified_contacts_count=unverified_contacts,
            companies_without_contacts_count=companies_without_contacts,
            companies_without_decision_maker_count=companies_without_decision_maker,
            contacts_missing_source_url_count=contacts_missing_source,
            overdue_followups_count=len(overdue_followups),
            followups_due_today_count=len(due_today_followups),
            upcoming_followups_count=len(upcoming_followups),
            today_followups=due_today_followups,
            overdue_followups=overdue_followups,
            meetings_today_count=len(meetings_today),
            upcoming_meetings_count=len(upcoming_meetings),
            meetings_missing_outcome_count=len(missing_outcome),
            meetings_today=meetings_today,
            next_meeting=next_meeting,
            work_queue=work_queue,
            sectors_breakdown=sectors,
            relationship_breakdown=relationship_counts,
            recent_companies=sorted_companies,
            recent_contacts=sorted_contacts,
            storage_status=self._get_storage_status(),
            research_status=self._get_tavily_status(),
            ai_status=self._get_ai_status(),
        )
