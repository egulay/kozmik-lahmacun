import { browser } from '$app/environment';
import { derived, writable } from 'svelte/store';

export type Locale = 'tr' | 'en';

const messages = {
  tr: {
    brand: 'Kozmik Lahmacun',
    skip: 'Ana içeriğe geç',
    chat: 'Sohbet',
    you: 'Siz',
    executions: 'Çalışmalar',
    results: 'Sonuçlar',
    entities: 'Veri Varlıkları',
    administration: 'Yönetim',
    users: 'Kullanıcılar',
    email: 'E-posta',
    signIn: 'Giriş yap',
    username: 'Kullanıcı adı',
    password: 'Şifre',
    invalidCredentials: 'Kullanıcı adı veya şifre geçersiz.',
    signedOutTitle: 'Güvenli analiz alanınıza giriş yapın',
    signedOutBody: 'Raporlara, sohbetlere ve yönetilen veri varlıklarına erişmek için kurumsal hesabınızı kullanın.',
    signOut: 'Çıkış',
    loading: 'Yükleniyor…',
    retry: 'Yeniden dene',
    unavailable: 'Bu bilgi şu anda kullanılamıyor.',
    apiUnavailable: 'Backend servisine ulaşılamadı. Kalıcı verileriniz güvende; bağlantı kurulunca yeniden yükleyin.',
    theme: 'Temayı değiştir',
    language: 'Dil',
    light: 'Açık',
    dark: 'Koyu',
    menu: 'Menü',
    privacyTitle: 'Kurumsal verileriniz yapay zekâyla paylaşılmaz',
    privacyBody: 'Yapay zekâ yalnızca isteğinizi anlar ve güvenli ortamınıza iletir; verileriniz bu ortamda işlenir.',
    newThread: 'Yeni sohbet',
    noThreads: 'Henüz sohbet yok',
    createThread: 'Sohbet oluştur',
    renameThread: 'Sohbeti yeniden adlandır',
    saveThreadName: 'Adı kaydet',
    threadTitleTooLong: 'Sohbet başlığı en fazla 50 karakter olabilir.',
    deleteThread: 'Sohbeti sil',
    deleteThreadConfirm: '“{title}” sohbetini silmek istediğinizden emin misiniz?',
    threadTitle: 'Sohbet başlığı',
    messagePlaceholder: 'Raporunuzu veya sorunuzu doğal dille yazın…',
    send: 'Gönder',
    sending: 'Gönderiliyor…',
    thinking: 'Düşünüyor',
    selectThread: 'Devam etmek için bir sohbet seçin.',
    streamOffline: 'Canlı bağlantı kullanılamıyor',
    streamLive: 'Canlı bağlantı etkin',
    streamDescription: 'Kafka olay omurgasının çalıştığını ve veri alımı ile yürütme durumlarının servisler arasında gerçek zamanlı aktığını gösterir.',
    assistantFailed: 'Yanıt tamamlanamadı. Kayıtlı durumu yeniden yükleyebilirsiniz.',
    executionCreated: 'Çalışma oluşturuldu',
    goExecution: 'Çalışmayı görüntüle',
    executionListTitle: 'Çalışmalar',
    executionListBody: 'Rapor ve makine öğrenmesi çalışmalarınızın kalıcı durumu.',
    search: 'Ara',
    allStatuses: 'Tüm durumlar',
    status: 'Durum',
    type: 'Tür',
    entity: 'Varlık',
    requester: 'Talep eden',
    requestedAt: 'Talep zamanı',
    duration: 'Süre',
    noExecutions: 'Gösterilecek çalışma yok.',
    listNotSupported: 'Çalışma listesi API’si henüz Java tarafında etkin değil. Doğrudan çalışma bağlantıları kullanılabilir.',
    originalRequest: 'Özgün istek',
    plan: 'Onaylı plan',
    approvedMlOrder: 'Onaylı ML çalıştırma emri',
    approvedReportPlan: 'Onaylı rapor planı',
    planningFailed: 'İstek, güvenli bir çalıştırma emrine dönüştürülürken doğrulamadan geçemedi. Spark çalıştırılmadı.',
    orderPending: 'Çalıştırma emri hazırlanıyor',
    orderPendingBody: 'LLM çıktısı henüz doğrulanıp kalıcı onaylı JSON emri olarak kaydedilmedi.',
    orderUnavailable: 'Onaylı çalıştırma emri oluşturulamadı',
    orderUnavailableBody: 'Planlama doğrulaması başarısız olduğu için çalıştırma emri JSON’u kaydedilmedi ve Spark başlatılmadı.',
    timeline: 'İlerleme zaman çizelgesi',
    progress: 'İlerleme',
    resolvingData: 'Yönetilen veri çözümleniyor',
    tuningModels: 'Aday modeller deneniyor',
    governedDatasetNotFound: 'Bu varlık ve şema sürümü için tamamlanmış yönetilen veri bulunamadı.',
    governedDatasetBindingMismatch: 'Çözümlenen veri çalışma varlığı veya şema sürümüyle eşleşmiyor.',
    failureReason: 'Çalışma neden başarısız oldu?',
    sanitizedReason: 'Güvenli teknik neden',
    explanationFallback: 'LLM açıklaması üretilemedi; doğrulanmış güvenli açıklama gösteriliyor.',
    sparkJobFailed: 'Onaylı rapor planı Spark tarafından güvenli biçimde yürütülemedi.',
    mixedReportFailure: 'Rapor planı satır düzeyindeki satış alanlarını genel bir toplama işlemiyle birleştirdi. Toplama tamamlandığında satış tarihi artık sıralama için mevcut değildi ve çalışma güvenli biçimde durduruldu. Tekil kayıtları listelemek için toplama işlemi kullanmayın; toplamlar isteniyorsa alanları açıkça gruplandırın.',
    cancel: 'İptal et',
    cancelConfirm: 'Bu çalışmayı iptal etmek istediğinizden emin misiniz? Yalnızca bu çalışmaya ait Spark işi durdurulacak ve durum İPTAL EDİLDİ olarak saklanacaktır. Kayıtlar ve dosyalar, daha sonra ayrıca Sil işlemini seçene kadar korunur.',
    resultReady: 'Sonuç hazır',
    viewResult: 'Sonucu görüntüle',
    resultTitle: 'Çalıştırma sonucu',
    emptyExecutionResultTitle: 'Eşleşen veri bulunamadı',
    emptyExecutionResultBody: 'Bu çalıştırma herhangi bir veri döndürmedi. İsteği veya filtreleri gözden geçirip yeniden deneyebilirsiniz.',
    summary: 'Yönetici özeti',
    summaryPending: 'Özet hazırlanıyor. Analitik sonuç kullanılabilir.',
    summaryFailed: 'Özet üretilemedi; analitik sonuç kullanılmaya devam edebilir.',
    kpis: 'Temel göstergeler',
    charts: 'Grafikler',
    featureImportance: 'Değişkenlerin etkisi',
    importance: 'Etki düzeyi',
    selectedAlgorithm: 'Seçilen yöntem',
    bestValidationScore: 'En iyi doğrulama sonucu',
    tuningTrialsEvaluated: 'Değerlendirilen ayar denemeleri',
    candidateAlgorithmsEvaluated: 'Değerlendirilen aday yöntemler',
    chartRenderFailed: 'Grafik oluşturulamadı.',
    metrics: 'Model metrikleri',
    preview: 'Sınırlı önizleme',
    warnings: 'Uyarılar ve sınırlamalar',
    artifact: 'Tam sonuç',
    artifactGuidance: 'Tam sonuç Parquet biçiminde kontrollü nesne deposundadır.',
    reporterGuidance: 'Önizleme yönetişim sınırlarıyla kısıtlıdır. Tam veri doğrudan tarayıcıda gösterilmez.',
    rowsShown: '{shown} satır gösteriliyor; toplam {total} satır.',
    resultRowsPaged: 'Önizleme, sayfa başına {size} satır olacak şekilde gösterilmektedir.',
    resultRowsLimited: 'Tarayıcı önizlemesinde, Parquet biçimindeki tam sonuçta bulunan {total} satırın {shown} satırı yer almaktadır.',
    previewPageRows: 'Önizlemedeki {total} satırın {from}-{to} arası gösteriliyor.',
    chartAlternative: 'Grafiğin metinsel özeti',
    entitiesTitle: 'Veri Varlıkları',
    entitiesBody: 'Raporlama ve rol tabanlı makine öğrenmesi çalışmalarında kullanılabilen veri varlıkları.',
    schemaVersion: 'Şema sürümü',
    importStatus: 'İçe aktarma durumu',
    governedRows: 'Yönetilen satırlar',
    ingesting: 'İçe aktarılıyor',
    latestBatch: 'Son parti',
    lastCheckpoint: 'Son tamamlanan veri alımı',
    ingestionActivity: 'Veri alımı',
    reporting: 'Raporlama',
    ml: 'Makine öğrenmesi',
    report: 'Rapor',
    enabled: 'Etkin',
    disabled: 'Kapalı',
    columns: 'Sütunlar',
    totalFields: 'Toplam alan',
    dataType: 'Veri tipi',
    eligibility: 'Uygunluk',
    adminOnly: 'Bu alan yalnızca yöneticiler içindir.',
    save: 'Kaydet',
    saving: 'Kaydediliyor…',
    usersBody: 'Keycloak kullanıcı ve rollerini Java üzerinden yönetin.',
    addUser: 'Kullanıcı ekle',
    fullName: 'Ad soyad',
    fullNameMinLength: 'Ad soyad en az 2 karakter olmalıdır.',
    fullNameMaxLength: 'Ad soyad en fazla 100 karakter olabilir.',
    invalidEmail: 'Geçerli bir e-posta adresi girin.',
    emailMaxLength: 'E-posta en fazla 254 karakter olabilir.',
    singleRoleRequired: 'Yalnızca bir rol seçilmelidir.',
    invitationEmailHelp: 'Kaydedildiğinde kullanıcıya güvenli parola oluşturma bağlantısı gönderilir.',
    resetPassword: 'Parolayı sıfırla',
    userResetPasswordConfirm: 'Bu kullanıcıya yeni bir güvenli parola oluşturma bağlantısı gönderilsin mi?',
    changePassword: 'Parolayı değiştir',
    passwordEmailDescription: 'Güvenli parola değiştirme bağlantısı e-posta adresinize gönderilecek.',
    passwordEmailSent: 'Güvenli parola değiştirme bağlantısı e-posta adresinize gönderildi.',
    close: 'Kapat',
    sendEmail: 'E-posta gönder',
    editUser: 'Kullanıcıyı düzenle',
    suspendUser: 'Kullanıcıyı askıya al',
    resumeUser: 'Kullanıcıyı etkinleştir',
    deleteUser: 'Kullanıcıyı sil',
    cannotDeleteOwnUser: 'Kendi hesabınızı silemezsiniz',
    cannotSuspendOwnUser: 'Kendi hesabınızı askıya alamazsınız',
    userDeleteConfirm: 'Bu kullanıcı Keycloak’tan silinecek ve yerel kaydı geçmişi korumak için anonimleştirilecektir. Devam edilsin mi?',
    userSuspendConfirm: 'Bu kullanıcı oturum açamayacak. Kullanıcı askıya alınsın mı?',
    userResumeConfirm: 'Bu kullanıcının oturum açma erişimi yeniden etkinleştirilsin mi?',
    userOperationPending: 'Kimlik sistemi değişikliği güvenli yeniden deneme için sıraya alındı.',
    actions: 'İşlemler',
    role: 'Rol',
    services: 'Hizmetler',
    available: 'Kullanılabilir',
    degraded: 'Kısıtlı',
    unavailableState: 'Kullanılamıyor',
    unknown: 'Bilinmiyor',
    refresh: 'Yenile',
    back: 'Geri',
    details: 'Ayrıntılar',
    noData: 'Veri yok',
    liveRegion: 'Durum güncellemesi',
    forbidden: 'Bu alan için yetkiniz yok.',
    technicalDetails: 'Teknik ayrıntılar',
    copyJson: 'JSON’u kopyala',
    copied: 'Kopyalandı',
    exportPdf: 'PDF olarak dışa aktar',
    preparingPdf: 'PDF hazırlanıyor',
    governedAnalytics: 'Yönetilen analitik',
    featureUnavailable: 'Bu işlem için Java API desteği bekleniyor.'
    ,openResults: 'Açık sonuçlar'
    ,openExecutions: 'Açık sekmeler'
    ,closeTab: 'Sekmeyi kapat'
    ,requestedAnalysis: 'İstenen analiz'
    ,modelUsed: 'Seçilen yaklaşım'
    ,reliability: 'Güvenilirlik ve doğruluk'
    ,howProduced: 'Nasıl üretildi?'
    ,executionId: 'Çalıştırma ID'
    ,entityId: 'Veri varlığı ID'
    ,whatIfAnalysis: 'Senaryo karşılaştırması'
    ,whatIfNotCausal: 'Senaryo sonuçları koşullu tahminlerdir; nedensel etki veya garanti göstermez.'
    ,page: 'Sayfa'
    ,totalRows: 'Toplam kayıt'
    ,rowsPerPage: 'Sayfa başına'
    ,previousPage: 'Önceki sayfa'
    ,nextPage: 'Sonraki sayfa'
    ,previewLimited: 'Sistem en fazla 100 önizleme satırı saklayabilir. Bu sonuçta {total} önizleme satırı bulunur ve sayfa başına en fazla {size} satır gösterilir.'
    ,recentThreads: 'Son sohbetler'
    ,recentWork: 'Raporlar ve modeller'
    ,registeredEntities: 'Kullanılabilir veri varlıkları'
    ,registeredSchemas: 'Analize hazır veri varlıkları'
    ,delete: 'Sil'
    ,deleting: 'Siliniyor…'
    ,deleteExecution: 'Çalışmayı sil'
    ,deleteExecutionTitle: 'Emin misiniz?'
    ,deleteExecutionBody: 'Bu çalışma ve ilişkili sonucu kalıcı olarak silmek üzeresiniz. Çalışma geçmişi, sonuç metaverisi ve MinIO üzerindeki Parquet/model dosyaları silinir. Bu işlem geri alınamaz.'
    ,deleteExecutionFailed: 'Çalışma güvenli biçimde silinemedi. Kalıcı kayıtları korundu; yeniden deneyin.'
    ,keepExecution: 'Vazgeç'
  },
  en: {
    brand: 'Kozmik Lahmacun',
    skip: 'Skip to main content',
    chat: 'Chat',
    you: 'You',
    executions: 'Executions',
    results: 'Results',
    entities: 'Data Entities',
    administration: 'Administration',
    users: 'Users',
    email: 'Email',
    signIn: 'Sign in',
    username: 'Username',
    password: 'Password',
    invalidCredentials: 'The username or password is invalid.',
    signedOutTitle: 'Sign in to your secure analytics workspace',
    signedOutBody: 'Use your organization account to access reports, conversations, and governed data entities.',
    signOut: 'Sign out',
    loading: 'Loading…',
    thinking: 'Thinking',
    retry: 'Try again',
    unavailable: 'This information is currently unavailable.',
    apiUnavailable: 'The Backend service is unreachable. Your durable data is safe; reload when the connection returns.',
    theme: 'Change theme',
    language: 'Language',
    light: 'Light',
    dark: 'Dark',
    menu: 'Menu',
    privacyTitle: 'Your corporate data is not shared with AI',
    privacyBody: 'AI only understands your request and sends it to your secure environment, where your data is processed.',
    newThread: 'New chat',
    deleteThread: 'Delete chat',
    deleteThreadConfirm: 'Are you sure you want to delete “{title}”?',
    noThreads: 'No conversations yet',
    createThread: 'Create conversation',
    renameThread: 'Rename chat',
    saveThreadName: 'Save name',
    threadTitleTooLong: 'Conversation title can contain at most 50 characters.',
    threadTitle: 'Conversation title',
    messagePlaceholder: 'Describe a report or ask a question in natural language…',
    send: 'Send',
    sending: 'Sending…',
    selectThread: 'Select a conversation to continue.',
    streamOffline: 'Live connection unavailable',
    streamLive: 'Live connection active',
    streamDescription: 'Shows that the Kafka event backbone is available and ingestion and execution status events can flow between services in real time.',
    assistantFailed: 'The response could not be completed. You can reload its persisted state.',
    executionCreated: 'Execution created',
    goExecution: 'View execution',
    executionListTitle: 'Executions',
    executionListBody: 'Durable state for your report and machine-learning work.',
    search: 'Search',
    allStatuses: 'All statuses',
    status: 'Status',
    type: 'Type',
    entity: 'Entity',
    requester: 'Requester',
    requestedAt: 'Requested',
    duration: 'Duration',
    noExecutions: 'No executions to show.',
    listNotSupported: 'The execution list API is not enabled in Java yet. Direct execution links remain available.',
    originalRequest: 'Original request',
    plan: 'Approved plan',
    approvedMlOrder: 'Approved ML execution order',
    approvedReportPlan: 'Approved report plan',
    planningFailed: 'The request could not be converted into a valid governed execution order. Spark was not started.',
    orderPending: 'Execution order is being prepared',
    orderPendingBody: 'The LLM output has not yet been validated and persisted as the approved JSON order.',
    orderUnavailable: 'No approved execution order was created',
    orderUnavailableBody: 'Planning validation failed, so no execution-order JSON was persisted and Spark was not started.',
    timeline: 'Progress timeline',
    progress: 'Progress',
    resolvingData: 'Resolving governed data',
    tuningModels: 'Evaluating candidate models',
    governedDatasetNotFound: 'No completed governed dataset exists for this entity and schema version.',
    governedDatasetBindingMismatch: 'The resolved dataset does not match the execution entity or schema version.',
    failureReason: 'Why did this execution fail?',
    sanitizedReason: 'Sanitized technical reason',
    explanationFallback: 'The LLM explanation was unavailable; the verified safe fallback is shown.',
    sparkJobFailed: 'Spark could not safely execute the approved report plan.',
    mixedReportFailure: 'The report plan combined row-level sales fields with an overall aggregation. After aggregation, the sale date was no longer available for sorting, so execution was stopped safely. To list individual records, do not use an aggregation; to request totals, explicitly group the fields.',
    cancel: 'Cancel',
    cancelConfirm: 'Are you sure you want to cancel this execution? Only this execution’s Spark job will be stopped and its status will be retained as CANCELLED. Records and files remain available until you explicitly choose Delete later.',
    resultReady: 'Result ready',
    viewResult: 'View result',
    resultTitle: 'Execution Result',
    emptyExecutionResultTitle: 'No matching data was found',
    emptyExecutionResultBody: 'This execution returned no data. Review the request or its filters and try again.',
    summary: 'Management summary',
    summaryPending: 'The summary is being prepared. The analytical result is available.',
    summaryFailed: 'Summary generation failed; the analytical result remains usable.',
    kpis: 'Key indicators',
    charts: 'Charts',
    featureImportance: 'Feature importance',
    importance: 'Importance',
    selectedAlgorithm: 'Selected method',
    bestValidationScore: 'Best validation score',
    tuningTrialsEvaluated: 'Tuning trials evaluated',
    candidateAlgorithmsEvaluated: 'Candidate methods evaluated',
    chartRenderFailed: 'The chart could not be rendered.',
    metrics: 'Model metrics',
    preview: 'Bounded preview',
    warnings: 'Warnings and limitations',
    artifact: 'Full result',
    artifactGuidance: 'The full result is stored as Parquet in the governed object store.',
    reporterGuidance: 'The preview is bounded by governance policy. Full data is not rendered directly in the browser.',
    rowsShown: 'Showing {shown} rows out of {total}.',
    resultRowsPaged: 'The preview is displayed in pages of {size} rows.',
    resultRowsLimited: 'The browser preview contains {shown} of the {total} rows stored in the complete Parquet result.',
    previewPageRows: 'Showing rows {from}-{to} of {total} preview rows.',
    chartAlternative: 'Text summary of chart',
    entitiesTitle: 'Data Entities',
    entitiesBody: 'Data entities available for reporting and role-based machine learning executions.',
    schemaVersion: 'Schema version',
    importStatus: 'Import status',
    governedRows: 'Governed rows',
    ingesting: 'Ingesting',
    latestBatch: 'Latest batch',
    lastCheckpoint: 'Last completed ingestion',
    ingestionActivity: 'Ingestion',
    reporting: 'Reporting',
    ml: 'Machine learning',
    report: 'Report',
    enabled: 'Enabled',
    disabled: 'Disabled',
    columns: 'Columns',
    totalFields: 'Total fields',
    dataType: 'Data type',
    eligibility: 'Eligibility',
    adminOnly: 'This area is for administrators only.',
    save: 'Save',
    saving: 'Saving…',
    usersBody: 'Manage Keycloak users and roles through Java.',
    addUser: 'Add user',
    fullName: 'Full name',
    fullNameMinLength: 'Full name must contain at least 2 characters.',
    fullNameMaxLength: 'Full name cannot exceed 100 characters.',
    invalidEmail: 'Enter a valid email address.',
    emailMaxLength: 'Email cannot exceed 254 characters.',
    singleRoleRequired: 'Exactly one role must be selected.',
    invitationEmailHelp: 'Saving sends the user a secure link to create their password.',
    resetPassword: 'Reset password',
    userResetPasswordConfirm: 'Send this user a new secure password-creation link?',
    changePassword: 'Change password',
    passwordEmailDescription: 'A secure password-change link will be sent to your email address.',
    passwordEmailSent: 'A secure password-change link was sent to your email address.',
    close: 'Close',
    sendEmail: 'Send email',
    editUser: 'Edit user',
    suspendUser: 'Suspend user',
    resumeUser: 'Activate user',
    deleteUser: 'Delete user',
    cannotDeleteOwnUser: 'You cannot delete your own account',
    cannotSuspendOwnUser: 'You cannot suspend your own account',
    userDeleteConfirm: 'This user will be deleted from Keycloak and the local reference anonymized to preserve history. Continue?',
    userSuspendConfirm: 'This user will no longer be able to sign in. Suspend the user?',
    userResumeConfirm: 'Restore this user’s sign-in access?',
    userOperationPending: 'The identity change was queued for safe retry.',
    actions: 'Actions',
    role: 'Role',
    services: 'Services',
    available: 'Available',
    degraded: 'Degraded',
    unavailableState: 'Unavailable',
    unknown: 'Unknown',
    refresh: 'Refresh',
    back: 'Back',
    details: 'Details',
    noData: 'No data',
    liveRegion: 'Status update',
    forbidden: 'You do not have access to this area.',
    technicalDetails: 'Technical details',
    copyJson: 'Copy JSON',
    copied: 'Copied',
    exportPdf: 'Export as PDF',
    preparingPdf: 'Preparing PDF',
    governedAnalytics: 'Governed analytics',
    featureUnavailable: 'Java API support for this operation is pending.'
    ,openResults: 'Open results'
    ,openExecutions: 'Open tabs'
    ,closeTab: 'Close tab'
    ,requestedAnalysis: 'Requested analysis'
    ,modelUsed: 'Selected approach'
    ,reliability: 'Reliability and accuracy'
    ,howProduced: 'How was this produced?'
    ,executionId: 'Execution ID'
    ,entityId: 'Entity ID'
    ,whatIfAnalysis: 'What-if scenario comparison'
    ,whatIfNotCausal: 'Scenario results are conditional predictions; they do not establish causal effects or guarantees.'
    ,page: 'Page'
    ,totalRows: 'Total records'
    ,rowsPerPage: 'Rows per page'
    ,previousPage: 'Previous page'
    ,nextPage: 'Next page'
    ,previewLimited: 'The system can retain up to 100 preview rows. This result contains {total} preview rows, displayed in pages of up to {size}.'
    ,recentThreads: 'Recent conversations'
    ,recentWork: 'Reports and models'
    ,registeredEntities: 'Available data entities'
    ,delete: 'Delete'
    ,deleting: 'Deleting…'
    ,deleteExecution: 'Delete execution'
    ,deleteExecutionTitle: 'Are you sure?'
    ,deleteExecutionBody: 'You are about to permanently delete this execution and its associated result. Its execution history, result metadata, and Parquet/model objects in MinIO will be removed. This action cannot be undone.'
    ,deleteExecutionFailed: 'The execution could not be deleted safely. Its durable records were retained; please try again.'
    ,keepExecution: 'Cancel'
    ,registeredSchemas: 'Data entities ready for analysis'
  }
} as const;

