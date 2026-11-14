"""Reattach retained work observations without admitting or contacting anything."""
from pathlib import Path
from independent_journal import CanonicalIntentReader, CoreJournalReader, safe_path, require


def attach_existing_work(controller, *, campaign_root, server_home, connector_state, stop_for_lane):
    root=Path(campaign_root).resolve()
    require(root==controller.root,'CAMPAIGN_ROOT_MISMATCH')
    homes={'local':safe_path(server_home,root),'connector':safe_path(connector_state,root)}
    attached=[]
    for lane in ('local','connector'):
        records=[r for r in controller.data['requests'].values() if r['kind']=='work' and r['lane']==lane]
        if not records:continue
        scope=records[0]['scope'];actor=records[0]['actor_agent_id']
        require(all(r['scope']==scope and r['actor_agent_id']==actor for r in records),'HISTORICAL_ACTOR_SCOPE_CHANGED')
        require(controller.data['owners'].get(lane)==str(homes[lane]),'HISTORICAL_OWNER_CHANGED')
        controller.attach_owner(lane,homes[lane],lambda selected=lane:stop_for_lane(selected))
        if lane in controller._readers:
            reader=controller._readers[lane];journal=controller._journals[lane]
            require(reader.pre_scope==scope and reader.actor_id==actor and reader.database==homes['local']/'nexus.db'
                and journal.owner==homes[lane] and journal.lane==lane,'OBSERVER_SELECTION_CHANGED')
        else:
            controller.attach_observer(lane,CanonicalIntentReader(root,homes['local'],
                server_id=scope['server_id'],actor_id=actor,pre_scope=scope),CoreJournalReader(root,homes[lane],lane))
        attached.append(lane)
    return attached
