import SwiftUI

enum AppLanguage: String, CaseIterable, Identifiable {
    case en
    case ar

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .en: return "English"
        case .ar: return "العربية"
        }
    }

    var layoutDirection: LayoutDirection {
        self == .ar ? .rightToLeft : .leftToRight
    }

    var acceptLanguage: String { rawValue }

    static let storageKey = "app_language"

    /// Reads persisted UI language without MainActor (safe for `AuthAPI` and other background callers).
    static var currentAcceptLanguage: String {
        let raw = UserDefaults.standard.string(forKey: storageKey) ?? AppLanguage.en.rawValue
        return AppLanguage(rawValue: raw)?.acceptLanguage ?? AppLanguage.en.acceptLanguage
    }
}

enum L10n {
    enum Key: String {
        case appName
        case signInSubtitle
        case password
        case signIn
        case menu
        case done
        case studio
        case search
        case mySignatures
        case help
        case refresh
        case signOut
        case language
        case english
        case arabic
        case forms
        case inbox
        case signatures
        case request
        case back
        case backToForms
        case searchRequests
        case inboxOpen
        case noOpenForms
        case noOpenFormsDesc
        case noMatches
        case noMatchesDesc
        case searchForms
        case readMoreAboutForm
        case applyNow
        case registrationClosed
        case gallery
        case about
        case featuredVideo
        case openVideo
        case registrationInfo
        case registerBy
        case fee
        case capacity
        case schedule
        case starts
        case ends
        case whereSection
        case format
        case location
        case viewOnMap
        case getInTouch
        case contact
        case highlights
        case downloadBrochure
        case guidelines
        case clear
        case clearFilters
        case due
        case inboxEmpty
        case inboxEmptyDesc
        case actionNeeded
        case approve
        case reject
        case rejectionReason
        case delegateNotice
        case searchEmpty
        case searchEmptyDesc
        case submit
        case submitted
        case submittedDesc
        case viewSubmission
        case loadingForm
        case couldNotLoadForm
        case notAvailable
        case chooseFile
        case removeFile
        case organizationUsername
        case allOrgs
        case allCategories
        case notAvailableDesc
        case date
        case ok
        case cancel
        case formsToComplete
        case formsToCompleteDesc
        case noPendingRelated
        case mainForm
        case thread
        case threadMessages
        case addMessage
        case post
        case responses
        case timeline
        case requestSection
        case reference
        case status
        case submittedLabel
        case from
        case email
        case currentStep
        case organization
        case openAttachment
        case couldNotLoad
        case tryAgain
        case approved
        case rejected
        case saved
        case allRoles
        case roleApplicant
        case roleWorkflow
        case allStatus
        case statusInProgress
        case statusCompleted
        case statusRejected
        case allForms
        case searchInbox
        case unread
        case unreadMessages
        case confirmApproveTitle
        case confirmApproveMessage
        case confirmRejectTitle
        case resultsCount
        case biometricUnlock
        case unlockApp
        case unlockAppDesc
        case unlockWithBiometrics
        case biometricFailed
        case sessionExpiredTitle
        case sessionExpiredMessage
        case queuedOffline
        case offlineFilesNotQueued
        case pendingSync
        case mergedDocument
        case attachedDocuments
        case viewPdf
        case viewDocx
        case viewOdt
    }

    static func t(_ key: Key, lang: AppLanguage) -> String {
        strings[lang]?[key] ?? strings[.en]![key]!
    }

