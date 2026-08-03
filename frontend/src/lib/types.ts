export type Role = 'REPORTER' | 'SCIENTIST' | 'ADMIN';

export interface CurrentUser {
  userId: string;
  username: string;
  displayName: string;
  email: string;
  roles: Role[];
  workspaceGeneration: string;
}

export interface ChatThread {
  id: string;
  title: string;
  language: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  threadId: string;
  sequenceNumber: number;
  role: 'USER' | 'ASSISTANT' | 'SYSTEM';
  content: string;
  status: 'PENDING' | 'STREAMING' | 'COMPLETED' | 'FAILED';
  errorCode?: string | null;
  createdAt: string;
  completedAt?: string | null;
}

export interface EntitySummary {
  id: string;
  name: string;
  description: string;
  nameTr?: string | null;
  descriptionTr?: string | null;
  canonicalName?: string;
  status: string;
  schemaRegistered: boolean;
  latestImportStatus?: string | null;
  governedRowCount?: number | null;
  latestBatchRowCount?: number | null;
  lastCheckpointAt?: string | null;
}

export interface ColumnDefinition {
  id: string;
  columnName: string;
  businessName: string;
  dataType: string;
  description?: string;
  businessNameTr?: string | null;
  descriptionTr?: string | null;
}

export interface EntitySchema {
  entityId: string;
  createdAt: string;
  columns: ColumnDefinition[];
}

export interface StatusHistory {
  eventId: string;
  stage: string;
  status: string;
  progressPercent: number;
  messageCode: string;
  details?: unknown;
  occurredAt: string;
}

export interface Execution {
  id: string;
  executionType: string;
  status: string;
  entityId: string;
  entityName?: string;
  entityNameTr?: string | null;
  requester?: string;
  originalRequest?: string;
  requestedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  latestStage?: string | null;
  latestProgressPercent?: number | null;
  order?: Record<string, unknown>;
  history: StatusHistory[];
  failure?: ExecutionFailure | null;
}

export interface ExecutionFailure {
  schemaVersion: string;
  failureCode: string;
  failedStage: string;
  sanitizedTechnicalReason: string;
  userExplanation: string;
  explanationStatus: 'COMPLETED' | 'FAILED';
  retryable: boolean;
  language: 'tr' | 'en';
  createdAt: string;
}

export interface ResultArtifact {
  artifactId: string;
  format: string;
  bucket?: string;
  objectKey?: string;
  storageUri?: string;
}

export interface ExecutionResult {
  executionId: string;
  rowCount: number;
  preview: unknown;
  kpis: unknown;
  charts: unknown;
  warnings: unknown;
  artifact: ResultArtifact;
  guidanceKey: string;
  summaryStatus: string;
  resultSummary?: string | null;
  metrics?: unknown;
  previewPage: number;
  previewSize: number;
  previewTotalElements: number;
  previewTotalPages: number;
}

export interface PageResponse<T> {
  items: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
  first: boolean;
  last: boolean;
  registeredStructureCount?: number;
}

export interface ManagedUser {
  id: string;
  keycloakUserId: string;
  username: string;
  displayName: string;
  email: string;
  status: 'ACTIVE' | 'SUSPENDED';
  roles: Role[];
  updatedAt: string;
}
