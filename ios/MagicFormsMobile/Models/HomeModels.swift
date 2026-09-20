import Foundation

struct HomeSummary: Decodable {
    let inboxCount: Int
    let applicantPendingCount: Int
    let isStaff: Bool
    let isSuperuser: Bool
    let bannerLogoUrl: String
    let bannerEntityName: String
    let menuLinks: MenuLinks

    enum CodingKeys: String, CodingKey {
        case inboxCount = "inbox_count"
        case applicantPendingCount = "applicant_pending_count"
        case isStaff = "is_staff"
        case isSuperuser = "is_superuser"
        case bannerLogoUrl = "banner_logo_url"
        case bannerEntityName = "banner_entity_name"
        case menuLinks = "menu_links"
    }
}

struct MenuLinks: Decodable {
    let studioHome: String
    let inbox: String
    let submissionSearch: String
    let mySignatures: String
    let publicSite: String
    let help: String

    enum CodingKeys: String, CodingKey {
        case studioHome = "studio_home"
        case inbox
        case submissionSearch = "submission_search"
        case mySignatures = "my_signatures"
        case publicSite = "public_site"
        case help
    }
}

struct PublishedFormItem: Decodable, Identifiable {
    let id: Int
    let title: String
    let slug: String
    let description: String
    let entity: FormEntityRef
    let category: FormCategoryRef?
    let submissionDeadline: String?
    let submissionDeadlineLabel: String
    let isForPublic: Bool
    let publicUrl: String
    let introPageEnabled: Bool
    let introPageUrl: String

    enum CodingKeys: String, CodingKey {
        case id, title, slug, description, entity, category
        case submissionDeadline = "submission_deadline"
        case submissionDeadlineLabel = "submission_deadline_label"
        case isForPublic = "is_for_public"
        case publicUrl = "public_url"
        case introPageEnabled = "intro_page_enabled"
        case introPageUrl = "intro_page_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        slug = try c.decode(String.self, forKey: .slug)
        description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
        entity = try c.decode(FormEntityRef.self, forKey: .entity)
        category = try c.decodeIfPresent(FormCategoryRef.self, forKey: .category)
        submissionDeadline = try c.decodeIfPresent(String.self, forKey: .submissionDeadline)
        submissionDeadlineLabel = try c.decodeIfPresent(String.self, forKey: .submissionDeadlineLabel) ?? ""
        isForPublic = try c.decodeIfPresent(Bool.self, forKey: .isForPublic) ?? true
        publicUrl = try c.decodeIfPresent(String.self, forKey: .publicUrl) ?? ""
        introPageEnabled = try c.decodeIfPresent(Bool.self, forKey: .introPageEnabled) ?? false
        introPageUrl = try c.decodeIfPresent(String.self, forKey: .introPageUrl) ?? ""
    }
}

struct FormIntroResponse: Decodable {
    let ok: Bool
    let intro: FormIntroPayload
}

struct FormIntroPayload: Decodable {
    let formId: Int
    let headline: String
    let tagline: String
    let messageHtml: String
    let highlights: [String]
    let highlightsListStyle: String?
    let guidelines: [String]
    let guidelinesListStyle: String?
    let gallery: [FormIntroGalleryItem]
    let schedule: FormIntroSchedule
    let registerBy: FormIntroRegisterBy
    let whereInfo: FormIntroWhere
    let contact: FormIntroContact
    let registration: FormIntroRegistration
    let video: FormIntroVideo?
    let brochureUrl: String?
    let applyLabel: String
    let applyUrl: String
    let closed: Bool
    let canApply: Bool

    enum CodingKeys: String, CodingKey {
        case formId = "form_id"
        case headline, tagline
        case messageHtml = "message_html"
        case highlights
        case highlightsListStyle = "highlights_list_style"
        case guidelines
        case guidelinesListStyle = "guidelines_list_style"
        case gallery, schedule
        case registerBy = "register_by"
        case whereInfo = "where"
        case contact, registration, video
        case brochureUrl = "brochure_url"
        case applyLabel = "apply_label"
        case applyUrl = "apply_url"
        case closed
        case canApply = "can_apply"
    }
}

