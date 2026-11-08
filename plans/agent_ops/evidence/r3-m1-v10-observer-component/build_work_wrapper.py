from pathlib import Path
import ast,difflib,hashlib,json
D=Path(__file__).parent
BASE=Path('C:/Users/jpamb/AppData/Local/Temp/m1-v9-preparation-t4xaqhca/draft/m1_v9_work.py')
original=BASE.read_text(encoding='utf-8');text=original
def change(old,new):
    global text
    assert text.count(old)==1,old
    text=text.replace(old,new)
change('from controller import POLICY','from controller import POLICY\nfrom independent_journal import CanonicalIntentReader, CoreJournalReader\nfrom serial_flow import SerialFlow\nfrom history_observers import attach_existing_work')
change('flows={}; observed={}; guards=[]; stops=[]; handles=[]; selected_decisions=set()',
       'flows={}; raw_flows={}; bindings={}; observed={}; guards=[]; stops=[]; handles=[]; selected_decisions=set()')
change('    transport.timeout=.5','    transport.timeout=30  # accounting and deadline ticks do not wait for this worker')
change("    flows[lane]=flow\n    controller.attach(lane,flow)","    raw_flows[lane]=flow\n    controller.attach_api_flow(lane,flow)")
change('    return flow\n\ndef public_write',
       "    facade=SerialFlow(controller,flow,lane,lambda:poll_and_publish(controller,\n"
       "        lambda value:public_write('live-accounting.json',value),publication_diagnostics,request))\n"
       "    flows[lane]=facade\n    return facade\n\ndef public_write")
change("    for lane in sorted(active_lanes):attach(lane)\n    flow=flows[LANE]",
       "    for lane in sorted(active_lanes):attach(lane)\n"
       "    # Restore all historical observers before the first API job can pump\n"
       "    # the global ledger. No binding, decision or final GET runs on owner.\n"
       "    attach_existing_work(controller,campaign_root=ROOT,server_home=P['paths']['server_home'],\n"
       "        connector_state=P['paths']['connector_state'],stop_for_lane=stop_owner)\n"
       "    for lane in sorted(active_lanes):\n"
       "        binding=flows[lane].binding();bindings[lane]=binding\n"
       "        if lane not in controller._readers:\n"
       "            me=flows[lane].api('GET','/connections/me')\n"
       "            require(me['server_id']==binding['server_id'],'ACTOR_SERVER_MISMATCH')\n"
       "            selected={k:binding[k] for k in ('server_id','executor_id','binding_id','agent_id','workspace_id','workspace_binding_id')}\n"
       "            controller.attach_observer(lane,CanonicalIntentReader(ROOT,P['paths']['server_home'],\n"
       "                server_id=binding['server_id'],actor_id=me['agent_id'],pre_scope=selected),\n"
       "                CoreJournalReader(ROOT,P['paths']['server_home' if lane=='local' else 'connector_state'],lane))\n"
       "    flow=flows[LANE]")
change("    try:controller.work(request,LANE,text,stage='useful_work' if PHASE=='useful' else 'continuation')\n    except ConnectionError as error:\n        submission_error={'code':error.code,'stage':error.stage,'possible_effect':error.possible_effect}\n        if request not in controller.data['requests']:raise",
       "    controller.start_work(request,LANE,text,binding=bindings[LANE],checkpoint=flow.document,\n"
       "        stage='useful_work' if PHASE=='useful' else 'continuation')")
change("        value=observed.get(LANE,{})\n        for detail in value.get('requests',{}).get('items',[]):publish_approval(flow,detail)\n        recover_decisions(flow)\n        if current['settled']:break\n        if current['stop_selected'] and all(p.poll() is not None for p in stops):",
       "        returned=controller.take_api_result()\n"
       "        if returned is not None:\n"
       "            require(returned['label']==request,'DISPATCH_RESULT_MISMATCH')\n"
       "            if not returned['ok']:\n"
       "                error=returned['error']\n"
       "                submission_error={'code':getattr(error,'code','UNKNOWN'),'stage':getattr(error,'stage','unknown'),\n"
       "                    'possible_effect':bool(getattr(error,'possible_effect',False))}\n"
       "        if current['settled'] and controller.api.thread is None:break\n"
       "        if current['stop_selected'] and current['stop_selected']['action']=='stop_owner' and stops and all(p.poll() is not None for p in stops):\n"
       "            break\n"
       "        if controller.api.thread is None and current.get('stream') and not current['stop_selected']:\n"
       "            value=flow.observe(session_id=current['session'])\n"
       "            for detail in value.get('requests',{}).get('items',[]):publish_approval(flow,detail)\n"
       "            recover_decisions(flow)\n"
       "        if current['stop_selected'] and current['stop_selected']['action']=='stop_owner' and stops and all(p.poll() is not None for p in stops):")
change("    if current['settled'] and current.get('session'):","    if current['settled'] and current.get('session') and not controller.data['faults']:")
change("    report=Path(deliverables)/'report.json'",
       "    # Drain before any snapshot: a returned stop wrapper does not prove\n"
       "    # native exit, and a late worker result may add usage or diagnostics.\n"
       "    controller.drain_api()\n"
       "    late=controller.take_api_result()\n"
       "    if late is not None and not late['ok']:\n"
       "        error=late['error']\n"
       "        submission_error=submission_error or {'code':getattr(error,'code','UNKNOWN'),\n"
       "            'stage':getattr(error,'stage','unknown'),'possible_effect':bool(getattr(error,'possible_effect',False))}\n"
       "    controller.poll()\n"
       "    current=controller.data['requests'][request]\n"
       "    report=Path(deliverables)/'report.json'")
change("    public_write(request+'-runner-error.json'",
       "    controller.drain_api()\n    public_write(request+'-runner-error.json'")
change('    if operation_id:\n        receipt=flow.operation',
       "    if operation_id and current['settled'] and not controller.data['faults']:\n        receipt=flow.operation")
change("            'maximum_poll_start_interval_seconds':max(intervals,default=0),'calls':call_counts,",
       "            'maximum_poll_start_interval_seconds':controller.data.get('independent_observation',{}).get('maximum_poll_start_interval_seconds'),\n"
       "            'outer_loop_interval_seconds':max(intervals,default=0),'calls':call_counts,\n"
       "            'independent_observation':controller.data.get('independent_observation'),\n"
       "            'preopen_failure':current.get('preopen_failure'),")
change("        'containment_error_type':containment_error,'summary':controller.summary(),",
       "        'containment_error_type':containment_error,'summary':controller.summary(),\n"
       "        'independent_observation':controller.data.get('independent_observation'),")
ast.parse(text)
(D/'m1_work_serial_candidate.py').write_text(text,encoding='utf-8',newline='\n')
(D/'work-wrapper.diff').write_text(''.join(difflib.unified_diff(original.splitlines(keepends=True),text.splitlines(keepends=True),fromfile='frozen-v9/m1_v9_work.py',tofile='candidate/m1_work_serial_candidate.py')),encoding='utf-8',newline='\n')
assert hashlib.sha256(BASE.read_bytes()).hexdigest()=='425ef79d7058c11179d3a235999264e47badabf6b132cdbc6a041e6867c2222a'
print(json.dumps({'status':'CANDIDATE_WRAPPER_BUILT_NOT_AUTHORIZED','sha256':hashlib.sha256((D/'m1_work_serial_candidate.py').read_bytes()).hexdigest()}))
