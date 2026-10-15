import { ConfigurationHelp } from './ConfigurationHelp';

export function BroadcastHandoffPolicy({value, onChange, inherited, rolloutEnabled, disabled, className}: {
  value: boolean | null; onChange: (value: boolean | null) => void;
  inherited?: boolean; rolloutEnabled: boolean; disabled?: boolean; className?: string;
}) {
  return <div className="space-y-1">
    <label className="block">Automatically claim broadcast handoffs
      <ConfigurationHelp label="Broadcast handoff automation">Reserve available runtime capacity before claiming a broadcast handoff. Only the winner executes it. Agent permissions, routing and a valid execution grant are still required. This does not change direct handoffs or ordinary broadcast messages.</ConfigurationHelp>
      <select aria-label="Automatically claim broadcast handoffs" className={className} disabled={disabled}
        value={value === null ? 'inherit' : String(value)}
        onChange={event => onChange(event.target.value === 'inherit' ? null : event.target.value === 'true')}>
        {inherited !== undefined && <option value="inherit">Use global setting ({inherited ? 'Enabled' : 'Disabled'})</option>}
        <option value="false">Disabled</option><option value="true">Enabled when capacity is available</option>
      </select>
    </label>
    {!rolloutEnabled && <p className="text-xs text-surface-500">Automatic acquisition is disabled on this server. You can save this preference; handoffs remain available through MCP and manual claims.</p>}
  </div>;
}
