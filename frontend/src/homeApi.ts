import { call } from './api';
import { encodeHomeTarget } from './homeNavigation';
import type { HomeActivity, HomeAgent, HomeFeedEvent, HomeFilters, HomeOverview, HomePage,
  HomePageQuery, HomeResolvedTarget, HomeResult, HomeTarget, HomeEntryFilters, HomeEntryQuery, HomeEntryPage,
  HomeEntryGroup, HomeEntry, HomeSessionRef,HomeBoard,HomeBoardPage,HomeBoardColumn,HomeBoardQuery,
  HomeHarnessBoard,HomeHarnessBoardPage,HomeHarnessChildrenPage,HomeHarnessRequestsPage,HomeHarnessSessionsPage } from './homeTypes';
import type { ExternalObservation } from './observationTypes';
import type { AttentionOccurrence } from './attentionTypes';

export interface HomeApi {
  overview(filters: HomeFilters, signal?: AbortSignal): Promise<HomeOverview>;
  work(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeActivity>>;
  results(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeResult>>;
  activity(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeFeedEvent>>;
  agents(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<HomeAgent>>;
  external(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<ExternalObservation>>;
  attention(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<AttentionOccurrence>>;
  server_attention(query: HomePageQuery, signal?: AbortSignal): Promise<HomePage<AttentionOccurrence>>;
  entries(query:HomeEntryFilters & {limit?:number;preview?:number;cursor?:string},signal?:AbortSignal):Promise<HomeEntryPage<HomeEntryGroup>>;
  entryChildren(groupId:string,query:HomeEntryQuery,signal?:AbortSignal):Promise<HomeEntryPage<HomeEntry>>;
  entrySessions(groupId:string,entryId:string,query:HomeEntryQuery,signal?:AbortSignal):Promise<HomeEntryPage<HomeSessionRef>>;
  entryAttention(groupId:string,entryId:string,query:HomeEntryQuery,signal?:AbortSignal):Promise<HomeEntryPage<AttentionOccurrence>>;
  entryResults(groupId:string,entryId:string,query:HomeEntryQuery,signal?:AbortSignal):Promise<HomeEntryPage<HomeResult>>;
  board(query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeBoard>;
  boardColumn(column:HomeBoardColumn,query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeBoardPage>;
  harnessBoard(query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessBoard>;
  harnessBoardColumn(column:HomeBoardColumn,query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessBoardPage>;
  harnessChildren(cardId:string,query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessChildrenPage>;
  harnessUnlinked(query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessChildrenPage>;
  harnessRequests?(cardId:string,query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessRequestsPage>;
  harnessSessions?(cardId:string,query:HomeBoardQuery,signal?:AbortSignal):Promise<HomeHarnessSessionsPage>;
  target(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget>;
  resolveTarget(target: HomeTarget, workspace: string | null, signal?: AbortSignal): Promise<HomeResolvedTarget>;
}
function queryString(query: HomePageQuery | HomeEntryQuery): string {
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
  attention: (query, signal) => get<HomePage<AttentionOccurrence>>(`attention?${queryString(query)}`, signal),
  server_attention: (query, signal) => get<HomePage<AttentionOccurrence>>(`server-attention?${queryString(query)}`, signal),
  entries:(query,signal)=>get<HomeEntryPage<HomeEntryGroup>>(`entries?${queryString(query)}`,signal),
  entryChildren:(group,query,signal)=>get<HomeEntryPage<HomeEntry>>(`entries/${encodeURIComponent(group)}/children?${queryString(query)}`,signal),
  entrySessions:(group,entry,query,signal)=>get<HomeEntryPage<HomeSessionRef>>(`entries/${encodeURIComponent(group)}/children/${encodeURIComponent(entry)}/sessions?${queryString(query)}`,signal),
  entryAttention:(group,entry,query,signal)=>get<HomeEntryPage<AttentionOccurrence>>(`entries/${encodeURIComponent(group)}/children/${encodeURIComponent(entry)}/attention?${queryString(query)}`,signal),
  entryResults:(group,entry,query,signal)=>get<HomeEntryPage<HomeResult>>(`entries/${encodeURIComponent(group)}/children/${encodeURIComponent(entry)}/results?${queryString(query)}`,signal),
  board:(query,signal)=>get<HomeBoard>(`board?${queryString(query)}`,signal),
  boardColumn:(column,query,signal)=>get<HomeBoardPage>(`board/${encodeURIComponent(column)}?${queryString(query)}`,signal),
  harnessBoard:(query,signal)=>get<HomeHarnessBoard>(`harness-board?${queryString(query)}`,signal),
  harnessBoardColumn:(column,query,signal)=>get<HomeHarnessBoardPage>(`harness-board/${encodeURIComponent(column)}?${queryString(query)}`,signal),
  harnessChildren:(card,query,signal)=>get<HomeHarnessChildrenPage>(`harness-board/cards/${encodeURIComponent(card)}/children?${queryString(query)}`,signal),
  harnessUnlinked:(query,signal)=>get<HomeHarnessChildrenPage>(`harness-board/unlinked?${queryString(query)}`,signal),
  harnessRequests:(card,query,signal)=>get<HomeHarnessRequestsPage>(`harness-board/cards/${encodeURIComponent(card)}/requests?${queryString(query)}`,signal),
  harnessSessions:(card,query,signal)=>get<HomeHarnessSessionsPage>(`harness-board/cards/${encodeURIComponent(card)}/sessions?${queryString(query)}`,signal),
  target, resolveTarget: target,
};
