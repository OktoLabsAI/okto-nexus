# Home R1 installed package and terminal regression

The integrated frontend run passed 196 tests once. The isolated installed selection passed 17 tests with no failures, errors or skips. The wheel and sdist passed Twine checks, and the runner verified all three application packages against their wheel bytes from `site-packages`, outside the checkout Python path.

The terminal checks exercise connect/reconnect, an interactive request with a question and answer, canonical result recovery, continuation in the exact existing session, close, and durable receipt/transport recovery. They use real installed CLI, HTTP/application and SQLite code with synthetic native peers. They neither visit Home nor invoke a real provider. This is terminal regression evidence, not a new provider acceptance campaign.

The Home package check serves the actual packaged index and every referenced JavaScript/CSS asset, compares their bytes with package resources, checks missing assets return404 and validates the Home v1/OpenAPI/runtime contracts together. No development web server is used.

`qualification.json` records commands, tool references, provenance, boundaries and warnings. `installed-campaign.json` confirms no source/docs/test input changed during the installed run. Root browser/performance work was allowed in parallel; durations here are not benchmark claims. The default client presentation remains classic/off in these exact bytes. Browser behavior is qualified separately.

The earlier stdio smoke paragraph in CONTRIBUTING does not override the current HTTP-only CLI contract; that historical script was not selected. Raw installation logs, binaries, environments, provider data and credentials are excluded from this evidence directory.
