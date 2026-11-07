# CLI syntax reference

Generated from the CLI parser. Regenerate with `python tools/generate_cli_reference.py`.

Read the [usage guide](cli.md) for effects and prerequisites. --json and --verbose work before or after any command; other global options go before the command. Uppercase values are placeholders. Brackets mean optional; unbracketed flags are required. Legacy syntax is not proof of R4 support.

## okto-nexus-connector

```text
usage: okto-nexus-connector [-h] [--version] [--json] [--verbose]
                            [--non-interactive] [--state-dir STATE_DIR]
                            {clean,proxy,reach,configure,connect,identity,executor,discover,bind,runtime,daemon,service,reconnect,status,logs,doctor,approvals,mcp-config,harness-config,connection-config} ...

Remote harness connector for Okto Nexus

positional arguments:
  {clean,proxy,reach,configure,connect,identity,executor,discover,bind,runtime,daemon,service,reconnect,status,logs,doctor,approvals,mcp-config,harness-config,connection-config}
    clean               reset local Connector state, credentials and pending
                        configurations
    proxy               configure the host-local HTTP and WebSocket proxy
    reach               test Server reachability and report supported versions
                        (no credentials required)
    configure           interactive connection wizard (JSON optional)
    connect             guided first-use flow
    identity            imported identity management
    executor            R4 executor registration
    discover            local harness inventory (redacted)
    bind                advanced binding management
    runtime             managed runtime operations
    daemon              local daemon lifecycle
    service             OS autostart management
    reconnect           gracefully restart the daemon to reconnect all
                        configured connections
    status              show live server and agent connection health
    logs                inspect persistent daemon logs
    doctor              layered diagnostics
    approvals           pending HITL requests (decision authority stays on the
                        Server)
    mcp-config          direct-HTTP MCP client configuration
    harness-config      inspect, validate and apply Core harness parameters
    connection-config   reuse a complete Nexus connection JSON

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --json                machine-readable JSON output
  --verbose             include technical details
  --non-interactive     never prompt; ambiguity fails with guidance
  --state-dir STATE_DIR
                        override the per-user state directory
```

## okto-nexus-connector clean

```text
usage: okto-nexus-connector clean [-h] [--yes] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --yes       explicitly confirm cleanup without prompting
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector proxy

```text
usage: okto-nexus-connector proxy [-h] [--json] [--verbose]
                                  {set,show,clear} ...

positional arguments:
  {set,show,clear}
    set             save outbound proxy settings
    show            show settings without resolving credentials
    clear           restore environment/system proxy discovery

options:
  -h, --help        show this help message and exit
  --json            machine-readable JSON output
  --verbose         include technical details
```

## okto-nexus-connector proxy set

```text
usage: okto-nexus-connector proxy set [-h] (--url URL | --url-env URL_ENV |
                                      --direct) [--no-proxy NO_PROXY] [--json]
                                      [--verbose]

options:
  -h, --help           show this help message and exit
  --url URL            HTTP(S) proxy URL without credentials
  --url-env URL_ENV    environment variable containing the proxy URL (supports
                       credentials)
  --direct             disable proxy use, including environment proxies
  --no-proxy NO_PROXY  comma-separated bypass hosts, domains, or host:port
                       entries; * bypasses all
  --json               machine-readable JSON output
  --verbose            include technical details