struct FormIntroGalleryItem: Decodable, Identifiable {
    var id: String { imageUrl }
    let imageUrl: String
    let caption: String
    let alt: String

    enum CodingKeys: String, CodingKey {
        case imageUrl = "image_url"
        case caption, alt
    }
}

struct FormIntroSchedule: Decodable {
    let startsAt: String
    let endsAt: String
    let startsLabel: String
    let endsLabel: String

    enum CodingKeys: String, CodingKey {
        case startsAt = "starts_at"
        case endsAt = "ends_at"
        case startsLabel = "starts_label"
        case endsLabel = "ends_label"
    }
}

struct FormIntroRegisterBy: Decodable {
    let date: String
    let label: String
}

struct FormIntroWhere: Decodable {
    let format: String
    let formatLabel: String
    let location: String
    let mapUrl: String

    enum CodingKeys: String, CodingKey {
        case format
        case formatLabel = "format_label"
        case location
        case mapUrl = "map_url"
    }
}

struct FormIntroContact: Decodable {
    let name: String
    let email: String
    let phone: String
}

struct FormIntroRegistration: Decodable {
    let fee: String
    let showCapacity: Bool
    let capacity: Int?
    let seatsRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case fee
        case showCapacity = "show_capacity"
        case capacity
        case seatsRemaining = "seats_remaining"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        fee = try c.decodeIfPresent(String.self, forKey: .fee) ?? ""
        showCapacity = try c.decodeIfPresent(Bool.self, forKey: .showCapacity) ?? false
        capacity = try c.decodeIfPresent(Int.self, forKey: .capacity)
        seatsRemaining = try c.decodeIfPresent(Int.self, forKey: .seatsRemaining)
    }
}

struct FormIntroVideo: Decodable {
    let provider: String
    let embedUrl: String
    let watchUrl: String

    enum CodingKeys: String, CodingKey {
        case provider
        case embedUrl = "embed_url"
        case watchUrl = "watch_url"
    }
}

struct FormEntityRef: Decodable {
    let id: Int
    let slug: String
    let name: String
}

struct FormCategoryRef: Decodable {
    let slug: String
    let name: String
}

struct InboxListResponse: Decodable {
    let ok: Bool
    let total: Int
    let offset: Int
    let limit: Int
    let items: [InboxItem]
}

struct InboxItem: Decodable, Identifiable, Hashable {
    let id: Int
    let referenceToken: String
    let workflowState: String
    let workflowStateLabel: String
    let form: InboxFormRef
    let submitter: String
    let submittedAt: String
    let submittedAtLabel: String
    let currentStepId: Int?
    let currentStepLabel: String
    let hasUnreadThread: Bool
    let canAct: Bool
    let manageUrl: String
    let roleLabels: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case referenceToken = "reference_token"
        case workflowState = "workflow_state"
        case workflowStateLabel = "workflow_state_label"
        case form, submitter
        case submittedAt = "submitted_at"
        case submittedAtLabel = "submitted_at_label"
        case currentStepId = "current_step_id"
        case currentStepLabel = "current_step_label"
        case hasUnreadThread = "has_unread_thread"
        case canAct = "can_act"
        case manageUrl = "manage_url"
        case roleLabels = "role_labels"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        referenceToken = try c.decodeIfPresent(String.self, forKey: .referenceToken) ?? ""
        workflowState = try c.decodeIfPresent(String.self, forKey: .workflowState) ?? ""
        workflowStateLabel = try c.decodeIfPresent(String.self, forKey: .workflowStateLabel) ?? ""
        form = try c.decode(InboxFormRef.self, forKey: .form)
        submitter = try c.decodeIfPresent(String.self, forKey: .submitter) ?? ""
        submittedAt = try c.decodeIfPresent(String.self, forKey: .submittedAt) ?? ""
        submittedAtLabel = try c.decodeIfPresent(String.self, forKey: .submittedAtLabel) ?? ""
        currentStepId = try c.decodeIfPresent(Int.self, forKey: .currentStepId)
        currentStepLabel = try c.decodeIfPresent(String.self, forKey: .currentStepLabel) ?? ""
        hasUnreadThread = try c.decodeIfPresent(Bool.self, forKey: .hasUnreadThread) ?? false
        canAct = try c.decodeIfPresent(Bool.self, forKey: .canAct) ?? false
        manageUrl = try c.decodeIfPresent(String.self, forKey: .manageUrl) ?? ""
        roleLabels = try c.decodeIfPresent([String].self, forKey: .roleLabels) ?? []
    }
}

