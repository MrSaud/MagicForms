package com.magicforms.mobile.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HomeSummaryResponse(
    val ok: Boolean,
    @SerialName("inbox_count") val inboxCount: Int = 0,
    @SerialName("applicant_pending_count") val applicantPendingCount: Int = 0,
    @SerialName("is_staff") val isStaff: Boolean = false,
    @SerialName("is_superuser") val isSuperuser: Boolean = false,
    @SerialName("banner_logo_url") val bannerLogoUrl: String = "",
    @SerialName("banner_entity_name") val bannerEntityName: String = "",
    @SerialName("menu_links") val menuLinks: MenuLinks = MenuLinks(),
)

@Serializable
data class MenuLinks(
    @SerialName("studio_home") val studioHome: String = "",
    val inbox: String = "",
    @SerialName("submission_search") val submissionSearch: String = "",
    @SerialName("my_signatures") val mySignatures: String = "",
    @SerialName("public_site") val publicSite: String = "",
    val help: String = "",
)

@Serializable
data class PublishedFormsResponse(
    val ok: Boolean,
    val forms: List<PublishedFormItem> = emptyList(),
)

@Serializable
data class PublishedFormItem(
    val id: Int,
    val title: String,
    val slug: String,
    val description: String = "",
    val entity: FormEntityRef,
    val category: FormCategoryRef? = null,
    @SerialName("submission_deadline") val submissionDeadline: String? = null,
    @SerialName("submission_deadline_label") val submissionDeadlineLabel: String = "",
    @SerialName("is_for_public") val isForPublic: Boolean = true,
    @SerialName("public_url") val publicUrl: String,
    @SerialName("intro_page_enabled") val introPageEnabled: Boolean = false,
    @SerialName("intro_page_url") val introPageUrl: String = "",
)

@Serializable
data class FormIntroResponse(
    val ok: Boolean,
    val intro: FormIntroPayload,
)

@Serializable
data class FormIntroPayload(
    @SerialName("form_id") val formId: Int,
    val headline: String = "",
    val tagline: String = "",
    @SerialName("message_html") val messageHtml: String = "",
    val highlights: List<String> = emptyList(),
    @SerialName("highlights_list_style") val highlightsListStyle: String = "bullet",
    val guidelines: List<String> = emptyList(),
    @SerialName("guidelines_list_style") val guidelinesListStyle: String = "bullet",
    val gallery: List<FormIntroGalleryItem> = emptyList(),
    val schedule: FormIntroSchedule = FormIntroSchedule(),
    @SerialName("register_by") val registerBy: FormIntroRegisterBy = FormIntroRegisterBy(),
    val where: FormIntroWhere = FormIntroWhere(),
    val contact: FormIntroContact = FormIntroContact(),
    val registration: FormIntroRegistration = FormIntroRegistration(),
    val video: FormIntroVideo? = null,
    @SerialName("brochure_url") val brochureUrl: String? = null,
    @SerialName("apply_label") val applyLabel: String = "",
    @SerialName("apply_url") val applyUrl: String = "",
    val closed: Boolean = false,
    @SerialName("can_apply") val canApply: Boolean = true,
)

@Serializable
data class FormIntroGalleryItem(
    @SerialName("image_url") val imageUrl: String,
    val caption: String = "",
    val alt: String = "",
)

@Serializable
data class FormIntroSchedule(
    @SerialName("starts_at") val startsAt: String = "",
    @SerialName("ends_at") val endsAt: String = "",
    @SerialName("starts_label") val startsLabel: String = "",
    @SerialName("ends_label") val endsLabel: String = "",
)

@Serializable
data class FormIntroRegisterBy(
    val date: String = "",
    val label: String = "",
)

@Serializable
data class FormIntroWhere(
    val format: String = "",
    @SerialName("format_label") val formatLabel: String = "",
    val location: String = "",
    @SerialName("map_url") val mapUrl: String = "",
)

@Serializable
data class FormIntroContact(
    val name: String = "",
    val email: String = "",
    val phone: String = "",
)

@Serializable
data class FormIntroRegistration(
    val fee: String = "",
    @SerialName("show_capacity") val showCapacity: Boolean = false,
    val capacity: Int? = null,
    @SerialName("seats_remaining") val seatsRemaining: Int? = null,
)

@Serializable
data class FormIntroVideo(
    val provider: String = "",
    @SerialName("embed_url") val embedUrl: String = "",
    @SerialName("watch_url") val watchUrl: String = "",
)

@Serializable
data class FormEntityRef(
    val id: Int,
    val slug: String,
    val name: String,
)

@Serializable
data class FormCategoryRef(
    val slug: String,
    val name: String,
)

