# Installed R4 directed Linux conformance

WSL Ubuntu / Python 3.13.14: 38 tests passed in 308.99 seconds.
The runner checked installed package bytes against the same development wheels
used on Windows; campaign inputs were unchanged. See `campaign.json`,
`installed.json` and `tests.xml` for commands, hashes and individual results.

This covers protocol/inventory, embedded actions/decisions and remote actions
over actual local HTTP/WebSocket transport with synthetic native peers. WSL is
on the Windows machine; this is not independent-host or real Linux-provider
acceptance, a full Linux regression, or a final M13 artifact freeze.