struct SubmissionSearchResponse: Decodable {
    let ok: Bool
    let total: Int
    let offset: Int
    let limit: Int
    let relation: String
    let workflowState: String
    let formId: Int?
    let q: String
    let formOptions: [SearchFormOption]
    let items: [InboxItem]

    enum CodingKeys: String, CodingKey {
        case ok, total, offset, limit, relation, q, items
        case workflowState = "workflow_state"
        case formId = "form_id"
        case formOptions = "form_options"
    }
}

struct SearchFormOption: Decodable, Identifiable, Hashable {
    let id: Int
    let title: String
    let slug: String
    let entityName: String

    enum CodingKeys: String, CodingKey {
        case id, title, slug
        case entityName = "entity_name"
    }
}

struct InboxDetailResponse: Decodable {
    let ok: Bool
    let submission: InboxSubmissionDetail
    let values: [SubmissionFieldValue]
    let events: [SubmissionTimelineEvent]
    let thread: SubmissionThreadBlock?
    let documents: SubmissionDocumentsBlock?
}

struct SubmissionDocumentsBlock: Decodable {
    let merged: MergedDocumentRef?
    let attachments: [SubmissionDocumentAttachment]
}

struct MergedDocumentRef: Decodable {
    let hasMergeOutput: Bool
    let canViewPdfInline: Bool
    let showDocxDownload: Bool
    let showOdtDownload: Bool
    let showPdfDownload: Bool
    let pdfApiPath: String
    let docxApiPath: String
    let odtApiPath: String

    enum CodingKeys: String, CodingKey {
        case hasMergeOutput = "has_merge_output"
        case canViewPdfInline = "can_view_pdf_inline"
        case showDocxDownload = "show_docx_download"
        case showOdtDownload = "show_odt_download"
        case showPdfDownload = "show_pdf_download"
        case pdfApiPath = "pdf_api_path"
        case docxApiPath = "docx_api_path"
        case odtApiPath = "odt_api_path"
    }
}

struct SubmissionDocumentAttachment: Decodable, Identifiable {
    let id: Int
    let title: String
    let filename: String
    let isPdf: Bool
    let canPreviewPdf: Bool
    let downloadApiPath: String
    let pdfApiPath: String

    enum CodingKeys: String, CodingKey {
        case id, title, filename
        case isPdf = "is_pdf"
        case canPreviewPdf = "can_preview_pdf"
        case downloadApiPath = "download_api_path"
        case pdfApiPath = "pdf_api_path"
    }
}

struct SubmissionThreadBlock: Decodable {
    let messages: [ThreadMessage]
    let canPost: Bool
    let maxBodyLength: Int

    enum CodingKeys: String, CodingKey {
        case messages
        case canPost = "can_post"
        case maxBodyLength = "max_body_length"
    }
}

struct ThreadMessage: Decodable, Identifiable {
    let id: Int
    let body: String
    let authorUsername: String
    let authorDisplay: String
    let createdAtLabel: String
    let isMine: Bool

    enum CodingKeys: String, CodingKey {
        case id, body
        case authorUsername = "author_username"
        case authorDisplay = "author_display"
        case createdAtLabel = "created_at_label"
        case isMine = "is_mine"
    }
}