```

## okto-nexus-connector proxy show

```text
usage: okto-nexus-connector proxy show [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector proxy clear

```text
usage: okto-nexus-connector proxy clear [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector reach

```text
usage: okto-nexus-connector reach [-h] --server SERVER [--json] [--verbose]

options:
  -h, --help       show this help message and exit
  --server SERVER  Nexus Server base URL
  --json           machine-readable JSON output
  --verbose        include technical details
```

## okto-nexus-connector configure

```text
usage: okto-nexus-connector configure [-h] [--file FILE] [--identity IDENTITY]
                                      [--server SERVER] [--agent AGENT]
                                      [--credential-stdin]
                                      [--credential-env CREDENTIAL_ENV]
                                      [--host {connector,server}]
                                      [--harness HARNESS] [--project PROJECT]
                                      [--workspace-label WORKSPACE_LABEL]
                                      [--provider-home PROVIDER_HOME]
                                      [--candidate-ref CANDIDATE_REF]
                                      [--executor-id EXECUTOR_ID]
                                      [--inventory-revision INVENTORY_REVISION]
                                      [--workspace-id WORKSPACE_ID]
                                      [--binding-id BINDING_ID]
                                      [--request-id REQUEST_ID]
                                      [--operator-identity OPERATOR_IDENTITY]
                                      [--operator-proof-ref OPERATOR_PROOF_REF]
                                      [--start-at-login | --no-start-at-login]
                                      [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --file FILE           portable connection template; destination paths are
                        ignored
  --identity IDENTITY   existing identity alias, or alias to register with a
                        hidden key prompt
  --server SERVER       Server URL when adding an identity
  --agent AGENT         identity hint, or target agent for Server-hosted
                        configuration
  --credential-stdin
  --credential-env CREDENTIAL_ENV
  --host {connector,server}
                        execution host (default: this Connector machine)
  --harness HARNESS
  --project PROJECT     workspace path on the execution host
  --workspace-label WORKSPACE_LABEL
  --provider-home PROVIDER_HOME
                        explicit login directory on the execution host
  --candidate-ref CANDIDATE_REF
  --executor-id EXECUTOR_ID
  --inventory-revision INVENTORY_REVISION
  --workspace-id WORKSPACE_ID
  --binding-id BINDING_ID
  --request-id REQUEST_ID
                        stable ID to resume configuration after an uncertain
                        response
  --operator-identity OPERATOR_IDENTITY
                        imported operator identity to apply Nexus policies
                        after binding approval
  --operator-proof-ref OPERATOR_PROOF_REF
                        operator approval reference from the binding proposal
  --start-at-login      include this Connector user logon task in the
                        connection review
  --no-start-at-login   keep the current service mode; existing tasks are
                        preserved
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector connect

```text
usage: okto-nexus-connector connect [-h] [--server SERVER]
                                    [--identity IDENTITY] [--agent AGENT]
                                    [--alias ALIAS]
                                    [--binding-alias BINDING_ALIAS]
                                    [--harness HARNESS]
                                    [--executable EXECUTABLE]
                                    [--pi-node PI_NODE] [--credential-stdin]
                                    [--credential-env CREDENTIAL_ENV]
                                    [--mcp-entry MCP_ENTRY]
                                    [--mcp-entry-name MCP_ENTRY_NAME]
                                    [--project PROJECT] [--start]
                                    [--trusted-provider-home]
                                    [--provider-home PROVIDER_HOME]
                                    [--request-id REQUEST_ID] [--customize]
                                    [--operator-identity OPERATOR_IDENTITY]
                                    [--operator-proof-ref OPERATOR_PROOF_REF]
                                    [--start-at-login | --no-start-at-login]
                                    [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server SERVER       Nexus Server base URL; reused from a saved project or
                        identity
  --identity IDENTITY   reuse this imported local identity without entering
                        its key again
  --agent AGENT         agent id hint from the Server screen
  --alias ALIAS         local identity alias (default: agent id)
  --binding-alias BINDING_ALIAS
                        local binding alias (default: harness)
  --harness HARNESS     adapter: codex_app_server|pi_rpc|claude_stream
  --executable EXECUTABLE
                        explicit harness executable to select
  --pi-node PI_NODE     trusted Node binary for the Pi CLI
  --credential-stdin    read the canonical key from stdin
  --credential-env CREDENTIAL_ENV
                        environment variable holding the key
  --mcp-entry MCP_ENTRY
                        explicitly selected MCP config file
  --mcp-entry-name MCP_ENTRY_NAME
                        entry name inside --mcp-entry
  --project PROJECT     project directory (default: cwd)
  --start               also start a runtime after connecting
  --trusted-provider-home
                        approve using the provider's own home dir
  --provider-home PROVIDER_HOME
                        provider login directory on this computer
  --request-id REQUEST_ID
                        resume the same R4 onboarding request
  --customize           edit advanced preferences before reviewing a new
                        project connection
  --operator-identity OPERATOR_IDENTITY
                        imported operator identity for Nexus configuration
  --operator-proof-ref OPERATOR_PROOF_REF
                        operator approval reference from Nexus
  --start-at-login      include this Connector user logon task in the
                        connection review
  --no-start-at-login   keep the current service mode; existing tasks are
                        preserved
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector identity

```text
usage: okto-nexus-connector identity [-h] [--json] [--verbose]
                                     {add,list,show,remove,replace-credential} ...

positional arguments:
  {add,list,show,remove,replace-credential}
    add                 import a canonical key

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector identity add

```text
usage: okto-nexus-connector identity add [-h] --server SERVER [--agent AGENT]
                                         --alias ALIAS [--credential-stdin]
                                         [--credential-env CREDENTIAL_ENV]
                                         [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server SERVER
  --agent AGENT
  --alias ALIAS
  --credential-stdin
  --credential-env CREDENTIAL_ENV
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector identity list

```text
usage: okto-nexus-connector identity list [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector identity show

```text
usage: okto-nexus-connector identity show [-h] [--json] [--verbose] alias

positional arguments:
  alias

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector identity remove

```text
usage: okto-nexus-connector identity remove [-h] [--json] [--verbose] alias

positional arguments:
  alias

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector identity replace-credential

```text
usage: okto-nexus-connector identity replace-credential [-h]
                                                        [--credential-stdin]
                                                        [--credential-env CREDENTIAL_ENV]
                                                        [--json] [--verbose]
                                                        alias

positional arguments:
  alias

options:
  -h, --help            show this help message and exit
  --credential-stdin
  --credential-env CREDENTIAL_ENV
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor

```text
usage: okto-nexus-connector executor [-h] [--json] [--verbose]
                                     {register,list,show,configure-launch,realize,configure-discovery,probe} ...

positional arguments:
  {register,list,show,configure-launch,realize,configure-discovery,probe}
    register            register this host using an imported identity
    list                list local registration intents and executor IDs
    show                show one Server's executor registration
    configure-launch    stage local launch consent without starting a runtime
    realize             publish this executor workspace and selected
                        installation
    configure-discovery
                        replace the Server executor local passive discovery
                        configuration
    probe               explicitly run the selected installation's sealed
                        version probe

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor register

```text
usage: okto-nexus-connector executor register [-h] --identity IDENTITY
                                              --label LABEL
                                              [--client-intent-id CLIENT_INTENT_ID]
                                              [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY   imported identity alias
  --label LABEL         host label shown by the Server
  --client-intent-id CLIENT_INTENT_ID
                        explicit registration intent ID; otherwise persisted
                        automatically
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor list

```text
usage: okto-nexus-connector executor list [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector executor show

```text
usage: okto-nexus-connector executor show [-h] [--json] [--verbose] server_id

positional arguments:
  server_id

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector executor configure-launch

```text
usage: okto-nexus-connector executor configure-launch [-h] --identity IDENTITY
                                                      --harness HARNESS
                                                      --local-consent-id LOCAL_CONSENT_ID
                                                      --profile-revision PROFILE_REVISION
                                                      [--provider-home PROVIDER_HOME]
                                                      [--secret-ref NAME=REFERENCE]
                                                      [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --harness HARNESS
  --local-consent-id LOCAL_CONSENT_ID
  --profile-revision PROFILE_REVISION
  --provider-home PROVIDER_HOME
                        explicitly approved existing provider login directory
  --secret-ref NAME=REFERENCE
                        protected vault/provider reference; never credential
                        material
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor realize

```text
usage: okto-nexus-connector executor realize [-h] --identity IDENTITY
                                             --client-intent-id CLIENT_INTENT_ID
                                             --harness HARNESS
                                             --candidate-ref CANDIDATE_REF
                                             --inventory-revision INVENTORY_REVISION
                                             --configuration-digest CONFIGURATION_DIGEST
                                             --project PROJECT
                                             [--workspace-id WORKSPACE_ID]
                                             --label LABEL [--json]
                                             [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --client-intent-id CLIENT_INTENT_ID
                        reuse this ID after a lost response
  --harness HARNESS
  --candidate-ref CANDIDATE_REF
  --inventory-revision INVENTORY_REVISION
  --configuration-digest CONFIGURATION_DIGEST
  --project PROJECT
  --workspace-id WORKSPACE_ID
  --label LABEL
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor configure-discovery

```text
usage: okto-nexus-connector executor configure-discovery [-h]
                                                         --server-id SERVER_ID
                                                         [--harness-root HARNESS_ROOT]
                                                         [--pi-install-root PI_INSTALL_ROOT]
                                                         [--pi-node PI_NODE]
                                                         [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server-id SERVER_ID
  --harness-root HARNESS_ROOT
                        approved absolute directory for PATH discovery; repeat
                        as needed
  --pi-install-root PI_INSTALL_ROOT
                        approved Pi releases directory
  --pi-node PI_NODE     Node executable for the Pi releases
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector executor probe

```text
usage: okto-nexus-connector executor probe [-h] --server-id SERVER_ID
                                           --harness HARNESS
                                           --candidate-ref CANDIDATE_REF
                                           --inventory-revision INVENTORY_REVISION
                                           [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server-id SERVER_ID
  --harness HARNESS
  --candidate-ref CANDIDATE_REF
  --inventory-revision INVENTORY_REVISION
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector discover

```text
usage: okto-nexus-connector discover [-h] [--server-id SERVER_ID]
                                     [--harness HARNESS]
                                     [--pi-releases-root PI_RELEASES_ROOT]
                                     [--pi-node PI_NODE] [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server-id SERVER_ID
                        preview persisted executor discovery configuration
  --harness HARNESS
  --pi-releases-root PI_RELEASES_ROOT
                        passively enumerate Pi release layouts under this
                        installation root
  --pi-node PI_NODE     trusted Node executable pairing the Pi releases
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector bind

```text
usage: okto-nexus-connector bind [-h] [--json] [--verbose]
                                 {prepare,apply,create,list,show,remove} ...

positional arguments:
  {prepare,apply,create,list,show,remove}
    prepare             prepare a reviewable R4 binding from a published
                        realization
    apply               apply the exact reviewed R4 binding proposal

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector bind prepare

```text
usage: okto-nexus-connector bind prepare [-h] --identity IDENTITY
                                         --realization-ref REALIZATION_REF
                                         [--replace-binding-id REPLACE_BINDING_ID]
                                         --alias ALIAS
                                         --client-intent-id CLIENT_INTENT_ID
                                         [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --realization-ref REALIZATION_REF
  --replace-binding-id REPLACE_BINDING_ID
                        Explicitly replace the reviewed binding realization.
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector bind apply

```text
usage: okto-nexus-connector bind apply [-h] --identity IDENTITY
                                       --prepare-intent-id PREPARE_INTENT_ID
                                       --client-intent-id CLIENT_INTENT_ID
                                       --approved-diff-hash APPROVED_DIFF_HASH
                                       [--operator-proof-ref OPERATOR_PROOF_REF]
                                       [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --prepare-intent-id PREPARE_INTENT_ID
  --client-intent-id CLIENT_INTENT_ID
  --approved-diff-hash APPROVED_DIFF_HASH
  --operator-proof-ref OPERATOR_PROOF_REF
                        explicit Server operator proof reference, when
                        required
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector bind create

```text
usage: okto-nexus-connector bind create [-h] --identity IDENTITY
                                        --harness HARNESS
                                        --executable EXECUTABLE
                                        [--pi-node PI_NODE] --alias ALIAS
                                        [--project PROJECT] [--json]
                                        [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --harness HARNESS
  --executable EXECUTABLE
  --pi-node PI_NODE
  --alias ALIAS
  --project PROJECT
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector bind list

```text
usage: okto-nexus-connector bind list [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector bind show

```text
usage: okto-nexus-connector bind show [-h] [--json] [--verbose] alias

positional arguments:
  alias

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector bind remove

```text
usage: okto-nexus-connector bind remove [-h] [--keep-config] [--json]
                                        [--verbose]
                                        alias

positional arguments:
  alias

options:
  -h, --help     show this help message and exit
  --keep-config
  --json         machine-readable JSON output
  --verbose      include technical details
```

## okto-nexus-connector runtime

```text
usage: okto-nexus-connector runtime [-h] [--json] [--verbose]
                                    {start,status,inspect,logs,submit,steer,interrupt,stop,operation} ...

positional arguments:
  {start,status,inspect,logs,submit,steer,interrupt,stop,operation}
    start               open or reuse an authorized session
    interrupt           cancel the active turn
    stop                close owned session resources
    operation           query a retained canonical runtime intent

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime start

```text
usage: okto-nexus-connector runtime start [-h]
                                          [--client-intent-id CLIENT_INTENT_ID]
                                          [--project PROJECT]
                                          [--harness HARNESS] [--new-session]
                                          [--session-id SESSION_ID]
                                          [--text TEXT] [--json] [--verbose]
                                          alias

positional arguments:
  alias

options:
  -h, --help            show this help message and exit
  --client-intent-id CLIENT_INTENT_ID
  --project PROJECT
  --harness HARNESS
  --new-session
  --session-id SESSION_ID
                        select an existing compatible R4 session
  --text TEXT           initial turn text
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime status

```text
usage: okto-nexus-connector runtime status [-h] [--alias ALIAS] [--json]
                                           [--verbose]

options:
  -h, --help     show this help message and exit
  --alias ALIAS  read retained R4 sessions from the Server
  --json         machine-readable JSON output
  --verbose      include technical details
```

## okto-nexus-connector runtime inspect

```text
usage: okto-nexus-connector runtime inspect [-h] [--alias ALIAS] [--json]
                                            [--verbose]
                                            session_id

positional arguments:
  session_id

options:
  -h, --help     show this help message and exit
  --alias ALIAS  select the retained R4 binding alias
  --json         machine-readable JSON output
  --verbose      include technical details
```

## okto-nexus-connector runtime logs

```text
usage: okto-nexus-connector runtime logs [-h] [--follow] [--json] [--verbose]
                                         session_id

positional arguments:
  session_id

options:
  -h, --help  show this help message and exit
  --follow
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector runtime submit

```text
usage: okto-nexus-connector runtime submit [-h] [--alias ALIAS]
                                           [--client-intent-id CLIENT_INTENT_ID]
                                           [--json] [--verbose]
                                           session_id text

positional arguments:
  session_id
  text

options:
  -h, --help            show this help message and exit
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime steer

```text
usage: okto-nexus-connector runtime steer [-h] --alias ALIAS
                                          --client-intent-id CLIENT_INTENT_ID
                                          [--expected-turn-id EXPECTED_TURN_ID]
                                          [--current-run] [--json] [--verbose]
                                          session_id text

positional arguments:
  session_id
  text

options:
  -h, --help            show this help message and exit
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --expected-turn-id EXPECTED_TURN_ID
  --current-run
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime interrupt

```text
usage: okto-nexus-connector runtime interrupt [-h] [--alias ALIAS]
                                              [--client-intent-id CLIENT_INTENT_ID]
                                              [--expected-turn-id EXPECTED_TURN_ID]
                                              [--current-run]
                                              [--reason REASON] [--json]
                                              [--verbose]
                                              session_id

positional arguments:
  session_id

options:
  -h, --help            show this help message and exit
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --expected-turn-id EXPECTED_TURN_ID
  --current-run
  --reason REASON
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime stop

```text
usage: okto-nexus-connector runtime stop [-h] [--alias ALIAS]
                                         [--client-intent-id CLIENT_INTENT_ID]
                                         [--reason REASON] [--json]
                                         [--verbose]
                                         session_id

positional arguments:
  session_id

options:
  -h, --help            show this help message and exit
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --reason REASON
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector runtime operation

```text
usage: okto-nexus-connector runtime operation [-h] --alias ALIAS
                                              --client-intent-id CLIENT_INTENT_ID
                                              [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --alias ALIAS
  --client-intent-id CLIENT_INTENT_ID
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector daemon

```text
usage: okto-nexus-connector daemon [-h] [--json] [--verbose]
                                   {start,run,status,stop} ...

positional arguments:
  {start,run,status,stop}
    start               background; returns after readiness
    run                 foreground (containers/diagnostics)

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector daemon start

```text
usage: okto-nexus-connector daemon start [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector daemon run

```text
usage: okto-nexus-connector daemon run [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector daemon status

```text
usage: okto-nexus-connector daemon status [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector daemon stop

```text
usage: okto-nexus-connector daemon stop [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector service

```text
usage: okto-nexus-connector service [-h] [--json] [--verbose]
                                    {install,uninstall,status} ...

positional arguments:
  {install,uninstall,status}

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector service install

```text
usage: okto-nexus-connector service install [-h] [--dry-run] [--json]
                                            [--verbose]

options:
  -h, --help  show this help message and exit
  --dry-run
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector service uninstall

```text
usage: okto-nexus-connector service uninstall [-h] [--dry-run] [--json]
                                              [--verbose]

options:
  -h, --help  show this help message and exit
  --dry-run
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector service status

```text
usage: okto-nexus-connector service status [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector reconnect

```text
usage: okto-nexus-connector reconnect [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector status

```text
usage: okto-nexus-connector status [-h] [--agent AGENT] [--json] [--verbose]

options:
  -h, --help     show this help message and exit
  --agent AGENT  show one agent by canonical agent id
  --json         machine-readable JSON output
  --verbose      include technical details
```

## okto-nexus-connector logs

```text
usage: okto-nexus-connector logs [-h] [--follow] [--errors] [--tail 1..10000]
                                 [--json] [--verbose]

options:
  -h, --help       show this help message and exit
  --follow         stream new log entries until Ctrl+C
  --errors         show warnings and errors only
  --tail 1..10000  maximum recent lines (default: 50)
  --json           machine-readable JSON output
  --verbose        include technical details
```

## okto-nexus-connector doctor

```text
usage: okto-nexus-connector doctor [-h] [--probe]
                                   [--diagnostic-format {legacy,v1}]
                                   [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --probe     attempt live network probes
  --diagnostic-format {legacy,v1}
              diagnostic report contract; legacy preserves existing JSON and exit codes
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector approvals

```text
usage: okto-nexus-connector approvals [-h] [--json] [--verbose]
                                      {list,decide} ...

positional arguments:
  {list,decide}
    list         list pending requests

options:
  -h, --help     show this help message and exit
  --json         machine-readable JSON output
  --verbose      include technical details
```

## okto-nexus-connector approvals list

```text
usage: okto-nexus-connector approvals list [-h] [--json] [--verbose]

options:
  -h, --help  show this help message and exit
  --json      machine-readable JSON output
  --verbose   include technical details
```

## okto-nexus-connector approvals decide

```text
usage: okto-nexus-connector approvals decide [-h] [--cas-token CAS_TOKEN]
                                             [--json] [--verbose]
                                             request_id {approve,deny}

positional arguments:
  request_id
  {approve,deny}

options:
  -h, --help            show this help message and exit
  --cas-token CAS_TOKEN
                        CAS token correlating the pending request
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector mcp-config

```text
usage: okto-nexus-connector mcp-config [-h] [--json] [--verbose]
                                       {plan,apply,remove} ...

positional arguments:
  {plan,apply,remove}

options:
  -h, --help           show this help message and exit
  --json               machine-readable JSON output
  --verbose            include technical details
```

## okto-nexus-connector mcp-config plan

```text
usage: okto-nexus-connector mcp-config plan [-h] --server SERVER
                                            --harness {codex_app_server,claude_stream,pi_rpc}
                                            --capability-ref CAPABILITY_REF
                                            [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server SERVER
  --harness {codex_app_server,claude_stream,pi_rpc}
  --capability-ref CAPABILITY_REF
                        mcp-cap: reference issued by the Server
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector mcp-config apply

```text
usage: okto-nexus-connector mcp-config apply [-h] --server SERVER
                                             --harness HARNESS
                                             --capability-ref CAPABILITY_REF
                                             --file FILE
                                             [--entry-name ENTRY_NAME]
                                             [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --server SERVER
  --harness HARNESS
  --capability-ref CAPABILITY_REF
  --file FILE
  --entry-name ENTRY_NAME
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector mcp-config remove

```text
usage: okto-nexus-connector mcp-config remove [-h] --harness HARNESS
                                              --file FILE
                                              [--entry-name ENTRY_NAME]
                                              [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --harness HARNESS
  --file FILE
  --entry-name ENTRY_NAME
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector harness-config

```text
usage: okto-nexus-connector harness-config [-h] [--json] [--verbose]
                                           {describe,validate,show,apply} ...

positional arguments:
  {describe,validate,show,apply}
    describe            show portable Core parameters; native availability
                        needs a live observation
    validate            validate a reusable JSON settings file without
                        applying it
    show                read or update canonical settings using an authorized
                        imported identity
    apply               read or update canonical settings using an authorized
                        imported identity

options:
  -h, --help            show this help message and exit
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector harness-config describe

```text
usage: okto-nexus-connector harness-config describe [-h]
                                                    --harness {codex_app_server,claude_stream,pi_rpc}
                                                    [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --harness {codex_app_server,claude_stream,pi_rpc}
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector harness-config validate

```text
usage: okto-nexus-connector harness-config validate [-h] --file FILE
                                                    [--harness HARNESS]
                                                    [--json] [--verbose]

options:
  -h, --help         show this help message and exit
  --file FILE
  --harness HARNESS
  --json             machine-readable JSON output
  --verbose          include technical details
```

## okto-nexus-connector harness-config show

```text
usage: okto-nexus-connector harness-config show [-h] --identity IDENTITY
                                                --endpoint-id ENDPOINT_ID
                                                [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --endpoint-id ENDPOINT_ID
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector harness-config apply

```text
usage: okto-nexus-connector harness-config apply [-h] --identity IDENTITY
                                                 --endpoint-id ENDPOINT_ID
                                                 --file FILE
                                                 --expected-revision EXPECTED_REVISION
                                                 [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --identity IDENTITY
  --endpoint-id ENDPOINT_ID
  --file FILE
  --expected-revision EXPECTED_REVISION
                        revision reviewed with harness-config show
  --json                machine-readable JSON output
  --verbose             include technical details
```

## okto-nexus-connector connection-config

```text
usage: okto-nexus-connector connection-config [-h] [--json] [--verbose]
                                              {validate,apply} ...

positional arguments:
  {validate,apply}

options:
  -h, --help        show this help message and exit
  --json            machine-readable JSON output
  --verbose         include technical details
```

## okto-nexus-connector connection-config validate

```text
usage: okto-nexus-connector connection-config validate [-h] --file FILE
                                                       [--json] [--verbose]

options:
  -h, --help   show this help message and exit
  --file FILE
  --json       machine-readable JSON output
  --verbose    include technical details
```

## okto-nexus-connector connection-config apply

```text
usage: okto-nexus-connector connection-config apply [-h] --file FILE
                                                    --identity IDENTITY
                                                    --agent AGENT
                                                    --request-id REQUEST_ID
                                                    [--executor-id EXECUTOR_ID]
                                                    [--candidate-ref CANDIDATE_REF]
                                                    [--inventory-revision INVENTORY_REVISION]
                                                    [--workspace-id WORKSPACE_ID]
                                                    [--binding-id BINDING_ID]
                                                    [--project PROJECT]
                                                    [--workspace-label WORKSPACE_LABEL]
                                                    [--provider-home PROVIDER_HOME]
                                                    [--execution-location {local,remote,all}]
                                                    [--json] [--verbose]

options:
  -h, --help            show this help message and exit
  --file FILE
  --identity IDENTITY   imported operator identity
  --agent AGENT
  --request-id REQUEST_ID
                        stable ID for safe retries
  --executor-id EXECUTOR_ID
  --candidate-ref CANDIDATE_REF
  --inventory-revision INVENTORY_REVISION
  --workspace-id WORKSPACE_ID
  --binding-id BINDING_ID
                        existing connection to replace
  --project PROJECT     workspace folder on the destination host; never
                        imported
  --workspace-label WORKSPACE_LABEL
  --provider-home PROVIDER_HOME
                        login directory on the destination host; never
                        imported
  --execution-location {local,remote,all}
  --json                machine-readable JSON output
  --verbose             include technical details
```
