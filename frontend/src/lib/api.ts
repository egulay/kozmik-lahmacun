import type {
  ChatMessage,
  ChatThread,
  ColumnDefinition,
  CurrentUser,
  EntitySchema,
  EntitySummary,
  Execution,
  ExecutionResult,
  ManagedUser,
  PageResponse,
  Role
} from './types';
import { get } from 'svelte/store';
import { locale } from './i18n';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string
  ) {
    super(message);
  }
}

interface CsrfTokenResponse {
  headerName: string;
  parameterName: string;
  token: string;
}

let csrfToken: CsrfTokenResponse | undefined;
let csrfRequest: Promise<CsrfTokenResponse> | undefined;

function isMutation(method?: string) {
  return !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes((method ?? 'GET').toUpperCase());
}

async function getCsrfToken(): Promise<CsrfTokenResponse> {
  if (csrfToken) return csrfToken;
  csrfRequest ??= fetch('/api/auth/csrf', {
    credentials: 'include',
    headers: { Accept: 'application/json' }
  }).then(async (response) => {
    if (!response.ok) throw new ApiError(response.status, 'Unable to initialize request protection');
    csrfToken = (await response.json()) as CsrfTokenResponse;
    return csrfToken;
  }).finally(() => {
    csrfRequest = undefined;
  });
  return csrfRequest;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const csrf = isMutation(init.method) ? await getCsrfToken() : undefined;
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      'Accept-Language': get(locale),
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(csrf ? { [csrf.headerName]: csrf.token } : {}),
      ...init.headers
    }
  });
  if (!response.ok) {
    let message = response.statusText;
    let code: string | undefined;
    try {
      const body = await response.json();
      message = body.message ?? body.detail ?? message;
      code = body.code;
    } catch {
      // Non-JSON infrastructure errors remain safely summarized.
    }
    throw new ApiError(response.status, message, code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  initializeCsrf: () => getCsrfToken().then(() => undefined),
  beginLogin: () => window.location.assign('/oauth2/authorization/keycloak'),
  logout: async () => {
    const csrf = await getCsrfToken();
    const form = document.createElement('form');
    form.method = 'post';
    form.action = '/api/auth/logout';
    const token = document.createElement('input');
    token.type = 'hidden';
    token.name = csrf.parameterName;
    token.value = csrf.token;
    form.append(token);
    document.body.append(form);
    form.submit();
  },
  currentUser: () => request<CurrentUser>('/api/auth/me'),
  serviceStatuses: () =>
    request<{
      checkedAt: string;
      services: Array<{
        service: 'backend' | 'executor' | 'llm' | 'kafka';
        status: string;
        model: string | null;
        errorCode: string | null;
      }>;
    }>('/api/health/services'),
  threadPage: async (page = 0, size = 20): Promise<PageResponse<ChatThread>> => {
    const response = await request<{
      threads: ChatThread[];
      page: number;
      size: number;
      totalElements: number;
      totalPages: number;
      first: boolean;
      last: boolean;
    }>(`/api/chat/threads?page=${page}&size=${size}`);
    return { ...response, items: response.threads };
  },
  createThread: (title: string, language: string) =>
    request<ChatThread>('/api/chat/threads', {
      method: 'POST',
      body: JSON.stringify({ title, language })
    }),
  renameThread: (threadId: string, title: string) =>
    request<ChatThread>(`/api/chat/threads/${threadId}`, {
      method: 'PUT',
      body: JSON.stringify({ title })
    }),
  deleteThread: (threadId: string) =>
    request<void>(`/api/chat/threads/${threadId}`, { method: 'DELETE' }),
  messagePage: async (
    threadId: string,
    page = 0,
    size = 20
  ): Promise<PageResponse<ChatMessage>> => {
    const response = await request<{
      messages: ChatMessage[];
      page: number;
      size: number;
      totalElements: number;
      totalPages: number;
      first: boolean;
      last: boolean;
    }>(`/api/chat/threads/${threadId}/messages?page=${page}&size=${size}`);
    return { ...response, items: response.messages };
  },
  messages: async (threadId: string) =>
    (await api.messagePage(threadId, 0, 1)).items,
  postMessage: (threadId: string, content: string, language: string) =>
    request<{ userMessage: ChatMessage; assistantMessage: ChatMessage }>(
      `/api/chat/threads/${threadId}/messages`,
      { method: 'POST', body: JSON.stringify({ content, language }) }
    ),
  executionPage: async ({
    page = 0,
    size = 20,
    statuses = [],
    search = ''
  }: {
    page?: number;
    size?: number;
    statuses?: string[];
    search?: string;
  } = {}): Promise<PageResponse<Execution>> => {
    const query = new URLSearchParams({ page: String(page), size: String(size) });
    if (search.trim()) query.set('search', search.trim());
    statuses.forEach((status) => query.append('status', status));
    const response = await request<{
      executions: Execution[];
      page: number;
      size: number;
      totalElements: number;
      totalPages: number;
      first: boolean;
      last: boolean;
    }>(`/api/executions?${query}`);
    return { ...response, items: response.executions };
  },
  execution: (id: string) => request<Execution>(`/api/executions/${id}`),
  result: (id: string, page = 0, size = 20) =>
    request<ExecutionResult>(
      `/api/executions/${id}/result?page=${page}&size=${size}`
    ),
  cancelExecution: (id: string) =>
    request<void>(`/api/executions/${id}/cancel`, { method: 'POST' }),
  deleteExecution: (id: string) =>
    request<{ schemaVersion: string; executionId: string; status: 'COMPLETED' | 'PENDING' }>(
      `/api/executions/${id}`, { method: 'DELETE' }
    ),
  entityPage: async (page = 0, size = 20): Promise<PageResponse<EntitySummary>> => {
    const response = await request<{
      entities: EntitySummary[];
      page: number;
      size: number;
      totalElements: number;
      registeredStructureCount: number;
      totalPages: number;
      first: boolean;
      last: boolean;
    }>(`/api/entities?page=${page}&size=${size}`);
    return { ...response, items: response.entities };
  },
  entities: async () => (await api.entityPage(0, 100)).items,
  entity: (id: string) => request<EntitySummary>(`/api/entities/${id}`),
  entitySchema: (id: string) => request<EntitySchema>(`/api/entities/${id}/schema`),
  entityColumns: async (id: string, page = 0, size = 20) => {
    const response = await request<{
      columns: ColumnDefinition[];
      page: number;
      size: number;
      totalElements: number;
      totalPages: number;
      first: boolean;
      last: boolean;
    }>(
      `/api/entities/${id}/schema/columns?page=${page}&size=${size}`
    );
    return { ...response, items: response.columns };
  },
  adminUsers: async (page = 0, size = 20): Promise<PageResponse<ManagedUser>> => {
    const response = await request<{
      users: ManagedUser[]; page: number; size: number; totalElements: number;
      totalPages: number; first: boolean; last: boolean;
    }>(`/api/admin/users?page=${page}&size=${size}`);
    return { ...response, items: response.users };
  },
  createAdminUser: (value: {
    displayName: string; email: string;
    roles: Role[];
  }) => request<ManagedUser>('/api/admin/users', {
    method: 'POST', body: JSON.stringify(value)
  }),
  updateAdminUser: (id: string, value: Pick<ManagedUser, 'displayName' | 'email' | 'roles'>) =>
    request(`/api/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(value) }),
  suspendAdminUser: (id: string) =>
    request(`/api/admin/users/${id}/suspend`, { method: 'POST' }),
  resumeAdminUser: (id: string) =>
    request(`/api/admin/users/${id}/resume`, { method: 'POST' }),
  resetAdminUserPassword: (id: string) =>
    request<{ status: 'EMAIL_SENT' }>(`/api/admin/users/${id}/password-reset`, {
      method: 'POST'
    }),
  deleteAdminUser: (id: string) =>
    request(`/api/admin/users/${id}`, { method: 'DELETE' }),
  requestPasswordChange: () =>
    request<{ status: 'EMAIL_SENT' }>('/api/account/password-change', {
      method: 'POST'
    }),
};
