import { useState } from "react";
import type { ApprovalDetail } from "../api";

type Question = {
  id?: string; question: string; header: string; isOther?: boolean;
  multiSelect?: boolean; options?: { label: string; description: string }[];
};
type Property = {
  type: "string" | "number" | "integer" | "boolean"; title?: string; description?: string;
  enum?: (string | number | boolean)[]; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number;
};
type NativeRequest = { method: string; params: {
  tool_name?: string; questions?: Question[]; input?: { questions?: Question[] };
  message?: string; requestedSchema?: { properties: Record<string, Property>; required?: string[] };
}};
const fieldClass = "block w-full mt-1 rounded border border-surface-300 dark:border-surface-600 bg-white dark:bg-surface-800 p-2 text-sm";

/** No defaults, credential inputs, remote schemas or automatic submissions. */
export function NativeApprovalInput({ detail, busy, onApprove }: {
  detail: ApprovalDetail; busy: boolean;
  onApprove: (response?: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const [error, setError] = useState<string | null>(null);
  const request = detail.request_payload?.kwargs?.payload as NativeRequest | undefined;
  const params = request?.params;
  const codex = request?.method === "item/tool/requestUserInput";
  const claude = request?.method === "control_request:can_use_tool" && params?.tool_name === "AskUserQuestion";
  const form = request?.method === "mcpServer/elicitation/request";
  const permission = ["item/commandExecution/requestApproval", "item/fileChange/requestApproval"].includes(request?.method ?? "") ||
    (request?.method === "control_request:can_use_tool" && ["Write", "Edit", "Bash"].includes(params?.tool_name ?? ""));
  const questions = (claude ? params?.input?.questions : params?.questions) ?? [];
  const properties = params?.requestedSchema?.properties ?? {};
  const supported = permission || ((codex || claude) && questions.length > 0) || (form && Object.keys(properties).length > 0);
  const native = detail.decision_detail;
  const expired = !!native && new Date(native.expires_at).getTime() <= Date.now();
  const ready = detail.status === "pending" && native?.state === "PENDING" && !expired;
  const set = (key: string, value: string) => setValues(old => ({ ...old, [key]: value }));

  const submit = () => {
    try {
      let response: Record<string, unknown> | undefined;
      if (codex || claude) {
        const answers = Object.fromEntries(questions.map((q, i) => {
          const key = String(i), custom = values[key] ?? "";
          const selected = (choices[key] ?? []).map(index => index === "custom" ? custom : q.options![Number(index)].label);
          const texts = q.options?.length ? selected : [custom];
          if (!texts.length || texts.some(text => !text.length)) throw new Error("Answer each question before sending.");
          return [codex ? q.id! : q.question, codex ? { answers: texts } : q.multiSelect ? texts : texts[0]];
        }));
        response = { answers };
      } else if (form) {
        const content = Object.fromEntries(Object.entries(properties).flatMap(([key, prop]) => {
          const raw = Object.hasOwn(values, key) ? values[key] : undefined;
          if (raw === undefined || (raw === "" && (prop.type !== "string" || prop.enum))) {
            if (params?.requestedSchema?.required?.includes(key)) throw new Error("Complete each required field.");
            return [];
          }
          const value = prop.enum ? prop.enum[Number(raw)] : prop.type === "boolean" ? raw === "true" :
            prop.type === "string" ? raw : Number(raw);
          if (typeof value === "number" && !Number.isFinite(value)) throw new Error("Enter a finite number.");
          return [[key, value]];
        }));
        response = { content };
      }
      if (response && new TextEncoder().encode(JSON.stringify(response)).length > 16384) throw new Error("The answer is too large.");
      setError(null);
      onApprove(response);
    } catch (exc) { setError((exc as Error).message); }
  };

  return <div className="space-y-3" data-testid="native-approval-input">
    <p>Runtime request: <b>{native?.state ?? "unavailable"}</b>{expired ? " · expired" : ""}.
      Your decision is recorded separately from delivery to the runtime.</p>
    {native?.reason && <p>Delivery detail: {native.reason}</p>}
    {native?.response != null && <pre className="whitespace-pre-wrap break-all max-h-40 overflow-auto">{JSON.stringify(native.response, null, 2)}</pre>}
    {!supported && <p>This request cannot be answered in this view. Its original details remain available below.</p>}
    {ready && supported && <form onSubmit={event => { event.preventDefault(); submit(); }} className="space-y-3">
      {(codex || claude) && questions.map((q, i) => {
        const key = String(i), id = `${detail.approval_id}-question-${i}`;
        const multiple = codex || q.multiSelect === true;
        return <div key={key}>
          <label htmlFor={id}>{q.question}</label>
          {q.options?.length ? <>
            {multiple && <p className="text-surface-500">Select one or more answers.</p>}
            <select id={id} className={fieldClass} required multiple={multiple}
              value={multiple ? choices[key] ?? [] : choices[key]?.[0] ?? ""}
              onChange={event => setChoices(old => ({ ...old, [key]: Array.from(event.target.selectedOptions, o => o.value) }))}>
              {!multiple && <option value="" disabled>Choose an answer</option>}
              {q.options.map((option, index) => <option key={index} value={String(index)}>{option.label}</option>)}
              {(claude || q.isOther) && <option value="custom">Write another answer</option>}
            </select>
            {q.options.map((option, index) => <p key={index} className="text-surface-500">{option.label}: {option.description}</p>)}
            {choices[key]?.includes("custom") && <label>Another answer
              <textarea className={fieldClass} required maxLength={4096} value={values[key] ?? ""} onChange={event => set(key, event.target.value)} />
            </label>}
          </> : <textarea id={id} className={fieldClass} required maxLength={4096} value={values[key] ?? ""} onChange={event => set(key, event.target.value)} />}
        </div>;
      })}
      {form && <>
        <p>{params?.message}</p>
        {Object.entries(properties).map(([key, prop], index) => {
          const id = `${detail.approval_id}-field-${index}`;
          const required = params?.requestedSchema?.required?.includes(key);
          const emptyText = prop.type === "string" && !prop.enum && !prop.minLength && Object.hasOwn(values, key) && values[key] === "";
          return <div key={key}>
            <label htmlFor={id}>{prop.title || key}{required ? " *" : " (optional)"}</label>
            {prop.description && <p className="text-surface-500">{prop.description}</p>}
            {prop.enum || prop.type === "boolean" ? <select id={id} className={fieldClass} required={required}
              value={Object.hasOwn(values, key) ? values[key] : ""} onChange={event => set(key, event.target.value)}>
              <option value="">Choose a value</option>
              {prop.enum ? prop.enum.map((value, i) => <option key={i} value={String(i)}>{String(value)}</option>) :
                <><option value="true">Yes</option><option value="false">No</option></>}
            </select> : <input id={id} className={fieldClass} required={required && !emptyText} type={prop.type === "string" ? "text" : "number"}
              step={prop.type === "integer" ? 1 : "any"} min={prop.minimum} max={prop.maximum}
              minLength={prop.minLength} maxLength={Math.min(prop.maxLength ?? 4096, 4096)}
              value={Object.hasOwn(values, key) ? values[key] : ""} onChange={event => set(key, event.target.value)} />}
            {prop.type === "string" && !prop.enum && !prop.minLength && <label className="flex gap-2 mt-1">
              <input type="checkbox" checked={emptyText} onChange={event => {
                if (event.target.checked) set(key, "");
                else setValues(old => Object.fromEntries(Object.entries(old).filter(([name]) => name !== key)));
              }} />Send empty text for {prop.title || key}
            </label>}
          </div>;
        })}
      </>}
      {error && <p role="alert" className="text-red-600">{error}</p>}
      <button type="submit" disabled={busy} className="rounded-lg bg-emerald-600 text-white px-3 py-2 disabled:opacity-50">
        {permission ? "Approve request" : "Send answer"}
      </button>
    </form>}
  </div>;
}