struct InboxSubmissionDetail: Decodable {
    let id: Int
    let referenceToken: String
    let workflowState: String
    let workflowStateLabel: String
    let submittedAt: String
    let submittedAtLabel: String
    let updatedAt: String
    let updatedAtLabel: String
    let submitter: String
    let submitterEmail: String
    let currentStepId: Int?
    let currentStepLabel: String
    let canAct: Bool
    let actingAsDelegate: Bool
    let rejectCommentRequired: Bool
    let form: InboxFormRef
    let manageUrl: String

    enum CodingKeys: String, CodingKey {
        case id
        case referenceToken = "reference_token"
        case workflowState = "workflow_state"
        case workflowStateLabel = "workflow_state_label"
        case submittedAt = "submitted_at"
        case submittedAtLabel = "submitted_at_label"
        case updatedAt = "updated_at"
        case updatedAtLabel = "updated_at_label"
        case submitter
        case submitterEmail = "submitter_email"
        case currentStepId = "current_step_id"
        case currentStepLabel = "current_step_label"
        case canAct = "can_act"
        case actingAsDelegate = "acting_as_delegate"
        case rejectCommentRequired = "reject_comment_required"
        case form
        case manageUrl = "manage_url"
    }
}

struct SubmissionFieldValue: Decodable, Identifiable {
    var id: String { "\(valueId)" }
    let valueId: Int
    let fieldName: String
    let fieldLabel: String
    let fieldType: String
    let displayValue: String
    let required: Bool
    let attachment: FieldAttachmentRef?

    enum CodingKeys: String, CodingKey {
        case valueId = "value_id"
        case fieldName = "field_name"
        case fieldLabel = "field_label"
        case fieldType = "field_type"
        case displayValue = "display_value"
        case required
        case attachment
    }
}

struct FieldAttachmentRef: Decodable {
    let filename: String
    let downloadUrl: String
    let apiPath: String

    enum CodingKeys: String, CodingKey {
        case filename
        case downloadUrl = "download_url"
        case apiPath = "api_path"
    }
}

struct SubmissionTimelineEvent: Decodable, Identifiable {
    let id: Int
    let kind: String
    let kindLabel: String
    let message: String
    let createdAt: String
    let createdAtLabel: String
    let stepLabel: String
    let author: String

    enum CodingKeys: String, CodingKey {
        case id, kind
        case kindLabel = "kind_label"
        case message
        case createdAt = "created_at"
        case createdAtLabel = "created_at_label"
        case stepLabel = "step_label"
        case author
    }
}

struct WorkflowActionRequest: Encodable {
    let decision: String
    let comment: String?
    let workflowActionAnchor: Int?

    enum CodingKeys: String, CodingKey {
        case decision, comment
        case workflowActionAnchor = "workflow_action_anchor"
    }
}

struct InboxFormRef: Decodable, Hashable {
    let id: Int
    let title: String
    let slug: String
    let entitySlug: String
    let entityName: String

    enum CodingKeys: String, CodingKey {
        case id, title, slug
        case entitySlug = "entity_slug"
        case entityName = "entity_name"
    }
}

struct HomeSummaryResponse: Decodable {
    let ok: Bool
    let inboxCount: Int
    let applicantPendingCount: Int
    let isStaff: Bool
    let isSuperuser: Bool
    let bannerLogoUrl: String
    let bannerEntityName: String
    let menuLinks: MenuLinks

    enum CodingKeys: String, CodingKey {
        case ok
        case inboxCount = "inbox_count"
        case applicantPendingCount = "applicant_pending_count"
        case isStaff = "is_staff"
        case isSuperuser = "is_superuser"
        case bannerLogoUrl = "banner_logo_url"
        case bannerEntityName = "banner_entity_name"
        case menuLinks = "menu_links"
    }

    var summary: HomeSummary {
        HomeSummary(
            inboxCount: inboxCount,
            applicantPendingCount: applicantPendingCount,
            isStaff: isStaff,
            isSuperuser: isSuperuser,
            bannerLogoUrl: bannerLogoUrl,
            bannerEntityName: bannerEntityName,
            menuLinks: menuLinks
        )
    }
}