@Serializable
data class InboxListResponse(
    val ok: Boolean,
    val total: Int = 0,
    val offset: Int = 0,
    val limit: Int = 0,
    val items: List<InboxItem> = emptyList(),
)

@Serializable
data class InboxItem(
    val id: Int,
    @SerialName("reference_token") val referenceToken: String = "",
    @SerialName("workflow_state") val workflowState: String = "",
    @SerialName("workflow_state_label") val workflowStateLabel: String = "",
    val form: InboxFormRef,
    val submitter: String = "",
    @SerialName("submitted_at") val submittedAt: String = "",
    @SerialName("submitted_at_label") val submittedAtLabel: String = "",
    @SerialName("current_step_id") val currentStepId: Int? = null,
    @SerialName("current_step_label") val currentStepLabel: String = "",
    @SerialName("has_unread_thread") val hasUnreadThread: Boolean = false,
    @SerialName("can_act") val canAct: Boolean = false,
    @SerialName("manage_url") val manageUrl: String = "",
    @SerialName("role_labels") val roleLabels: List<String> = emptyList(),
)

@Serializable
data class SubmissionSearchResponse(
    val ok: Boolean,
    val total: Int = 0,
    val offset: Int = 0,
    val limit: Int = 0,
    val relation: String = "any",
    @SerialName("workflow_state") val workflowState: String = "",
    @SerialName("form_id") val formId: Int? = null,
    val q: String = "",
    @SerialName("form_options") val formOptions: List<SearchFormOption> = emptyList(),
    val items: List<InboxItem> = emptyList(),
)

@Serializable
data class SearchFormOption(
    val id: Int,
    val title: String,
    val slug: String = "",
    @SerialName("entity_name") val entityName: String = "",
)

@Serializable
data class InboxFormRef(
    val id: Int,
    val title: String,
    val slug: String,
    @SerialName("entity_slug") val entitySlug: String,
    @SerialName("entity_name") val entityName: String,
)

@Serializable
data class InboxDetailResponse(
    val ok: Boolean,
    val submission: InboxSubmissionDetail,
    val values: List<SubmissionFieldValue> = emptyList(),
    val events: List<SubmissionTimelineEvent> = emptyList(),
    val thread: SubmissionThreadBlock? = null,
    val documents: SubmissionDocumentsBlock? = null,
    val message: String? = null,
)

@Serializable
data class SubmissionDocumentsBlock(
    val merged: MergedDocumentRef? = null,
    val attachments: List<SubmissionDocumentAttachment> = emptyList(),
)

@Serializable
data class MergedDocumentRef(
    @SerialName("has_merge_output") val hasMergeOutput: Boolean = false,
    @SerialName("can_view_pdf_inline") val canViewPdfInline: Boolean = false,
    @SerialName("show_docx_download") val showDocxDownload: Boolean = false,
    @SerialName("show_odt_download") val showOdtDownload: Boolean = false,
    @SerialName("show_pdf_download") val showPdfDownload: Boolean = false,
    @SerialName("pdf_api_path") val pdfApiPath: String = "",
    @SerialName("docx_api_path") val docxApiPath: String = "",
    @SerialName("odt_api_path") val odtApiPath: String = "",
)

@Serializable
data class SubmissionDocumentAttachment(
    val id: Int,
    val title: String = "",
    val filename: String = "",
    @SerialName("is_pdf") val isPdf: Boolean = false,
    @SerialName("can_preview_pdf") val canPreviewPdf: Boolean = false,
    @SerialName("download_api_path") val downloadApiPath: String = "",
    @SerialName("pdf_api_path") val pdfApiPath: String = "",
)

@Serializable
data class SubmissionThreadBlock(
    val messages: List<ThreadMessage> = emptyList(),
    @SerialName("can_post") val canPost: Boolean = false,
    @SerialName("max_body_length") val maxBodyLength: Int = 4000,
)

@Serializable
data class ThreadMessage(
    val id: Int,
    val body: String,
    @SerialName("author_username") val authorUsername: String = "",
    @SerialName("author_display") val authorDisplay: String = "",
    @SerialName("created_at_label") val createdAtLabel: String = "",
    @SerialName("is_mine") val isMine: Boolean = false,
)

@Serializable
data class ThreadPostRequest(
    val body: String,
)

@Serializable
data class InboxSubmissionDetail(
    val id: Int,
    @SerialName("reference_token") val referenceToken: String = "",
    @SerialName("workflow_state") val workflowState: String = "",
    @SerialName("workflow_state_label") val workflowStateLabel: String = "",
    @SerialName("submitted_at") val submittedAt: String = "",
    @SerialName("submitted_at_label") val submittedAtLabel: String = "",
    @SerialName("updated_at") val updatedAt: String = "",
    @SerialName("updated_at_label") val updatedAtLabel: String = "",
    val submitter: String = "",
    @SerialName("submitter_email") val submitterEmail: String = "",
    @SerialName("current_step_id") val currentStepId: Int? = null,
    @SerialName("current_step_label") val currentStepLabel: String = "",
    @SerialName("can_act") val canAct: Boolean = false,
    @SerialName("acting_as_delegate") val actingAsDelegate: Boolean = false,
    @SerialName("reject_comment_required") val rejectCommentRequired: Boolean = true,
    val form: InboxFormRef,
    @SerialName("manage_url") val manageUrl: String = "",
)

