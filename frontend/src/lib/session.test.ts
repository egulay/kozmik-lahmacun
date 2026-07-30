import { describe, expect, it } from 'vitest';
import { primaryRole } from './session';
import type { CurrentUser } from './types';

function user(roles: CurrentUser['roles']): CurrentUser {
  return {
    userId: '1',
    username: 'demo',
    displayName: 'Demo Admin',
    email: 'demo@example.test',
    roles
  };
}

describe('primaryRole', () => {
  it('does not present inherited Keycloak composite roles as assigned roles', () => {
    expect(primaryRole(user(['REPORTER', 'SCIENTIST', 'ADMIN']))).toBe('ADMIN');
  });

  it('uses the highest effective platform role', () => {
    expect(primaryRole(user(['REPORTER', 'SCIENTIST']))).toBe('SCIENTIST');
    expect(primaryRole(user(['REPORTER']))).toBe('REPORTER');
  });
});