struct PublishedFormsResponse: Decodable {
    let ok: Bool
    let forms: [PublishedFormItem]
}

struct FormSchemaResponse: Decodable {
    let ok: Bool
    let form: PublishedFormItem
    let status: String
    let statusMessage: String
    let sections: [FormSectionSchema]
    let fields: [FormFieldSchema]
    let initial: [String: FormInitialValue]
    let visibilityRules: [FormVisibilityRule]
    let related: RelatedFormContext?

    enum CodingKeys: String, CodingKey {
        case ok, form, status, sections, fields, initial, related
        case statusMessage = "status_message"
        case visibilityRules = "visibility_rules"
    }
}

struct RelatedFormContext: Decodable {
    let accessToken: String
    let parentFormTitle: String
    let parentReferenceToken: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case parentFormTitle = "parent_form_title"
        case parentReferenceToken = "parent_reference_token"
    }
}

struct PendingRelatedResponse: Decodable {
    let ok: Bool
    let total: Int
    let items: [PendingRelatedItem]
}

struct PendingRelatedItem: Decodable, Identifiable {
    let accessToken: String
    let invitedAtLabel: String
    let childForm: PendingRelatedFormRef
    let parentSubmission: PendingRelatedParentRef

    var id: String { accessToken }

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case invitedAtLabel = "invited_at_label"
        case childForm = "child_form"
        case parentSubmission = "parent_submission"
    }
}

struct PendingRelatedFormRef: Decodable {
    let id: Int
    let title: String
    let slug: String
    let entitySlug: String
    let entityName: String

    enum CodingKeys: String, CodingKey {
        case id, title, slug
        case entitySlug = "entity_slug"
        case entityName = "entity_name"
    }
}

struct PendingRelatedParentRef: Decodable {
    let id: Int
    let referenceToken: String
    let formTitle: String

    enum CodingKeys: String, CodingKey {
        case id
        case referenceToken = "reference_token"
        case formTitle = "form_title"
    }
}

struct ThreadPostRequest: Encodable {
    let body: String
}

enum FormInitialValue: Decodable {
    case string(String)
    case bool(Bool)
    case strings([String])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let arr = try? container.decode([String].self) {
            self = .strings(arr)
        } else {
            self = .string(try container.decode(String.self))
        }
    }
}

struct FormSectionSchema: Decodable, Identifiable {
    let id: Int
    let title: String
    let description: String
    let startsCollapsed: Bool
    let order: Int

    enum CodingKeys: String, CodingKey {
        case id, title, description, order
        case startsCollapsed = "starts_collapsed"
    }
}

struct FormFieldSchema: Decodable, Identifiable {
    let id: Int
    let key: String
    let name: String
    let fieldType: String
    let label: String
    let helpText: String
    let placeholder: String
    let required: Bool
    let choices: [String]
    let optionsLayout: String
    let inline: Bool
    let sectionId: Int?
    let visibilityControlFieldId: Int?
    let visibilityValues: [String]
    let maxLength: Int?

    enum CodingKeys: String, CodingKey {
        case id, key, name, label, required, choices, inline
        case fieldType = "field_type"
        case helpText = "help_text"
        case placeholder
        case optionsLayout = "options_layout"
        case sectionId = "section_id"
        case visibilityControlFieldId = "visibility_control_field_id"
        case visibilityValues = "visibility_values"
        case maxLength = "max_length"
    }
}

struct FormVisibilityRule: Decodable {
    let target: String
    let control: String
    let values: [String]
}

struct FormSubmitResponse: Decodable {
    let ok: Bool
    let submission: FormSubmitResult?
    let message: String?
    let fieldErrors: [String: [String]]?

    enum CodingKeys: String, CodingKey {
        case ok, submission, message
        case fieldErrors = "field_errors"
    }
}

struct FormSubmitResult: Decodable {
    let id: Int
    let referenceToken: String
    let detailUrl: String

    enum CodingKeys: String, CodingKey {
        case id
        case referenceToken = "reference_token"
        case detailUrl = "detail_url"
    }
}