@Serializable
data class SubmissionFieldValue(
    @SerialName("value_id") val valueId: Int = 0,
    @SerialName("field_name") val fieldName: String,
    @SerialName("field_label") val fieldLabel: String,
    @SerialName("field_type") val fieldType: String,
    @SerialName("display_value") val displayValue: String,
    val required: Boolean = false,
    val attachment: FieldAttachmentRef? = null,
)

@Serializable
data class FieldAttachmentRef(
    val filename: String,
    @SerialName("download_url") val downloadUrl: String,
    @SerialName("api_path") val apiPath: String = "",
)

@Serializable
data class SubmissionTimelineEvent(
    val id: Int,
    val kind: String,
    @SerialName("kind_label") val kindLabel: String,
    val message: String = "",
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("created_at_label") val createdAtLabel: String = "",
    @SerialName("step_label") val stepLabel: String = "",
    val author: String = "",
)

@Serializable
data class WorkflowActionRequest(
    val decision: String,
    val comment: String? = null,
    @SerialName("workflow_action_anchor") val workflowActionAnchor: Int? = null,
)

@Serializable
data class FormSchemaResponse(
    val ok: Boolean,
    val form: PublishedFormItem,
    val status: String = "open",
    @SerialName("status_message") val statusMessage: String = "",
    val sections: List<FormSectionSchema> = emptyList(),
    val fields: List<FormFieldSchema> = emptyList(),
    val initial: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    @SerialName("visibility_rules") val visibilityRules: List<FormVisibilityRule> = emptyList(),
    val related: RelatedFormContext? = null,
)

@Serializable
data class RelatedFormContext(
    @SerialName("access_token") val accessToken: String,
    @SerialName("parent_form_title") val parentFormTitle: String = "",
    @SerialName("parent_reference_token") val parentReferenceToken: String = "",
)

@Serializable
data class PendingRelatedResponse(
    val ok: Boolean,
    val total: Int = 0,
    val items: List<PendingRelatedItem> = emptyList(),
)

@Serializable
data class PendingRelatedItem(
    @SerialName("access_token") val accessToken: String,
    @SerialName("invited_at_label") val invitedAtLabel: String = "",
    @SerialName("child_form") val childForm: PendingRelatedFormRef,
    @SerialName("parent_submission") val parentSubmission: PendingRelatedParentRef,
)

@Serializable
data class PendingRelatedFormRef(
    val id: Int,
    val title: String,
    val slug: String = "",
    @SerialName("entity_slug") val entitySlug: String = "",
    @SerialName("entity_name") val entityName: String = "",
)

@Serializable
data class PendingRelatedParentRef(
    val id: Int,
    @SerialName("reference_token") val referenceToken: String = "",
    @SerialName("form_title") val formTitle: String = "",
)

@Serializable
data class FormSectionSchema(
    val id: Int,
    val title: String,
    val description: String = "",
    @SerialName("starts_collapsed") val startsCollapsed: Boolean = false,
    val order: Int = 0,
)

@Serializable
data class FormFieldSchema(
    val id: Int,
    val key: String,
    val name: String,
    @SerialName("field_type") val fieldType: String,
    val label: String,
    @SerialName("help_text") val helpText: String = "",
    val placeholder: String = "",
    val required: Boolean = false,
    val choices: List<String> = emptyList(),
    @SerialName("options_layout") val optionsLayout: String = "vertical",
    val inline: Boolean = false,
    @SerialName("section_id") val sectionId: Int? = null,
    @SerialName("visibility_control_field_id") val visibilityControlFieldId: Int? = null,
    @SerialName("visibility_values") val visibilityValues: List<String> = emptyList(),
    @SerialName("max_length") val maxLength: Int? = null,
)

@Serializable
data class FormVisibilityRule(
    val target: String,
    val control: String,
    val values: List<String> = emptyList(),
)

@Serializable
data class FormSubmitResponse(
    val ok: Boolean,
    val submission: FormSubmitResult? = null,
    val message: String? = null,
    @SerialName("field_errors") val fieldErrors: Map<String, List<String>>? = null,
)

@Serializable
data class FormSubmitResult(
    val id: Int,
    @SerialName("reference_token") val referenceToken: String = "",
    @SerialName("detail_url") val detailUrl: String = "",
)
