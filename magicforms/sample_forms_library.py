"""
Starter draft forms (HR, Finance, Operations, Education, Government, Surveys, IT, Medical, Business correspondence) for every organization.

Used by data migrations and ``manage.py load_sample_forms``.
Idempotent: skips any form whose slug already exists under that entity.

Forms are **draft** and listed in the studio **Starter sample forms** section per organization.
Staff or superusers can **claim** a template they choose; it then appears in their main **Forms**
list with ``created_by`` set to them so they can edit and publish. Unclaimed samples stay in the
starter section. Public links stay off until published.

``SAMPLE_ENTITY_SLUG`` is kept for backwards compatibility (older docs / links); samples are
not limited to that organization.

Medical and legal-style templates are **starting points only**; they are not legal or clinical advice.

Government and public-sector templates are **starting points only**; statutes, retention, and accessibility requirements vary by jurisdiction—customize with qualified review before publishing.

Arabic UI for sample copy (titles, labels, choices, workflow defaults) is provided via
``magicforms/sample_forms_ar.json`` and :func:`magicforms.i18n_db.gettext_db` when the active
language is Arabic—no DB migration. Regenerate JSON with ``scripts/regenerate_sample_forms_ar_json.py``.
"""

from __future__ import annotations

from typing import Any

SAMPLE_ENTITY_SLUG = "sample-forms-library"
SAMPLE_ENTITY_NAME = "Sample forms library"

# category_slug -> (display name, sort order)
SAMPLE_CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("hr", "HR", 0),
    ("finance", "Finance", 10),
    ("operations", "Operations", 20),
    ("education", "Education", 22),
    ("government", "Government", 23),
    ("surveys", "Surveys", 25),
    ("it", "IT", 30),
    ("medical", "Medical / healthcare", 40),
    ("business", "Business correspondence", 50),
)


