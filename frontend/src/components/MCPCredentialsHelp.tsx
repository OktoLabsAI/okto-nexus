export function MCPCredentialsHelp() {
  return <div className="space-y-3 text-xs leading-relaxed text-surface-600 dark:text-surface-300">
    <h3 className="font-semibold">Direct values</h3>
    <p>Choose <b>Direct value</b> for an environment variable or HTTP header. Values are saved in the connection configuration and can appear in exports and backups. Masking the field only hides it on screen. This warning does not prevent saving. For Authorization headers, include the complete value expected by the MCP, such as the Bearer prefix.</p>
    <h3 className="font-semibold">Host environment</h3>
    <p>Choose <b>Host environment</b> and enter the variable name, for example <code>MY_MCP_TOKEN</code>. Nexus stores the reference <code>provider:MY_MCP_TOKEN</code>, not its value. Set the variable in the environment of the process that runs Nexus (local) or Connector (remote). An external secret manager can supply that environment; Nexus does not fetch arbitrary provider URLs. A running process must be relaunched to inherit a changed environment.</p>
    <h3 className="font-semibold">Local credential vault</h3>
    <p>The Nexus vault is local storage backed by the operating system: Windows Credential Manager on Windows. It is not an external vault service. There is currently no dashboard form to register values in it. For a local runtime, use the CLI with the same Nexus home, agent and OS account as the server:</p>
    <pre className="whitespace-pre-wrap break-all rounded bg-surface-100 p-3 dark:bg-surface-800">{'okto-nexus provider-credentials set --home "PATH_TO_NEXUS_HOME" --agent-id YOUR_AGENT --reference vault:my-mcp-key'}</pre>
    <p>Replace PATH_TO_NEXUS_HOME with the server data directory (normally .okto_nexus in your user folder). The CLI prompts for the value without displaying it. Choose <b>Host vault</b> and enter <code>my-mcp-key</code>. A remote Connector uses credentials on its own host; storing a value on the Nexus Server does not copy it there.</p>
    <h3 className="font-semibold">Reference authorization</h3>
    <p>Environment and vault references must exist on the execution host and be included in the connection&apos;s approved secret bindings. Entering a reference in this form does not create the secret or grant that authorization. Until that host configuration is available, use a direct value or an already configured inherited MCP. These checks still apply when a runtime uses a reference.</p>
    <p>Add or save the MCP to the list, then finish the connection workflow. Changes apply to new sessions.</p>
  </div>;
}