    private static let strings: [AppLanguage: [Key: String]] = [
        .en: [
            .appName: "MagicForms",
            .signInSubtitle: "Sign in with your organization account",
            .password: "Password",
            .signIn: "Sign in",
            .menu: "Menu",
            .done: "Done",
            .studio: "Studio",
            .search: "Search",
            .mySignatures: "My signatures",
            .help: "Help",
            .refresh: "Refresh",
            .signOut: "Sign out",
            .language: "Language",
            .english: "English",
            .arabic: "Arabic",
            .forms: "Forms",
            .inbox: "Inbox",
            .signatures: "Signatures",
            .request: "Request",
            .back: "Back",
            .backToForms: "Back to forms",
            .searchRequests: "Search requests",
            .inboxOpen: "Inbox, %d open requests",
            .noOpenForms: "No open forms",
            .noOpenFormsDesc: "Published forms for your organizations will appear here.",
            .noMatches: "No matches",
            .noMatchesDesc: "Try a different search or clear filters.",
            .searchForms: "Search forms",
            .readMoreAboutForm: "Read more about this form",
            .applyNow: "Apply now",
            .registrationClosed: "Registration is closed for this form.",
            .gallery: "Gallery",
            .about: "About",
            .featuredVideo: "Featured video",
            .openVideo: "Open video",
            .registrationInfo: "Registration",
            .registerBy: "Register by",
            .fee: "Fee",
            .capacity: "Capacity",
            .schedule: "Schedule",
            .starts: "Starts",
            .ends: "Ends",
            .whereSection: "Where",
            .format: "Format",
            .location: "Location",
            .viewOnMap: "View on map",
            .getInTouch: "Get in touch",
            .contact: "Contact",
            .highlights: "Highlights",
            .downloadBrochure: "Download brochure (PDF)",
            .guidelines: "Guidelines",
            .clear: "Clear",
            .clearFilters: "Clear filters",
            .due: "Due %@",
            .inboxEmpty: "Inbox empty",
            .inboxEmptyDesc: "Workflow requests assigned to you will appear here.",
            .actionNeeded: "Action needed",
            .approve: "Approve",
            .reject: "Reject",
            .rejectionReason: "Rejection reason (required)",
            .delegateNotice: "You are acting as a delegate on this step.",
            .searchEmpty: "No requests found",
            .searchEmptyDesc: "Submissions you submitted, were assigned, or worked on will appear here.",
            .submit: "Submit",
            .submitted: "Submitted",
            .submittedDesc: "Your response was recorded.",
            .viewSubmission: "View submission",
            .loadingForm: "Loading form…",
            .couldNotLoadForm: "Could not load form",
            .notAvailable: "Not available",
            .chooseFile: "Choose file",
            .removeFile: "Remove file",
            .organizationUsername: "Organization username",
            .allOrgs: "All orgs",
            .allCategories: "All categories",
            .notAvailableDesc: "This form cannot be submitted.",
            .date: "Date",
            .ok: "OK",
            .cancel: "Cancel",
            .formsToComplete: "Forms to complete",
            .formsToCompleteDesc: "Extra forms linked to submissions you started.",
            .noPendingRelated: "Nothing pending",
            .mainForm: "Main form",
            .thread: "Thread",
            .threadMessages: "Messages",
            .addMessage: "Add a message",
            .post: "Post",
            .responses: "Responses",
            .timeline: "Timeline",
            .requestSection: "Request",
            .reference: "Reference",
            .status: "Status",
            .submittedLabel: "Submitted",
            .from: "From",
            .email: "Email",
            .currentStep: "Current step",
            .organization: "Organization",
            .openAttachment: "Open attachment",
            .couldNotLoad: "Could not load",
            .tryAgain: "Try again.",
            .approved: "Approved.",
            .rejected: "Rejected.",
            .saved: "Saved.",
            .allRoles: "All roles",
            .roleApplicant: "Applicant",
            .roleWorkflow: "Workflow",
            .allStatus: "All status",
            .statusInProgress: "In progress",
            .statusCompleted: "Completed",
            .statusRejected: "Rejected",
            .allForms: "All forms",
            .searchInbox: "Search inbox",
            .unread: "Unread",
            .unreadMessages: "Unread messages",
            .confirmApproveTitle: "Approve request?",
            .confirmApproveMessage: "This will advance the workflow for this submission.",
            .confirmRejectTitle: "Reject request",
            .resultsCount: "%d results",
            .biometricUnlock: "Unlock with Face ID",
            .unlockApp: "Unlock MagicForms",
            .unlockAppDesc: "Use biometrics to open the app.",
            .unlockWithBiometrics: "Unlock",
            .biometricFailed: "Could not verify. Try again.",
            .sessionExpiredTitle: "Session expired",
            .sessionExpiredMessage: "Your session expired. Please sign in again.",
            .queuedOffline: "Saved offline. It will submit when you are back online.",
            .offlineFilesNotQueued: "Connect to the internet to submit forms with file uploads.",
            .pendingSync: "%d submission(s) waiting to sync",
            .mergedDocument: "Merged document",
            .attachedDocuments: "Attached documents",
            .viewPdf: "View PDF",
            .viewDocx: "View DOCX",
            .viewOdt: "View ODT",
        ],
        .ar: [
            .appName: "MagicForms",
            .signInSubtitle: "سجّل الدخول بحساب مؤسستك",
            .password: "كلمة المرور",
            .signIn: "تسجيل الدخول",
            .menu: "القائمة",
            .done: "تم",
            .studio: "الاستوديو",
            .search: "بحث",
            .mySignatures: "توقيعاتي",
            .help: "المساعدة",
            .refresh: "تحديث",
            .signOut: "تسجيل الخروج",
            .language: "اللغة",
            .english: "English",
            .arabic: "العربية",
            .forms: "النماذج",
            .inbox: "صندوق الوارد",
            .signatures: "التوقيعات",
            .request: "طلب",
            .back: "رجوع",
            .backToForms: "العودة إلى النماذج",
            .searchRequests: "بحث الطلبات",
            .inboxOpen: "صندوق الوارد، %d طلبات مفتوحة",
            .noOpenForms: "لا توجد نماذج مفتوحة",
            .noOpenFormsDesc: "ستظهر هنا النماذج المنشورة لمؤسساتك.",
            .noMatches: "لا توجد نتائج",
            .noMatchesDesc: "جرّب بحثًا آخر أو امسح عوامل التصفية.",
            .searchForms: "بحث في النماذج",
            .readMoreAboutForm: "اقرأ المزيد عن هذا النموذج",
            .applyNow: "قدّم الآن",
            .registrationClosed: "التسجيل مغلق لهذا النموذج.",
            .gallery: "معرض الصور",
            .about: "نبذة",
            .featuredVideo: "فيديو مميز",
            .openVideo: "فتح الفيديو",
            .registrationInfo: "التسجيل",
            .registerBy: "التسجيل قبل",
            .fee: "الرسوم",
            .capacity: "السعة",
            .schedule: "الجدول",
            .starts: "يبدأ",
            .ends: "ينتهي",
            .whereSection: "المكان",
            .format: "النوع",
            .location: "الموقع",
            .viewOnMap: "عرض على الخريطة",
            .getInTouch: "تواصل معنا",
            .contact: "جهة الاتصال",
            .highlights: "أبرز النقاط",
            .downloadBrochure: "تحميل الكتيب (PDF)",
            .guidelines: "الإرشادات",
            .clear: "مسح",
            .clearFilters: "مسح عوامل التصفية",
            .due: "الاستحقاق %@",
            .inboxEmpty: "صندوق الوارد فارغ",
            .inboxEmptyDesc: "ستظهر هنا طلبات سير العمل المسندة إليك.",
            .actionNeeded: "إجراء مطلوب",
            .approve: "موافقة",
            .reject: "رفض",
            .rejectionReason: "سبب الرفض (مطلوب)",
            .delegateNotice: "أنت تعمل كمفوّض في هذه الخطوة.",
            .searchEmpty: "لم يُعثر على طلبات",
            .searchEmptyDesc: "ستظهر هنا الطلبات التي قدّمتها أو سُندت إليك أو عملت عليها.",
            .submit: "إرسال",
            .submitted: "تم الإرسال",
            .submittedDesc: "تم تسجيل ردك.",
            .viewSubmission: "عرض الطلب",
            .loadingForm: "جاري تحميل النموذج…",
            .couldNotLoadForm: "تعذّر تحميل النموذج",
            .notAvailable: "غير متاح",
            .chooseFile: "اختيار ملف",
            .removeFile: "إزالة الملف",
            .organizationUsername: "اسم مستخدم المؤسسة",
            .allOrgs: "كل المؤسسات",
            .allCategories: "كل الفئات",
            .notAvailableDesc: "لا يمكن إرسال هذا النموذج.",
            .date: "التاريخ",
            .ok: "موافق",
            .cancel: "إلغاء",
            .formsToComplete: "نماذج لإكمالها",
            .formsToCompleteDesc: "نماذج إضافية مرتبطة بطلبات بدأتها.",
            .noPendingRelated: "لا يوجد شيء معلّق",
            .mainForm: "النموذج الرئيسي",
            .thread: "المحادثة",
            .threadMessages: "الرسائل",
            .addMessage: "أضف رسالة",
            .post: "إرسال",
            .responses: "الإجابات",
            .timeline: "الجدول الزمني",
            .requestSection: "الطلب",
            .reference: "المرجع",
            .status: "الحالة",
            .submittedLabel: "تاريخ الإرسال",
            .from: "من",
            .email: "البريد",
            .currentStep: "الخطوة الحالية",
            .organization: "المؤسسة",
            .openAttachment: "فتح المرفق",
            .couldNotLoad: "تعذّر التحميل",
            .tryAgain: "حاول مرة أخرى.",
            .approved: "تمت الموافقة.",
            .rejected: "تم الرفض.",
            .saved: "تم الحفظ.",
            .allRoles: "كل الأدوار",
            .roleApplicant: "مقدّم الطلب",
            .roleWorkflow: "سير العمل",
            .allStatus: "كل الحالات",
            .statusInProgress: "قيد التنفيذ",
            .statusCompleted: "مكتمل",
            .statusRejected: "مرفوض",
            .allForms: "كل النماذج",
            .searchInbox: "بحث في الوارد",
            .unread: "غير مقروء",
            .unreadMessages: "رسائل غير مقروءة",
            .confirmApproveTitle: "الموافقة على الطلب؟",
            .confirmApproveMessage: "سيُقدَّم سير العمل لهذا الطلب.",
            .confirmRejectTitle: "رفض الطلب",
            .resultsCount: "%d نتيجة",
            .biometricUnlock: "فتح بالبصمة / Face ID",
            .unlockApp: "فتح MagicForms",
            .unlockAppDesc: "استخدم البصمة لفتح التطبيق.",
            .unlockWithBiometrics: "فتح",
            .biometricFailed: "تعذّر التحقق. حاول مرة أخرى.",
            .sessionExpiredTitle: "انتهت الجلسة",
            .sessionExpiredMessage: "انتهت جلستك. يُرجى تسجيل الدخول مرة أخرى.",
            .queuedOffline: "تم الحفظ دون اتصال. سيُرسَل عند عودة الشبكة.",
            .offlineFilesNotQueued: "اتصل بالإنترنت لإرسال النماذج التي تتضمن ملفات.",
            .pendingSync: "%d إرسال بانتظار المزامنة",
            .mergedDocument: "المستند المدمج",
            .attachedDocuments: "المستندات المرفقة",
            .viewPdf: "عرض PDF",
            .viewDocx: "عرض DOCX",
            .viewOdt: "عرض ODT",
        ],
    ]
}

@MainActor
final class LanguageManager: ObservableObject {
    static let shared = LanguageManager()

    @Published private(set) var language: AppLanguage

    private init() {
        let raw = UserDefaults.standard.string(forKey: AppLanguage.storageKey) ?? AppLanguage.en.rawValue
        language = AppLanguage(rawValue: raw) ?? .en
    }

    func setLanguage(_ lang: AppLanguage) {
        guard language != lang else { return }
        language = lang
        UserDefaults.standard.set(lang.rawValue, forKey: AppLanguage.storageKey)
    }

    func t(_ key: L10n.Key) -> String {
        L10n.t(key, lang: language)
    }

    func t(_ key: L10n.Key, _ args: CVarArg...) -> String {
        let format = t(key)
        return String(format: format, locale: language == .ar ? Locale(identifier: "ar") : Locale(identifier: "en"), arguments: args)
    }
}