def _form_specs() -> tuple[dict[str, Any], ...]:
    """Draft sample forms: realistic fields, no file uploads (simpler for empty installs)."""
    return (
        {
            "slug": "sample-leave-request",
            "title": "Leave / time-off request",
            "category": "hr",
            "description": "Request paid or unpaid time away. HR can adapt approval steps in the workflow editor.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "As it should appear on records.", ""),
                ("department", "text", "Department / team", False, "", ""),
                ("leave_type", "select", "Type of leave", True, "", "Annual leave\nSick leave\nUnpaid leave\nOther"),
                ("start_date", "date", "First day off", True, "", ""),
                ("end_date", "date", "Last day off (inclusive)", True, "", ""),
                ("reason", "textarea", "Reason / notes", False, "Optional context for approvers.", ""),
            ),
        },
        {
            "slug": "sample-onboarding-checklist",
            "title": "New hire onboarding",
            "category": "hr",
            "description": "Collect key details before day one. Pair with your HRIS or manual onboarding process.",
            "fields": (
                ("full_name", "text", "Full legal name", True, "", ""),
                ("personal_email", "email", "Personal email", True, "Used before company account exists.", ""),
                ("start_date", "date", "Start date", True, "", ""),
                ("role_title", "text", "Job title", True, "", ""),
                ("manager_name", "text", "Hiring manager", False, "", ""),
                ("equipment_needs", "checkbox", "I need hardware shipped before start", False, "", ""),
                ("notes", "textarea", "Notes for HR", False, "", ""),
            ),
        },
        {
            "slug": "sample-performance-self-review",
            "title": "Performance review (self-assessment)",
            "category": "hr",
            "description": "Annual or mid-cycle self review. Staff can extend with rating scales or competency picklists.",
            "fields": (
                ("review_period", "text", "Review period (e.g. Q1 2026)", True, "", ""),
                ("goals_summary", "textarea", "Goals for this period", True, "", ""),
                ("achievements", "textarea", "Key achievements", True, "", ""),
                ("development_areas", "textarea", "Areas for growth", False, "", ""),
            ),
        },
        {
            "slug": "sample-workplace-incident",
            "title": "Workplace incident report",
            "category": "hr",
            "description": "Safety or conduct incidents. Restrict visibility and workflow assignees in production.",
            "fields": (
                ("incident_date", "date", "Date of incident", True, "", ""),
                ("location", "text", "Location / site", True, "", ""),
                ("severity", "radio", "Severity", True, "", "Low\nMedium\nHigh"),
                ("description", "textarea", "What happened?", True, "Factual description.", ""),
                ("witnesses", "textarea", "Witnesses (optional)", False, "", ""),
                ("reporter_email", "email", "Your email", True, "For follow-up if needed.", ""),
            ),
        },
        {
            "slug": "sample-expense-reimbursement",
            "title": "Expense reimbursement",
            "category": "finance",
            "description": "Employee-paid expenses for approval. Add a file field in the studio for receipts if needed.",
            "fields": (
                ("amount", "number", "Amount (same currency as policy)", True, "Numbers only; decimals allowed.", ""),
                ("expense_date", "date", "Date of expense", True, "", ""),
                ("expense_category", "select", "Category", True, "", "Travel\nMeals\nSoftware\nSupplies\nOther"),
                ("business_purpose", "textarea", "Business purpose", True, "", ""),
                ("receipt_reference", "text", "Receipt # or description", False, "If not attaching a file yet.", ""),
            ),
        },
        {
            "slug": "sample-purchase-requisition",
            "title": "Purchase requisition",
            "category": "finance",
            "description": "Request spend before a PO. Link to budget owner workflow steps in manage.",
            "fields": (
                ("item_description", "textarea", "What are you buying?", True, "", ""),
                ("quantity", "number", "Quantity", True, "", ""),
                ("estimated_total", "number", "Estimated total", True, "", ""),
                ("budget_code", "text", "Cost center / budget code", False, "", ""),
                ("vendor_suggestion", "text", "Preferred vendor (optional)", False, "", ""),
            ),
        },
        {
            "slug": "sample-vendor-intake",
            "title": "Vendor / supplier intake",
            "category": "finance",
            "description": "Basic supplier onboarding. Extend with banking and compliance fields as required.",
            "fields": (
                ("company_name", "text", "Legal company name", True, "", ""),
                ("tax_id", "text", "Tax ID / registration number", False, "", ""),
                ("contact_email", "email", "Primary contact email", True, "", ""),
                ("payment_terms", "select", "Requested payment terms", False, "", "Net 15\nNet 30\nNet 45\nUpon receipt"),
                ("services_summary", "textarea", "Products or services provided", True, "", ""),
            ),
        },
        {
            "slug": "sample-it-service-request",
            "title": "IT service request",
            "category": "operations",
            "description": "Help desk triage. Map workflow steps to L1/L2 teams.",
            "fields": (
                ("system_or_app", "text", "System or application", True, "", ""),
                ("urgency", "radio", "Urgency", True, "", "Standard\nHigh\nEmergency"),
                ("issue_description", "textarea", "Describe the issue", True, "", ""),
                ("error_message", "textarea", "Error text (if any)", False, "", ""),
            ),
        },
        {
            "slug": "sample-room-booking",
            "title": "Room or resource booking",
            "category": "operations",
            "description": "Simple booking request. Replace room list with your real inventory.",
            "fields": (
                ("room", "select", "Room / resource", True, "", "Conference room A\nConference room B\nHuddle space\nAuditorium"),
                ("booking_date", "date", "Date", True, "", ""),
                ("time_window", "text", "Time window", True, "e.g. 09:00–11:00", ""),
                ("attendees", "textarea", "Attendees or headcount", False, "", ""),
            ),
        },
        {
            "slug": "sample-customer-feedback",
            "title": "Customer feedback",
            "category": "operations",
            "description": "Lightweight satisfaction form. Add NPS logic with number validation in the field editor.",
            "fields": (
                ("rating", "number", "Overall rating (1–5)", True, "", ""),
                ("comments", "textarea", "Comments", False, "", ""),
                ("contact_email", "email", "Email (optional, for follow-up)", False, "", ""),
                ("would_recommend", "radio", "Would you recommend us?", False, "", "Yes\nNo\nNot sure"),
            ),
        },
        # --- Surveys ---
        {
            "slug": "sample-survey-nps-pulse",
            "title": "NPS / relationship pulse",
            "category": "surveys",
            "description": "Net-promoter style check-in. Adjust the 0–10 scale validation in the field editor if needed.",
            "fields": (
                ("respondent_role", "select", "I am responding as", False, "", "Customer\nPartner\nEmployee\nOther"),
                ("recommend_score", "number", "How likely are you to recommend us? (0–10)", True, "0 = not at all, 10 = extremely likely.", ""),
                ("primary_reason", "textarea", "What influenced your score the most?", True, "", ""),
                ("improvement_idea", "textarea", "One thing we could do better", False, "", ""),
            ),
        },
        {
            "slug": "sample-survey-event-feedback",
            "title": "Event or session feedback",
            "category": "surveys",
            "description": "Post-workshop or town-hall survey. Duplicate per event and tweak titles in the studio.",
            "fields": (
                ("event_name", "text", "Event name", True, "", ""),
                ("session_date", "date", "Session date", True, "", ""),
                ("content_rating", "radio", "Content quality", True, "", "Excellent\nGood\nFair\nPoor"),
                ("speaker_rating", "radio", "Speaker / facilitator", True, "", "Excellent\nGood\nFair\nPoor"),
                ("highlights", "textarea", "What worked well?", False, "", ""),
                ("suggestions", "textarea", "What should change next time?", False, "", ""),
            ),
        },
        {
            "slug": "sample-survey-employee-engagement",
            "title": "Employee engagement snapshot",
            "category": "surveys",
            "description": "Anonymous-friendly pulse (no names). Pair with sign-in rules and confidentiality notes in production.",
            "fields": (
                ("team", "select", "Team / function (broad)", False, "", "Engineering\nSales\nOperations\nCorporate\nPrefer not to say"),
                ("morale", "radio", "Overall morale this month", True, "", "Very positive\nPositive\nNeutral\nNegative\nVery negative"),
                ("support_from_manager", "radio", "I get enough support from my manager", True, "", "Strongly agree\nAgree\nNeutral\nDisagree\nStrongly disagree"),
                ("open_feedback", "textarea", "Anything else we should hear?", False, "", ""),
            ),
        },
        # --- More HR ---
        {
            "slug": "sample-hr-flexible-work-request",
            "title": "Flexible work arrangement request",
            "category": "hr",
            "description": "Request remote or hybrid patterns. Add approval chains and policy attestations in workflow.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("manager_name", "text", "Manager name", True, "", ""),
                ("arrangement_type", "select", "Requested arrangement", True, "", "Fully remote\nHybrid\nAdjusted hours\nOther"),
                ("effective_date", "date", "Requested effective date", True, "", ""),
                ("business_rationale", "textarea", "Business rationale", True, "", ""),
                ("equipment_notes", "textarea", "Equipment or workplace notes", False, "", ""),
            ),
        },
        {
            "slug": "sample-hr-training-request",
            "title": "Training or certification request",
            "category": "hr",
            "description": "Course, conference, or certification funding. Route to manager then L&D in workflow.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("course_title", "text", "Course / program title", True, "", ""),
                ("provider", "text", "Provider or institution", False, "", ""),
                ("start_date", "date", "Start date", False, "", ""),
                ("cost_estimate", "number", "Estimated cost", False, "Numbers only; decimals allowed.", ""),
                ("justification", "textarea", "How does this support your role or team goals?", True, "", ""),
            ),
        },
        {
            "slug": "sample-hr-reference-check",
            "title": "Employment reference check (referee)",
            "category": "hr",
            "description": "For referees verifying a candidate. Comply with local law; extend with consent references as needed.",
            "fields": (
                ("referee_name", "text", "Your name", True, "", ""),
                ("referee_email", "email", "Your email", True, "", ""),
                ("candidate_name", "text", "Candidate name", True, "", ""),
                ("relationship", "text", "Your relationship to the candidate", True, "e.g. Direct manager, peer, client", ""),
                ("employment_period", "text", "Employment period you can speak to", True, "", ""),
                ("would_rehire", "radio", "Would you rehire this person?", True, "", "Yes\nNo\nWith reservations\nPrefer not to answer"),
                ("comments", "textarea", "Additional factual comments", False, "Stick to verifiable facts your policy allows.", ""),
            ),
        },
        {
            "slug": "sample-hr-grievance-intake",
            "title": "HR concern intake (confidential)",
            "category": "hr",
            "description": "Initial capture for workplace concerns. Restrict access, add legal review steps, and publish only on a secure portal.",
            "fields": (
                ("contact_email", "email", "Contact email (optional if anonymous channel)", False, "", ""),
                ("category", "select", "Category", True, "", "Interpersonal conflict\nPolicy concern\nSafety\nDiscrimination or harassment\nOther"),
                ("involved_parties", "textarea", "Who or what teams are involved? (factual)", True, "", ""),
                ("timeline", "textarea", "When did this occur or begin?", True, "", ""),
                ("desired_outcome", "textarea", "What outcome are you hoping for?", False, "", ""),
                ("supporting_facts", "textarea", "Supporting facts or locations", False, "", ""),
            ),
        },
        {
            "slug": "sample-hr-permission-during-day",
            "title": "Permission to leave during the workday",
            "category": "hr",
            "description": "Short authorized absence (same day, hours away). HR can align with attendance rules and manager approval in workflow.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("department", "text", "Department / team", True, "", ""),
                ("permission_date", "date", "Date of absence", True, "", ""),
                ("leave_from", "text", "Leaving from (time)", True, "e.g. 14:00", ""),
                ("return_by", "text", "Return by (time)", True, "e.g. 16:30", ""),
                ("reason", "textarea", "Reason", True, "Personal appointment, government office, etc.", ""),
                ("manager_name", "text", "Manager name (if pre-approved)", False, "", ""),
            ),
        },
        {
            "slug": "sample-hr-sick-leave",
            "title": "Sick leave request",
            "category": "hr",
            "description": "Dedicated sick-leave capture. Add file upload for medical certificates in the studio if your policy requires them.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("first_day_off", "date", "First day of sick leave", True, "", ""),
                ("last_day_off", "date", "Last day of sick leave (expected)", True, "", ""),
                ("expected_return", "date", "Expected return to work", False, "", ""),
                ("summary", "textarea", "Brief description (optional)", False, "High level only; avoid detailed medical data if policy restricts it.", ""),
                ("medical_document_ref", "text", "Medical certificate / report reference (if any)", False, "Reference number or “will follow”.", ""),
                ("contact_phone", "text", "Daytime phone for HR contact", True, "", ""),
            ),
        },
        {
            "slug": "sample-hr-emergency-leave",
            "title": "Emergency leave request",
            "category": "hr",
            "description": "Unplanned leave for serious personal or family emergencies. Route to HR and line manager per your escalation policy.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("emergency_type", "select", "Nature of emergency", True, "", "Family medical emergency\nDeath in family\nHome / safety emergency\nChildcare emergency\nOther"),
                ("leave_start", "date", "Leave start date", True, "", ""),
                ("leave_end", "date", "Leave end date (expected)", True, "", ""),
                ("explanation", "textarea", "What happened? (factual)", True, "Share what you are comfortable disclosing; HR may follow up.", ""),
                ("contact_phone", "text", "Phone where you can be reached", True, "", ""),
                ("notified_manager", "checkbox", "I have informed or attempted to inform my manager", True, "", ""),
            ),
        },
        # --- More IT ---
        {
            "slug": "sample-it-access-provisioning",
            "title": "Access provisioning request",
            "category": "it",
            "description": "New system, group, or role access. Attach approvals in workflow; add file upload for screenshots if needed.",
            "fields": (
                ("requester_name", "text", "Requester name", True, "", ""),
                ("target_user", "text", "User needing access (if not yourself)", False, "", ""),
                ("system_name", "text", "System or application", True, "", ""),
                ("access_type", "select", "Type of access", True, "", "New account\nRole change\nTemporary elevated access\nAPI or service account"),
                ("business_justification", "textarea", "Business justification", True, "", ""),
                ("needed_by", "date", "Needed by", False, "", ""),
            ),
        },
        {
            "slug": "sample-it-hardware-request",
            "title": "Hardware or peripheral request",
            "category": "it",
            "description": "Laptop, monitor, dock, or accessories. Map asset tags and procurement steps in workflow.",
            "fields": (
                ("employee_name", "text", "Employee name", True, "", ""),
                ("ship_to_location", "text", "Ship-to / office location", True, "", ""),
                ("item_type", "select", "Primary item", True, "", "Laptop\nMonitor\nDocking station\nHeadset\nKeyboard / mouse\nOther"),
                ("spec_preferences", "textarea", "Specifications or model preferences", False, "", ""),
                ("replacement", "radio", "Is this a replacement?", True, "", "Yes\nNo"),
                ("urgency", "radio", "Urgency", True, "", "Standard\nHigh"),
            ),
        },
        {
            "slug": "sample-it-security-incident-triage",
            "title": "Security incident triage (initial report)",
            "category": "it",
            "description": "First report for suspected phishing, malware, or account compromise. Escalate via workflow to security.",
            "fields": (
                ("reporter_name", "text", "Reporter name", True, "", ""),
                ("reporter_email", "email", "Reporter email", True, "", ""),
                ("incident_type", "radio", "Incident type", True, "", "Phishing\nMalware\nUnauthorized access\nLost device\nOther"),
                ("when_noticed", "text", "When did you notice it?", True, "Date and approximate time.", ""),
                ("systems_affected", "textarea", "Systems, accounts, or data possibly affected", True, "", ""),
                ("steps_taken", "textarea", "Steps already taken (e.g. disconnected VPN)", False, "", ""),
            ),
        },
        {
            "slug": "sample-it-change-request",
            "title": "IT change request (lightweight)",
            "category": "it",
            "description": "Small production or configuration changes. Pair with CAB or risk fields for heavier ITIL use cases.",
            "fields": (
                ("change_title", "text", "Change title", True, "", ""),
                ("environment", "radio", "Environment", True, "", "Production\nStaging\nBoth"),
                ("risk_level", "radio", "Perceived risk", True, "", "Low\nMedium\nHigh"),
                ("description", "textarea", "What will change?", True, "", ""),
                ("rollback_plan", "textarea", "Rollback or mitigation plan", False, "", ""),
                ("preferred_window", "text", "Preferred implementation window", False, "", ""),
            ),
        },
        # --- Medical / healthcare (templates only) ---
        {
            "slug": "sample-med-patient-intake",
            "title": "New patient registration (admin)",
            "category": "medical",
            "description": "Administrative intake template only—not a clinical record. Adapt to your jurisdiction, EMR, and privacy program.",
            "fields": (
                ("legal_name", "text", "Legal full name", True, "", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("phone", "text", "Primary phone", True, "", ""),
                ("email", "email", "Email", False, "", ""),
                ("reason_for_visit", "textarea", "Reason for visit (brief)", True, "High-level reason only; not for diagnosis.", ""),
                ("insurance_carrier", "text", "Insurance carrier (if applicable)", False, "", ""),
                ("preferred_language", "select", "Preferred language", False, "", "English\nArabic\nFrench\nSpanish\nOther"),
            ),
        },
        {
            "slug": "sample-med-appointment-request",
            "title": "Appointment request or change",
            "category": "medical",
            "description": "Request a visit or reschedule. Wire to scheduling staff via workflow; not for emergencies.",
            "fields": (
                ("patient_name", "text", "Patient name", True, "", ""),
                ("patient_dob", "date", "Patient date of birth", True, "", ""),
                ("request_type", "select", "Request type", True, "", "New appointment\nReschedule\nCancel\nFollow-up"),
                ("preferred_dates", "textarea", "Preferred dates or times", True, "", ""),
                ("department", "select", "Department or clinic", False, "", "Primary care\nDental\nLab\nImaging\nOther"),
                ("notes", "textarea", "Notes for scheduling (non-urgent)", False, "", ""),
            ),
        },
        {
            "slug": "sample-med-feedback",
            "title": "Care experience feedback",
            "category": "medical",
            "description": "Post-visit satisfaction. Avoid collecting clinical details here; use your privacy notice.",
            "fields": (
                ("visit_date", "date", "Visit date", True, "", ""),
                ("department", "text", "Department or service line", False, "", ""),
                ("overall_care", "radio", "Overall care experience", True, "", "Excellent\nGood\nFair\nPoor"),
                ("staff_communication", "radio", "Staff communication", True, "", "Excellent\nGood\nFair\nPoor"),
                ("wait_time", "radio", "Wait time", True, "", "Very reasonable\nReasonable\nToo long"),
                ("comments", "textarea", "Comments (optional)", False, "", ""),
            ),
        },
        {
            "slug": "sample-med-records-request",
            "title": "Medical records request (administrative)",
            "category": "medical",
            "description": "Template for chart copy or records release workflows. Legal and consent requirements vary—customize before use.",
            "fields": (
                ("requester_name", "text", "Requester full name", True, "", ""),
                ("requester_email", "email", "Requester email", True, "", ""),
                ("patient_name", "text", "Patient name on record", True, "", ""),
                ("patient_dob", "date", "Patient date of birth", True, "", ""),
                ("records_needed", "textarea", "Description of records needed", True, "Date range and type of documents.", ""),
                ("delivery_method", "radio", "Preferred delivery", True, "", "Secure email\nPickup\nPostal mail"),
                ("authorization_attestation", "checkbox", "I confirm I am authorized to request these records (where applicable)", True, "", ""),
            ),
        },
        # --- Business correspondence & workflow ---
        {
            "slug": "sample-biz-internal-memo-request",
            "title": "Internal memo or bulletin request",
            "category": "business",
            "description": "Route internal communications for leadership or comms approval before distribution.",
            "fields": (
                ("requester_name", "text", "Requester name", True, "", ""),
                ("department", "text", "Department", True, "", ""),
                ("audience", "select", "Intended audience", True, "", "All staff\nSingle department\nLeadership only\nProject team"),
                ("subject_line", "text", "Subject / headline", True, "", ""),
                ("key_message", "textarea", "Key message (draft)", True, "", ""),
                ("publish_date", "date", "Requested publish date", False, "", ""),
            ),
        },
        {
            "slug": "sample-biz-external-letter-approval",
            "title": "External letter or email approval",
            "category": "business",
            "description": "Correspondence leaving the organization (customers, regulators, partners). Add legal review steps in workflow.",
            "fields": (
                ("requester_name", "text", "Requester name", True, "", ""),
                ("recipient_type", "select", "Recipient type", True, "", "Customer\nVendor\nRegulator\nPartner\nOther"),
                ("recipient_name", "text", "Recipient name or organization", True, "", ""),
                ("channel", "radio", "Channel", True, "", "Email\nPostal letter\nBoth"),
                ("purpose", "textarea", "Purpose of communication", True, "", ""),
                ("draft_body", "textarea", "Draft body (paste text)", True, "Attach final files in studio if you add a file field.", ""),
                ("deadline", "date", "Send-by deadline", False, "", ""),
            ),
        },
        {
            "slug": "sample-biz-contract-review-intake",
            "title": "Contract or agreement review request",
            "category": "business",
            "description": "Intake for legal or procurement review. Add NDAs, MSAs, and file uploads in the field editor.",
            "fields": (
                ("requester_name", "text", "Requester name", True, "", ""),
                ("counterparty", "text", "Counterparty name", True, "", ""),
                ("agreement_type", "select", "Agreement type", True, "", "NDA\nMSA\nOrder form or SOW\nAmendment\nOther"),
                ("contract_value", "text", "Approximate value or term (if applicable)", False, "", ""),
                ("risk_flags", "checkbox", "This involves unusual liability, data processing, or regulatory exposure", False, "", ""),
                ("summary", "textarea", "Summary of what you need reviewed", True, "", ""),
                ("needed_by", "date", "Decision needed by", True, "", ""),
            ),
        },
        {
            "slug": "sample-biz-rfq-response",
            "title": "RFQ / RFP response coordination",
            "category": "business",
            "description": "Coordinate bid responses across sales, finance, and delivery. Attach pricing sheets via file fields if needed.",
            "fields": (
                ("opportunity_name", "text", "Opportunity or tender name", True, "", ""),
                ("rfq_reference", "text", "RFQ / tender reference", False, "", ""),
                ("bid_due_date", "date", "Submission deadline", True, "", ""),
                ("owner_name", "text", "Bid owner (sales or PM)", True, "", ""),
                ("sections_needed", "textarea", "Sections or attachments needed from other teams", True, "e.g. Pricing, legal, technical architecture", ""),
                ("compliance_notes", "textarea", "Compliance or format requirements", False, "", ""),
            ),
        },
        # --- Education (K–12 school & college starters) ---
        {
            "slug": "sample-edu-field-trip-consent",
            "title": "Field trip permission (K–12)",
            "category": "education",
            "description": "Parent or guardian consent for off-site learning. Add district policy text and emergency contacts in the studio.",
            "fields": (
                ("student_legal_name", "text", "Student full name", True, "", ""),
                ("grade_homeroom", "text", "Grade / homeroom", True, "", ""),
                ("trip_name", "text", "Trip or destination name", True, "", ""),
                ("trip_date", "date", "Trip date", True, "", ""),
                ("guardian_name", "text", "Parent or guardian name", True, "", ""),
                ("guardian_email", "email", "Guardian email", True, "", ""),
                ("guardian_phone", "text", "Daytime phone", True, "", ""),
                ("dietary_medical_notes", "textarea", "Dietary or medical notes staff should know", False, "Allergies, mobility, medication timing—follow your privacy rules.", ""),
                ("consent_ack", "checkbox", "I consent to my child participating in this trip", True, "", ""),
            ),
        },
        {
            "slug": "sample-edu-student-absence-notification",
            "title": "Student absence notification (K–12)",
            "category": "education",
            "description": "Same-day or planned absence message to the school office. Align attendance codes with your SIS.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("student_id", "text", "Student ID (if used)", False, "", ""),
                ("grade", "text", "Grade / class", True, "", ""),
                ("absence_date", "date", "Date of absence", True, "", ""),
                ("absence_type", "select", "Reason category", True, "", "Illness\nFamily matter\nAppointment\nReligious observance\nOther"),
                ("detail", "textarea", "Brief details (optional)", False, "Avoid unnecessary personal health information if policy limits it.", ""),
                ("submitted_by", "select", "Submitted by", True, "", "Parent / guardian\nStudent (secondary)\nSchool staff"),
                ("contact_phone", "text", "Callback phone", True, "", ""),
            ),
        },
        {
            "slug": "sample-edu-parent-teacher-conference",
            "title": "Parent–teacher conference request (K–12)",
            "category": "education",
            "description": "Request a meeting slot with a teacher or team. Pair with scheduling or calendar tools in workflow.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("teacher_name", "text", "Teacher name (if known)", False, "", ""),
                ("preferred_contact", "email", "Your email", True, "", ""),
                ("topics", "textarea", "Topics you would like to discuss", True, "", ""),
                ("availability", "textarea", "General availability (days / times)", True, "e.g. Weekdays after 15:30", ""),
                ("interpreter_needed", "radio", "Interpreter needed", False, "", "No\nYes"),
            ),
        },
        {
            "slug": "sample-edu-club-or-activity-signup",
            "title": "Club or activity signup (K–12)",
            "category": "education",
            "description": "Interest form for sports, arts, or clubs. Add fees, waivers, and capacity limits in the field editor.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("grade", "text", "Grade", True, "", ""),
                ("activity_choice", "select", "Activity", True, "", "Robotics\nDebate\nBasketball\nDrama\nMusic\nSTEM club\nOther"),
                ("experience_level", "radio", "Prior experience", True, "", "Beginner\nSome experience\nAdvanced"),
                ("parent_name", "text", "Parent / guardian name", True, "", ""),
                ("parent_email", "email", "Parent email", True, "", ""),
                ("transportation", "select", "How will the student get home after late activities?", False, "", "School bus\nParent pickup\nWalk\nOther"),
            ),
        },
        {
            "slug": "sample-edu-school-event-volunteer",
            "title": "School event volunteer signup (K–12)",
            "category": "education",
            "description": "Recruit helpers for fairs, sports days, or performances. Add background-check attestation fields if required.",
            "fields": (
                ("volunteer_name", "text", "Volunteer full name", True, "", ""),
                ("email", "email", "Email", True, "", ""),
                ("phone", "text", "Mobile phone", True, "", ""),
                ("event_name", "text", "Event name", True, "", ""),
                ("event_date", "date", "Event date", True, "", ""),
                ("role_preference", "select", "Preferred role", True, "", "Setup / teardown\nRegistration desk\nFood service\nChaperone\nFirst aid liaison\nOther"),
                ("shirt_size", "select", "T-shirt size (if provided)", False, "", "S\nM\nL\nXL\nXXL\nNot needed"),
                ("notes", "textarea", "Notes for organizers", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-course-add-drop-request",
            "title": "Course add / drop request (college)",
            "category": "education",
            "description": "Registrar-friendly intake for schedule changes. Map workflow to advisor and registrar queues.",
            "fields": (
                ("student_name", "text", "Student full name", True, "", ""),
                ("student_id", "text", "Student ID number", True, "", ""),
                ("term", "text", "Term (e.g. Fall 2026)", True, "", ""),
                ("request_type", "select", "Request type", True, "", "Add a course\nDrop a course\nSwap sections\nWithdraw with W grade"),
                ("course_codes", "textarea", "Course code(s) and section(s)", True, "e.g. ENG-101-02", ""),
                ("reason", "textarea", "Academic or personal rationale", True, "", ""),
                ("advisor_name", "text", "Academic advisor (if already consulted)", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-residence-hall-maintenance",
            "title": "Residence hall maintenance request (college)",
            "category": "education",
            "description": "Dorm or apartment-style housing issues. Add photo upload and priority rules in the studio.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("email", "email", "Campus email", True, "", ""),
                ("building_room", "text", "Building and room number", True, "", ""),
                ("issue_type", "select", "Issue type", True, "", "Plumbing\nElectrical\nHVAC / climate\nFurniture\nPest concern\nInternet\nLock / key\nOther"),
                ("urgency", "radio", "Urgency", True, "", "Within a few days\nSame week\nEmergency (safety or flood)"),
                ("description", "textarea", "Describe the problem", True, "", ""),
                ("entry_permission", "checkbox", "Maintenance may enter if I am not present (per housing policy)", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-academic-advising-appointment",
            "title": "Academic advising appointment request (college)",
            "category": "education",
            "description": "Students request a planning session. Connect to advising centers or department workflows.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("student_email", "email", "Student email", True, "", ""),
                ("major_or_program", "text", "Major or intended program", True, "", ""),
                ("year_level", "select", "Year level", True, "", "First year\nSecond year\nThird year\nFourth year\nGraduate\nNon-degree"),
                ("topics", "checklist", "Topics to discuss (check all that apply)", True, "", "Degree audit / graduation plan\nCourse selection\nTransfer credits\nProbation recovery\nCareer or grad school\nOther"),
                ("availability", "textarea", "When are you generally free?", True, "", ""),
            ),
        },
        {
            "slug": "sample-edu-internship-application-internal",
            "title": "Internship or co-op application (college)",
            "category": "education",
            "description": "Internal application for career services or department placements. Extend with GPA or transcript uploads if needed.",
            "fields": (
                ("student_name", "text", "Student name", True, "", ""),
                ("email", "email", "Email", True, "", ""),
                ("term_available", "text", "Term(s) available for placement", True, "e.g. Summer 2026", ""),
                ("preferred_fields", "textarea", "Preferred industries or roles", True, "", ""),
                ("hours_per_week", "number", "Maximum hours per week", True, "", ""),
                ("relocation", "radio", "Open to relocation for the term?", True, "", "Yes\nNo\nOnly local"),
                ("skills_summary", "textarea", "Relevant coursework or skills", True, "", ""),
            ),
        },
        {
            "slug": "sample-edu-student-organization-charter",
            "title": "New student organization charter request (college)",
            "category": "education",
            "description": "Start a new club or society. Add constitution upload and advisor assignment steps in workflow.",
            "fields": (
                ("org_proposed_name", "text", "Proposed organization name", True, "", ""),
                ("purpose", "textarea", "Mission and purpose", True, "", ""),
                ("president_name", "text", "Primary contact (president or chair)", True, "", ""),
                ("contact_email", "email", "Contact email", True, "", ""),
                ("expected_members", "number", "Expected active members (approx.)", False, "", ""),
                ("advisor_name", "text", "Faculty or staff advisor name", False, "If already identified.", ""),
                ("meeting_frequency", "select", "Planned meeting frequency", True, "", "Weekly\nBiweekly\nMonthly\nAs needed"),
                ("funding_interest", "checkbox", "We may request student government funding later", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-kids-registration",
            "title": "Kids program registration (ages 3–6)",
            "category": "education",
            "description": "Early childhood or kindergarten intake. Add immunization uploads, fee schedules, and policy text in the studio.",
            "fields": (
                ("child_legal_name", "text", "Child full legal name", True, "", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("program_level", "select", "Program / grade applying for", True, "", "Pre-K (ages 3–4)\nKindergarten (ages 5–6)\nMixed-age early learning\nOther"),
                ("preferred_start_date", "date", "Preferred start date", True, "", ""),
                ("parent_guardian_name", "text", "Parent or guardian name", True, "", ""),
                ("parent_email", "email", "Parent / guardian email", True, "", ""),
                ("parent_phone", "text", "Parent / guardian phone", True, "", ""),
                ("home_address", "textarea", "Home address", True, "", ""),
                ("previous_care_setting", "text", "Previous preschool or daycare (if any)", False, "", ""),
                ("allergies_medical", "textarea", "Allergies, medications, or medical notes", False, "Follow your privacy and consent rules.", ""),
                ("emergency_contact_name", "text", "Emergency contact name", True, "", ""),
                ("emergency_contact_phone", "text", "Emergency contact phone", True, "", ""),
                ("photo_consent", "checkbox", "I consent to photos/videos for school activities per published policy", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-middle-school-registration",
            "title": "Middle school student registration (grades 6–8)",
            "category": "education",
            "description": "Enrollment intake for lower secondary programs. Map workflow to registrar review and document collection steps.",
            "fields": (
                ("student_legal_name", "text", "Student full legal name", True, "", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("grade_applying", "select", "Grade applying for", True, "", "Grade 6\nGrade 7\nGrade 8"),
                ("school_year", "text", "School year (e.g. 2026–2027)", True, "", ""),
                ("gender", "select", "Gender (if collected per policy)", False, "", "Female\nMale\nNon-binary / another term\nPrefer not to say"),
                ("previous_school", "text", "Previous school name", True, "", ""),
                ("previous_school_city", "text", "Previous school city / country", False, "", ""),
                ("parent_guardian_name", "text", "Parent or guardian name", True, "", ""),
                ("parent_email", "email", "Parent / guardian email", True, "", ""),
                ("parent_phone", "text", "Parent / guardian phone", True, "", ""),
                ("home_address", "textarea", "Home address", True, "", ""),
                ("language_at_home", "select", "Primary language at home", False, "", "Arabic\nEnglish\nFrench\nOther"),
                ("special_education_support", "radio", "Does the student receive learning support or an IEP/504 plan?", False, "", "No\nYes\nNot sure yet"),
                ("emergency_contact_name", "text", "Emergency contact (if different from parent)", False, "", ""),
                ("emergency_contact_phone", "text", "Emergency contact phone", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-high-school-registration",
            "title": "High school student registration (grades 9–12)",
            "category": "education",
            "description": "Upper secondary enrollment with pathway and transcript placeholders. Add transcript upload fields in the studio if needed.",
            "fields": (
                ("student_legal_name", "text", "Student full legal name", True, "", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("grade_applying", "select", "Grade applying for", True, "", "Grade 9\nGrade 10\nGrade 11\nGrade 12"),
                ("school_year", "text", "School year (e.g. 2026–2027)", True, "", ""),
                ("student_email", "email", "Student email (if applicable)", False, "", ""),
                ("pathway", "select", "Academic pathway or track", False, "", "General\nSTEM\nHumanities\nBusiness\nArts\nIB / AP track\nUndecided"),
                ("previous_school", "text", "Previous school name", True, "", ""),
                ("credits_or_curriculum", "textarea", "Prior credits, curriculum, or exam board (if transfer)", False, "e.g. IGCSE, American diploma, national system", ""),
                ("parent_guardian_name", "text", "Parent or guardian name", True, "", ""),
                ("parent_email", "email", "Parent / guardian email", True, "", ""),
                ("parent_phone", "text", "Parent / guardian phone", True, "", ""),
                ("home_address", "textarea", "Home address", True, "", ""),
                ("graduation_year_target", "text", "Expected graduation year", False, "", ""),
                ("activities_interest", "textarea", "Sports, clubs, or activities of interest", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-toefl-exam-registration",
            "title": "TOEFL exam registration intake",
            "category": "education",
            "description": "Collect candidate details before booking TOEFL iBT or Essentials. This is an administrative template—not affiliated with ETS; verify official registration rules.",
            "fields": (
                ("candidate_legal_name", "text", "Full name (as on ID)", True, "Must match passport or national ID used on test day.", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("email", "email", "Email address", True, "Used for scheduling confirmations.", ""),
                ("phone", "text", "Mobile phone", True, "", ""),
                ("id_type", "select", "ID document type", True, "", "Passport\nNational ID card\nOther government photo ID"),
                ("id_number", "text", "ID number (last 4 digits only if policy requires masking)", True, "Store full numbers only if your privacy policy allows.", ""),
                ("test_format", "select", "Test format", True, "", "TOEFL iBT\nTOEFL Essentials\nNot sure—advisor will advise"),
                ("preferred_test_month", "text", "Preferred test month or window", True, "e.g. March 2026", ""),
                ("preferred_location", "text", "Preferred city or test center", False, "", ""),
                ("prior_toefl_score", "text", "Most recent TOEFL score (if retake)", False, "Leave blank if first attempt.", ""),
                ("accommodations", "radio", "Testing accommodations requested", True, "", "None\nYes—contact me to complete accommodations paperwork"),
                ("prep_course_interest", "checkbox", "I am interested in prep course information from the center", False, "", ""),
            ),
        },
        {
            "slug": "sample-edu-standardized-exam-registration",
            "title": "Standardized exam registration (IELTS, SAT, ACT, and more)",
            "category": "education",
            "description": "Multi-exam intake for test centers and schools. Customize exam list and disclaimers; not affiliated with exam boards.",
            "fields": (
                ("candidate_legal_name", "text", "Full name (as on ID)", True, "", ""),
                ("date_of_birth", "date", "Date of birth", True, "", ""),
                ("email", "email", "Email", True, "", ""),
                ("phone", "text", "Mobile phone", True, "", ""),
                ("exam_type", "select", "Exam", True, "", "IELTS Academic\nIELTS General Training\nSAT\nACT\nGRE\nGMAT\nAP Exam\nCambridge B2 First (FCE)\nCambridge C1 Advanced (CAE)\nDuolingo English Test\nOther"),
                ("exam_other_name", "text", "Other exam name (if selected Other)", False, "", ""),
                ("preferred_test_date", "date", "Preferred test date (or first choice)", True, "", ""),
                ("alternate_test_date", "date", "Alternate test date (optional)", False, "", ""),
                ("test_location", "text", "Preferred test center or city", False, "", ""),
                ("id_type", "select", "ID document type", True, "", "Passport\nNational ID\nStudent ID (if accepted for this exam)\nOther"),
                ("prior_scores", "textarea", "Prior scores (optional)", False, "Include exam name, date, and score if retaking.", ""),
                ("accommodations", "radio", "Accommodations or access arrangements needed", True, "", "None\nYes"),
                ("accommodation_details", "textarea", "Accommodation details", False, "Complete only if accommodations = Yes.", ""),
                ("registration_ack", "checkbox", "I understand this form does not replace official exam board registration", True, "Staff will confirm fees and official booking steps.", ""),
            ),
        },
        # --- Government (public sector — templates only; comply with local law before publishing) ---
        {
            "slug": "sample-gov-public-records-request",
            "title": "Public records / information request",
            "category": "government",
            "description": "Administrative template for formal information requests. Statutes, fees, and timelines vary—customize with legal review before use.",
            "fields": (
                ("requester_name", "text", "Requester full name (or organization)", True, "", ""),
                ("requester_email", "email", "Email for correspondence", True, "", ""),
                ("requester_address", "textarea", "Mailing address (if required by policy)", False, "", ""),
                ("record_description", "textarea", "Describe the records you seek (be specific)", True, "Agency, date range, subject, or reference numbers if known.", ""),
                ("preferred_format", "select", "Preferred format", False, "", "Electronic copy\nPaper copy\nInspection only\nNo preference"),
                ("purpose", "textarea", "Purpose of request (if your jurisdiction allows or requires it)", False, "", ""),
            ),
        },
        {
            "slug": "sample-gov-service-feedback-or-complaint",
            "title": "Service feedback or complaint (citizen)",
            "category": "government",
            "description": "311-style intake for programs, facilities, or staff interactions. Add routing and escalation in workflow; not for emergencies.",
            "fields": (
                ("contact_name", "text", "Your name", True, "", ""),
                ("contact_email", "email", "Email", True, "", ""),
                ("contact_phone", "text", "Phone (optional)", False, "", ""),
                ("service_area", "select", "Service or department", True, "", "Streets / sanitation\nUtilities\nParks / recreation\nLicensing\nSocial services\nOther"),
                ("feedback_type", "radio", "Type", True, "", "Compliment\nComplaint\nSuggestion"),
                ("location_or_reference", "text", "Location, case #, or reference (if any)", False, "", ""),
                ("description", "textarea", "What happened?", True, "Facts and dates. For emergencies call your local emergency number—do not use this form.", ""),
            ),
        },
        {
            "slug": "sample-gov-permit-preapplication",
            "title": "Permit pre-application (building / zoning)",
            "category": "government",
            "description": "Early intake before a full permit package. Pair with GIS, fee schedules, and plan-review workflow in production.",
            "fields": (
                ("applicant_name", "text", "Applicant or owner name", True, "", ""),
                ("applicant_email", "email", "Email", True, "", ""),
                ("project_address", "text", "Property address or legal description", True, "", ""),
                ("project_type", "select", "Project type", True, "", "New construction\nAddition / alteration\nDemolition\nChange of use\nSignage\nFence or accessory\nOther"),
                ("scope_summary", "textarea", "Scope summary", True, "Square footage, stories, use, and key dimensions if known.", ""),
                ("questions_for_planner", "textarea", "Questions for planning or building staff", False, "", ""),
            ),
        },
        {
            "slug": "sample-gov-vendor-registration-interest",
            "title": "Vendor / supplier registration interest",
            "category": "government",
            "description": "Initial interest before full procurement onboarding. Extend with certifications, banking, and compliance fields as required.",
            "fields": (
                ("company_legal_name", "text", "Legal entity name", True, "", ""),
                ("tax_id", "text", "Tax ID or registration number", False, "", ""),
                ("primary_contact", "text", "Primary contact name", True, "", ""),
                ("contact_email", "email", "Contact email", True, "", ""),
                ("goods_services", "textarea", "Goods or services offered", True, "NAICS or commodity codes can be added in the studio.", ""),
                ("small_business", "radio", "Small or disadvantaged business classifications (if applicable)", False, "", "Yes\nNo\nPrefer not to state"),
            ),
        },
        {
            "slug": "sample-gov-grant-program-inquiry",
            "title": "Grant program inquiry of interest",
            "category": "government",
            "description": "Expression of interest before a full grant application window. Add eligibility attestations and budget templates in the field editor.",
            "fields": (
                ("organization_name", "text", "Organization name", True, "", ""),
                ("contact_name", "text", "Authorized contact name", True, "", ""),
                ("contact_email", "email", "Email", True, "", ""),
                ("program_name", "text", "Grant program or fund name (if known)", False, "", ""),
                ("project_summary", "textarea", "Proposed project summary", True, "", ""),
                ("estimated_amount", "text", "Estimated funding sought (range or TBD)", False, "", ""),
            ),
        },
        {
            "slug": "sample-gov-public-meeting-appearance",
            "title": "Request to speak or appear at a public meeting",
            "category": "government",
            "description": "Speaker card or agenda-slot style intake. Align with open-meeting laws, time limits, and notice periods for your jurisdiction.",
            "fields": (
                ("requester_name", "text", "Name (or organization representative)", True, "", ""),
                ("requester_email", "email", "Email", True, "", ""),
                ("meeting_body", "select", "Meeting body", True, "", "City council\nCounty board\nPlanning commission\nSchool board\nAdvisory committee\nOther"),
                ("meeting_date", "date", "Meeting date (if known)", False, "", ""),
                ("topic", "textarea", "Topic or agenda item", True, "", ""),
                ("stance", "radio", "Position (optional)", False, "", "Support\nOppose\nNeutral / information only"),
                ("time_requested", "radio", "Time requested", False, "", "Standard slot (e.g. 3 minutes)\nExtended presentation\nNo preference"),
            ),
        },
        {
            "slug": "sample-gov-fraud-waste-abuse-report",
            "title": "Fraud, waste, or abuse concern (internal or external)",
            "category": "government",
            "description": "Hotline-style intake. Restrict access, preserve confidentiality, and route to ethics or oversight per policy—not legal advice.",
            "fields": (
                ("reporter_relationship", "select", "Your relationship to the organization", False, "", "Employee\nContractor\nCitizen / vendor\nPrefer not to say"),
                ("contact_email", "email", "Contact email (optional if anonymous channel exists)", False, "", ""),
                ("category", "select", "Concern category", True, "", "Fraud or theft\nWaste of resources\nAbuse of authority\nConflict of interest\nOther"),
                ("involved_parties", "textarea", "Who or what units are involved? (factual)", True, "", ""),
                ("timeline", "textarea", "When did this occur or begin?", True, "", ""),
                ("description", "textarea", "Description of the concern", True, "Factual summary; avoid speculation where possible.", ""),
            ),
        },
        {
            "slug": "sample-gov-special-event-street-closure",
            "title": "Special event or street closure application",
            "category": "government",
            "description": "Parades, races, or block parties. Add insurance, traffic control, and emergency services coordination fields in the studio.",
            "fields": (
                ("event_organizer", "text", "Organizer or responsible party", True, "", ""),
                ("organizer_email", "email", "Organizer email", True, "", ""),
                ("event_name", "text", "Event name", True, "", ""),
                ("event_date", "date", "Primary event date", True, "", ""),
                ("closure_route", "textarea", "Requested closure area or route", True, "Streets, intersections, and times.", ""),
                ("expected_attendance", "select", "Expected attendance", True, "", "Under 100\n100–500\n500–2,000\nOver 2,000"),
                ("rain_date", "date", "Rain or alternate date (if applicable)", False, "", ""),
                ("alcohol_or_amplified_sound", "checkbox", "Event includes alcohol service or amplified sound (may require additional permits)", False, "", ""),
            ),
        },
    )


SAMPLE_FORM_SLUGS = tuple(spec["slug"] for spec in _form_specs())
SAMPLE_FORM_SLUG_SET = frozenset(SAMPLE_FORM_SLUGS)


def is_starter_sample_slug(slug: str) -> bool:
    return slug in SAMPLE_FORM_SLUG_SET


def is_unclaimed_starter_sample(form) -> bool:
    return is_starter_sample_slug(form.slug) and form.created_by_id is None


def _model_kwargs(model, **kwargs) -> dict:
    """
    Keep only keyword arguments that are fields on ``model``.

    Data migrations call this library with *historical* models, which lack fields added later
    (``options_layout`` arrived in 0042, after 0038 first loaded the samples). Dropping unknown
    kwargs lets a fresh database (test runs, new installs) replay the migration chain.
    """
    names = {f.name for f in model._meta.get_fields()}
    return {k: v for k, v in kwargs.items() if k in names}


def ensure_sample_forms_for_entity(entity, apps) -> int:
    """
    Ensure sample categories (HR, Finance, Operations, Education, Government, Surveys, IT, Medical, Business) and all sample
    forms exist for ``entity``.

    Uses historical models from ``apps`` when called from migrations.

    Returns the number of **new** forms created (0 if this entity already had all samples).
    """
    Form = apps.get_model("magicforms", "Form")
    FormCategory = apps.get_model("magicforms", "FormCategory")
    FormField = apps.get_model("magicforms", "FormField")
    WorkflowStep = apps.get_model("magicforms", "WorkflowStep")

    cat_by_slug: dict[str, Any] = {}
    for slug, name, order in SAMPLE_CATEGORIES:
        cat, _ = FormCategory.objects.get_or_create(
            entity=entity,
            slug=slug,
            defaults=_model_kwargs(FormCategory, name=name, order=order),
        )
        cat_by_slug[slug] = cat

    created = 0
    for spec in _form_specs():
        if Form.objects.filter(entity=entity, slug=spec["slug"]).exists():
            continue
        category = cat_by_slug.get(spec["category"])
        form = Form.objects.create(**_model_kwargs(
            Form,
            entity=entity,
            title=spec["title"][:255],
            slug=spec["slug"][:120],
            description=(spec.get("description") or ""),
            category=category,
            is_published=False,
            is_for_public=True,
            one_time_submit=False,
            hide_from_form_lists=False,
            allow_submission_forward=False,
            created_by=None,
        ))
        for order, row in enumerate(spec["fields"]):
            name, ftype, label, required, help_text, choices = row
            ol = "vertical"
            if ftype == "radio":
                ol = "horizontal"
            FormField.objects.create(**_model_kwargs(
                FormField,
                form=form,
                order=order,
                field_type=ftype,
                name=name[:80],
                label=label[:255],
                help_text=(help_text or "")[:500],
                placeholder="",
                required=required,
                choices_text=(choices or "")[:10000],
                options_layout=ol,
            ))
        WorkflowStep.objects.create(**_model_kwargs(
            WorkflowStep,
            form=form,
            order=0,
            slug="new",
            label="New",
            description="Initial step for new submissions.",
        ))
        created += 1

    return created


def load_sample_forms(apps) -> tuple[int, int]:
    """
    For every organization, create any missing sample categories and forms.

    Also ensures the legacy ``sample-forms-library`` organization exists (older installs and docs).

    Returns ``(entity_count, forms_created_count)``.
    """
    Entity = apps.get_model("magicforms", "Entity")

    Entity.objects.get_or_create(
        slug=SAMPLE_ENTITY_SLUG,
        defaults=_model_kwargs(Entity, name=SAMPLE_ENTITY_NAME, is_active=True, show_on_public_directory=False),
    )

    entities = list(Entity.objects.all().order_by("pk"))
    total_created = 0
    for entity in entities:
        total_created += ensure_sample_forms_for_entity(entity, apps)
    return len(entities), total_created


def ensure_sample_forms_for_entity_live(entity) -> int:
    """Same as :func:`ensure_sample_forms_for_entity` using the live app registry."""
    from django.apps import apps

    return ensure_sample_forms_for_entity(entity, apps)


def load_sample_forms_live() -> tuple[int, int]:
    """Same as :func:`load_sample_forms` using the live app registry (management commands, shell)."""
    from django.apps import apps

    return load_sample_forms(apps)
