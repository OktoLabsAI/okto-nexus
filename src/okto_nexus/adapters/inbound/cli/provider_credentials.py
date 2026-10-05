"""Local owner CLI for provider credentials; secret material is never printed."""
import argparse
import getpass
import json
import sys

from ...outbound.provider_vault import ProviderVault, ProviderVaultError


def run_provider_credentials(argv):
    parser=argparse.ArgumentParser(prog="okto-nexus provider-credentials")
    parser.add_argument("action",choices=("set","remove"))
    parser.add_argument("--home",required=True)
    parser.add_argument("--agent-id",required=True)
    parser.add_argument("--reference",required=True,help="Agent-scoped reference, such as vault:openai.")
    parser.add_argument("--secret-stdin",action="store_true",help="Read the provider secret from stdin instead of a hidden prompt.")
    args=parser.parse_args(argv)
    try:
        vault=ProviderVault(args.home,args.agent_id)
        if args.action=="set":
            if args.secret_stdin:
                value=sys.stdin.read(4098).removesuffix("\n").removesuffix("\r")
            elif sys.stdin.isatty():
                value=getpass.getpass("Provider credential: ")
            else:
                raise ProviderVaultError("Use --secret-stdin for noninteractive credential input.")
            vault.store(args.reference,value)
        else:
            if args.secret_stdin:
                raise ProviderVaultError("Secret input is not accepted for removal.")
            vault.remove(args.reference)
    except (ProviderVaultError,EOFError,KeyboardInterrupt):
        print("The provider credential operation could not be completed.",file=sys.stderr)
        return 1
    print(json.dumps({"reference":args.reference,"agent_id":args.agent_id,"status":"stored" if args.action=="set" else "removed"}))
    return 0