export type TranslationKey = keyof typeof messages.tr;
const hasLocalStorage = browser && typeof globalThis.localStorage !== 'undefined';
const loginLocale = browser
  ? document.cookie
      .split('; ')
      .find((cookie) => cookie.startsWith('kozmik-login-locale='))
      ?.split('=')[1]
  : undefined;
const storedLocale = hasLocalStorage
  ? globalThis.localStorage.getItem('kozmik-locale')
  : undefined;
const initial: Locale = loginLocale === 'tr' || loginLocale === 'en'
  ? loginLocale
  : storedLocale === 'en'
    ? 'en'
    : 'tr';
if (hasLocalStorage && (loginLocale === 'tr' || loginLocale === 'en')) {
  globalThis.localStorage.setItem('kozmik-locale', loginLocale);
  document.cookie = 'kozmik-login-locale=; Max-Age=0; Path=/; SameSite=Lax';
}
export const locale = writable<Locale>(initial);
export const t = derived(locale, ($locale) => (key: TranslationKey, vars?: Record<string, unknown>) => {
  let value: string = messages[$locale][key];
  for (const [name, replacement] of Object.entries(vars ?? {})) {
    value = value.replace(`{${name}}`, String(replacement));
  }
  return value;
});

const statusMessages: Record<Locale, Record<string, string>> = {
  tr: {
    ACTIVE: 'Aktif',
    AVAILABLE: 'Kullanılabilir',
    CANCELLED: 'İptal edildi',
    COMPLETED: 'Tamamlandı',
    DEGRADED: 'Kısıtlı',
    DELETED: 'Silindi',
    DOWN: 'Çalışmıyor',
    FAILED: 'Başarısız',
    INGESTING: 'İçe aktarılıyor',
    PENDING: 'Bekliyor',
    PLANNING: 'Planlanıyor',
    PROCESSING: 'İşleniyor',
    QUEUED: 'Sırada',
    RECEIVED: 'Alındı',
    REGISTERED: 'Kayıtlı',
    RETRY_PENDING: 'Yeniden deneme bekliyor',
    RUNNING: 'Çalışıyor',
    STARTED: 'Başlatıldı',
    SUCCEEDED: 'Başarılı',
    SUSPENDED: 'Askıya alındı',
    TIMED_OUT: 'Zaman aşımına uğradı',
    TRAINING: 'Eğitiliyor',
    UNAVAILABLE: 'Kullanılamıyor',
    UNKNOWN: 'Bilinmiyor',
    UP: 'Çalışıyor',
    VALIDATED: 'Doğrulandı'
  },
  en: {
    ACTIVE: 'Active',
    AVAILABLE: 'Available',
    CANCELLED: 'Cancelled',
    COMPLETED: 'Completed',
    DEGRADED: 'Degraded',
    DELETED: 'Deleted',
    DOWN: 'Down',
    FAILED: 'Failed',
    INGESTING: 'Ingesting',
    PENDING: 'Pending',
    PLANNING: 'Planning',
    PROCESSING: 'Processing',
    QUEUED: 'Queued',
    RECEIVED: 'Received',
    REGISTERED: 'Registered',
    RETRY_PENDING: 'Retry pending',
    RUNNING: 'Running',
    STARTED: 'Started',
    SUCCEEDED: 'Succeeded',
    SUSPENDED: 'Suspended',
    TIMED_OUT: 'Timed out',
    TRAINING: 'Training',
    UNAVAILABLE: 'Unavailable',
    UNKNOWN: 'Unknown',
    UP: 'Up',
    VALIDATED: 'Validated'
  }
};

export function statusLabel(status: string, selectedLocale: Locale): string {
  const normalized = status.trim().toUpperCase();
  return statusMessages[selectedLocale][normalized]
    ?? normalized.toLowerCase().replaceAll('_', ' ').replace(/^\p{L}/u, (letter) => letter.toUpperCase());
}

export function setLocale(value: Locale) {
  locale.set(value);
  if (hasLocalStorage) {
    globalThis.localStorage.setItem('kozmik-locale', value);
    document.documentElement.lang = value;
  }
}
