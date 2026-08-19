# Generic `availableconstraint` parsing retry

## Problem

`opensdmx constraints EXR --provider https://nsidisseminate-stat.nbb.be/rest`
fails although the NBB `availableconstraint` endpoint works. The first request
currently includes the implicit parameter `references=none`. NBB answers that
variant with HTTP 200, `text/html`, and a malformed JavaScript error page. The
same endpoint without `references` returns 57,735 bytes of valid SDMX-XML that
the existing parser reads correctly.

`get_available_values()` catches the parsing exception and returns an empty
mapping. The CLI then turns every empty mapping into the unsupported-endpoint
guess. This loses the verified cause and gives the user the wrong next action.

## Goals

- Make `constraints` work with NBB without provider-specific URL checks.
- Keep the first request and successful path unchanged for standard providers.
- Retry once without `references` only for the observed interoperability case.
- Preserve the real failure when the retry cannot recover.
- Remove the unsupported-endpoint guess from the empty-result CLI message.
- Add regression coverage for both recovery and unchanged provider behavior.

## Non-goals

- Add NBB as a built-in provider preset.
- Change constraint endpoint selection or timeout behavior.
- Retry arbitrary HTTP errors or all parsing failures with different requests.
- Change `contentconstraint`, hub, cache, or `serieskeysonly` behavior.
- Address the previously reported `get EXR --REF_AREA BE` 404; it no longer
  reproduces and the command currently returns data.

## Design

### Request and parsing flow

The existing request remains the first attempt. `get_available_values()` builds
the same path, timeout, retry count, and effective `constraint_params`, then
requests and parses the response as it does today.

If parsing raises an XML parsing exception, a second attempt is allowed only
when all of these conditions hold:

1. the selected endpoint is `availableconstraint`;
2. the effective request parameters contain `references`;
3. the failure occurred while parsing the returned body, not while making the
   HTTP request.

The second request uses the same path, timeout, retry count, and every other
parameter, with only `references` removed. It runs at most once. Its response
is passed to the existing `_parse_constraint_xml()` function. A successful
result follows the existing cache and DataFrame conversion path.

The retry logic stays private to `discovery.py`. No public API or new provider
configuration key is introduced.

### Error handling

HTTP failures retain their current handling: timeout may use
`serieskeysonly`, status 500 maps to `ConstraintsUnavailable`, and the
`contentconstraint` 404 fallback remains unchanged.

If the initial body cannot be parsed and retry is ineligible, the existing
generic failure path receives that parsing exception. If the retry request or
its parsing also fails, the final exception is logged with the retry context;
the function does not run a third request.

When no constrained values are returned, the CLI reports that fact without
claiming the provider may not support `availableconstraint`. Detailed fetch or
parse failures remain visible through the existing error logging.

### Compatibility boundaries

- Eurostat uses `contentconstraint`: no parsing retry and no request change.
- ISTAT normally uses its hub or `contentconstraint`: no parsing retry and no
  request change.
- ABS and OECD explicitly set `constraint_params: {}`: their requests contain
  no `references`, so no new retry is eligible.
- BIS and IMF keep their existing first request. A valid response produces no
  second call. Only an XML parsing failure can activate the compatibility retry.
- Custom providers keep the current implicit `references=none` first request;
  endpoints with NBB-like behavior can recover generically.

This preserves success-path URL and parameter behavior for every standard
provider. The only added network call occurs after a response that could not be
parsed and was already unusable.

## Tests

Unit tests will establish:

- malformed XML from `availableconstraint` with `references=none`, followed by
  valid XML without it, returns parsed values and caches them;
- the retry removes only `references` and preserves other parameters;
- valid first-response XML makes exactly one request;
- `contentconstraint` parsing failure does not retry without `references`;
- explicit empty `constraint_params` makes no retry eligible;
- a failed second attempt terminates after two calls and exposes the final
  failure through the current error path;
- the CLI empty-result message is neutral and contains no unsupported-endpoint
  diagnosis.

Regression verification will run the focused discovery, HTTP, and CLI tests,
then the full test suite, ruff, and mypy. Live before/after probes will compare
standard providers that exercise distinct branches: Eurostat
(`contentconstraint`), ABS (explicit empty params), BIS and IMF (successful
`availableconstraint` with the default params), and OECD when its constraints
endpoint is operational. NBB must finish with five dimensions and the verified
code counts 27/1/945/3/4 from a clean cache.

## Documentation and delivery

`LOG.md` will replace the diagnosis-only wording with the implemented behavior,
tests, and live compatibility evidence. No README change is needed because the
CLI interface and user workflow do not change.
