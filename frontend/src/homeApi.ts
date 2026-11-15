import { api, call } from './api';
import { encodeHomeTarget } from './homeNavigation';
import type { HomeActivity, HomeAgent, HomeFeedEvent, HomeFilters, HomeOverview, HomePage,
  HomePageQuery, HomeResolvedTarget, HomeResult, HomeTarget } from './homeTypes';
import type { ExternalObservation } from './observationTypes';
import type { AttentionPage, AttentionPageQuery } from './attentionTypes';

export interface HomeApi {
  overview(filters: HomeFilters, signal?: AbortSignal): Promise<HomeOverview>;
  work(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeActivity>>;
  results(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeResult>>;
  activity(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeFeedEvent>>;
  agents(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeAgent>>;
  external(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<ExternalObservation>>;
  attention(query: AttentionPageQuery, signal?: AbortSignal): Promise<AttentionPage>;
  target(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget>;
  resolveTarget(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget>;
}
function queryString(query: HomePageQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '' && !(key === 'workspace_id' && value === 'all')) params.set(key, String(value));
  }
  return params.toString();
}
const get = <T>(path: string, signal?: AbortSignal) => call<T>(`/api/v1/home/${path}`, { signal, cache: 'no-store' });
function target(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget> {
  const params = new URLSearchParams({ target: encodeHomeTarget(target) });
  if (workspace && workspace !== 'all') params.set('workspace_id', workspace);
  return get<HomeResolvedTarget>(`target?${params}`, signal);
}
export const homeApi: HomeApi = {
  overview: (filters, signal) => get<HomeOverview>(`overview?${queryString(filters)}`, signal),
  work: (query, signal) => get<HomePage<HomeActivity>>(`work?${queryString(query)}`, signal),
  results: (query, signal) => get<HomePage<HomeResult>>(`results?${queryString(query)}`, signal),
  activity: (query, signal) => get<HomePage<HomeFeedEvent>>(`activity?${queryString(query)}`, signal),
  agents: (query, signal) => get<HomePage<HomeAgent>>(`agents?${queryString(query)}`, signal),
  external: (query, signal) => get<HomePage<ExternalObservation>>(`external?${queryString(query)}`, signal),
  attention: (query, signal) => api.attention(query, signal),
  target, resolveTarget: target,
};
