import { writable } from 'svelte/store';
import type { CurrentUser, Role } from './types';

export const currentUser = writable<CurrentUser | null>(null);
export const sessionLoading = writable(true);

export function hasRole(user: CurrentUser | null, ...roles: string[]) {
  return Boolean(user?.roles.some((role) => roles.includes(role)));
}

export function primaryRole(user: CurrentUser | null): Role | null {
  if (user?.roles.includes('ADMIN')) return 'ADMIN';
  if (user?.roles.includes('SCIENTIST')) return 'SCIENTIST';
  if (user?.roles.includes('REPORTER')) return 'REPORTER';
  return null;
}
