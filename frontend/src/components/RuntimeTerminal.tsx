import { useMemo, useRef, useState, useEffect, useLayoutEffect, useCallback, type Ref, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Terminal, Check, ChevronRight, Circle, AlertCircle, Maximize2, Minimize2, Minus, Plus } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { RuntimeEventPage } from '../runtimeApi';
import { presentEvents, type TerminalAction } from '../runtimePresentation';
import { content } from '../runtimePresentation/model';
import './RuntimeTerminal.css';

const time = (value?: string) => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleTimeString() : '';
const fontPreference = 'nexus-terminal-font-size';
const defaultFontSize = 12, minFontSize = 10, maxFontSize = 24;
interface Scrollback {
  hasPrevious: boolean; loading: boolean; error: string; loadPrevious: () => void;
  autoScroll: boolean; setAutoScroll: (value: boolean) => void;
}
function readFontSize() {
  try {
    const value = Number(localStorage.getItem(fontPreference));
    if (Number.isInteger(value) && value >= minFontSize && value <= maxFontSize) return value;
  } catch { /* The terminal also works when browser storage is unavailable. */ }
  return defaultFontSize;
}
function Action({action}: {action: TerminalAction}) {
  const failed=action.kind==='error' || action.status==='failed', completed=['completed','success','succeeded'].includes(action.status || '');
  return <li data-action-id={action.id} className={`runtime-terminal-action runtime-terminal-${action.kind} ${failed?'runtime-terminal-failed':''}`}>
    <span className="runtime-terminal-symbol" aria-hidden="true">{failed?<AlertCircle size={14}/>:action.kind==='user'?<ChevronRight size={14}/>:completed?<Check size={14}/>:<Circle size={8}/>}</span>
    <div className="runtime-terminal-action-body">
      <div className="runtime-terminal-action-header"><strong>{action.title}</strong>{action.status && <span>{action.status}</span>}<time title={action.time}>{time(action.time)}</time></div>
      {action.text && <div className="runtime-terminal-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content(action.text)}</ReactMarkdown></div>}
      {!!action.fields?.length && <dl className="runtime-terminal-fields">{action.fields.map((field,i)=><div key={i}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>}
      {!!action.details?.length && <details className="runtime-terminal-output"><summary>Delivery context</summary><dl className="runtime-terminal-fields">{action.details.map((field,i)=><div key={i}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl></details>}
      {action.output && <details className="runtime-terminal-output" open={failed || undefined}><summary>Output</summary><pre>{action.output}</pre></details>}
    </div>
  </li>;
}

export function RuntimeTerminal({events, harness, scrollRef, scrollback, label='Session terminal', empty='No activity to display yet.'}: {
  events: RuntimeEventPage['events']; harness?: string; scrollRef?: Ref<HTMLOListElement>; scrollback?: Scrollback; label?: string; empty?: string;
}) {
  const actions=useMemo(()=>presentEvents(events,harness),[events,harness]);
  return <TerminalView actions={actions} harness={harness} scrollRef={scrollRef} scrollback={scrollback} label={label} empty={empty}/>;
}

export function RuntimeFinalOutput({text}: {text: string}) {
  return <TerminalView actions={[{id:'final',kind:'assistant',title:'Assistant',text}]} label="Execution output"/>;
}

function TerminalView({actions,harness,scrollRef,scrollback,label,empty}: {actions:TerminalAction[];harness?:string;scrollRef?:Ref<HTMLOListElement>;scrollback?:Scrollback;label:string;empty?:string}) {
  const [maximized,setMaximized]=useState(false);
  const [fontSize,setFontSize]=useState(readFontSize);
  useEffect(()=>{
    const sync=()=>setFontSize(readFontSize());
    window.addEventListener(fontPreference,sync);
    window.addEventListener('storage',sync);
    return ()=>{window.removeEventListener(fontPreference,sync);window.removeEventListener('storage',sync);};
  },[]);
  const resizeFont=(size:number)=>{
    const next=Math.min(maxFontSize,Math.max(minFontSize,size));
    setFontSize(next);
    try {localStorage.setItem(fontPreference,String(next));window.dispatchEvent(new Event(fontPreference));}
    catch { /* Keep the current terminal usable without persistence. */ }
  };
  const dialog=useRef<HTMLDialogElement>(null);
  const trigger=useRef<HTMLButtonElement>(null);
  const screen=useRef<HTMLOListElement|null>(null);
  const position=useRef(0);
  const anchor=useRef<{id?:string; offset:number; top:number; height:number}>({offset:0,top:0,height:0});
  const rememberPosition=()=>{
    const el=screen.current;
    if (!el) return;
    const top=el.getBoundingClientRect().top;
    const row=Array.from(el.querySelectorAll<HTMLElement>('[data-action-id]')).find(item=>item.getBoundingClientRect().bottom>top);
    anchor.current={id:row?.dataset.actionId,offset:row?row.getBoundingClientRect().top-top:0,top:el.scrollTop,height:el.scrollHeight};
    position.current=el.scrollTop;
  };
  useLayoutEffect(()=>{
    const el=screen.current;
    if (!el || !scrollback) return;
    if (scrollback.autoScroll) el.scrollTop=el.scrollHeight;
    else {
      const saved=anchor.current;
      const row=Array.from(el.querySelectorAll<HTMLElement>('[data-action-id]')).find(item=>item.dataset.actionId===saved.id);
      if (row) el.scrollTop+=row.getBoundingClientRect().top-el.getBoundingClientRect().top-saved.offset;
      else if (saved.height && el.scrollHeight>saved.height) el.scrollTop=saved.top+el.scrollHeight-saved.height;
    }
    rememberPosition();
  },[actions,scrollback?.autoScroll,scrollback?.hasPrevious,maximized,fontSize]);
  const loadPrevious=()=>{
    if (scrollback?.hasPrevious && !scrollback.loading) {
      scrollback.setAutoScroll(false);rememberPosition();scrollback.loadPrevious();
    }
  };
  const onScroll=()=>{
    const el=screen.current;
    if (!el) return;
    const upwards=el.scrollTop<position.current;
    if (upwards && scrollback?.autoScroll) scrollback.setAutoScroll(false);
    rememberPosition();
    if (upwards && el.scrollTop<120) loadPrevious();
  };
  useEffect(()=>{
    if (!maximized) return;
    const element=dialog.current!;element.showModal();
    return ()=>{element.close();trigger.current?.focus({preventScroll:true});};
  },[maximized]);
  const toggle=()=>{position.current=screen.current?.scrollTop || 0;setMaximized(v=>!v);};
  const setScreen=useCallback((element:HTMLOListElement|null)=>{
    if (!element && screen.current) position.current=screen.current.scrollTop;
    screen.current=element;
    if (typeof scrollRef==='function') scrollRef(element);
    else if (scrollRef) (scrollRef as {current:HTMLOListElement|null}).current=element;
    if (element) element.scrollTop=position.current;
  },[scrollRef,maximized]);
  const terminal=<div className="runtime-terminal" style={{'--terminal-font-size':`${fontSize}px`} as CSSProperties}>
    <header className="runtime-terminal-bar"><Terminal size={14}/><span>{harness==='codex_app_server'?'Codex':harness==='claude_stream'?'Claude':harness==='pi_rpc'?'Pi':'Session'} · terminal</span><span className="runtime-terminal-readonly">Read only</span>
      <div className="runtime-terminal-font-controls" role="group" aria-label="Terminal font size">
        <button type="button" className="runtime-terminal-expand" aria-label="Decrease terminal font size" title="Decrease font size" disabled={fontSize<=minFontSize} onClick={()=>resizeFont(fontSize-1)}><Minus size={15}/></button>
        <button type="button" className="runtime-terminal-expand runtime-terminal-font-size" aria-label="Reset terminal font size" title="Reset font size to 12px" onClick={()=>resizeFont(defaultFontSize)}><span aria-live="polite">{fontSize}px</span></button>
        <button type="button" className="runtime-terminal-expand" aria-label="Increase terminal font size" title="Increase font size" disabled={fontSize>=maxFontSize} onClick={()=>resizeFont(fontSize+1)}><Plus size={15}/></button>
      </div>
      <button type="button" ref={maximized?undefined:trigger} className="runtime-terminal-expand" aria-label={maximized?'Restore terminal':'Maximize terminal'} title={maximized?'Restore terminal (Esc)':'Maximize terminal'} onClick={toggle}>
        {maximized?<Minimize2 size={15}/>:<Maximize2 size={15}/>}</button>
    </header>
    <ol ref={setScreen} className="runtime-terminal-screen" aria-label={label} tabIndex={0} onScroll={onScroll}
      onWheel={event=>{if(event.deltaY<0 && (screen.current?.scrollTop ?? Infinity)<120) loadPrevious();}}>
      {scrollback?.hasPrevious && <li className="runtime-terminal-previous"><button type="button" disabled={scrollback.loading} onClick={loadPrevious}>{scrollback.loading?'Loading previous events…':'Load previous events'}</button></li>}
      {scrollback?.error && <li role="alert" className="runtime-terminal-failed">{scrollback.error}</li>}
      {actions.map(action=><Action key={action.id} action={action}/>)}
      {!actions.length && <li className="runtime-terminal-empty">{empty}</li>}
    </ol>
  </div>;
  return maximized ? createPortal(<dialog ref={dialog} className="runtime-terminal-dialog" aria-label={`${label} · maximized`} aria-modal="true"
    onCancel={event=>{event.preventDefault();event.stopPropagation();toggle();}}>{terminal}</dialog>,document.body) : terminal;
}
