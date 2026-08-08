# Issue draft — `quoteShipping` error message points to the wrong service

> Status: DRAFT — for review before submission. Not yet posted to GitHub.
> Target: https://github.com/open-telemetry/opentelemetry-demo
> Submission channel: normal issue (project has `SECURITY.md`; this is a correctness/bug report, not security).
> Confidence: HIGH — verified in local source checkout (commit `2e72d8bcdf754603e956406808630bc9663c992c`).

## Title

`quoteShipping` reports "failed POST to email service" when the failing call is to the shipping service (copy-paste error in the error message)

## Summary

In `checkout/main.go`, the `quoteShipping` function performs an HTTP POST to the **shipping** service (`shippingSvcAddr + "/get-quote"`), but the non-200 response error message says "failed POST to **email** service". This is a copy-paste error that misdirects anyone debugging a shipping-quote failure toward the email service.

## Evidence

`src/checkout/main.go:494` (inside `quoteShipping`):

```go
func (cs *checkout) quoteShipping(ctx context.Context, address *pb.Address, items []*pb.CartItem) (*pb.Money, error) {
    ...
    req, err := http.NewRequestWithContext(ctx, "POST", cs.shippingSvcAddr+"/get-quote", ...)  // shipping
    ...
    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("failed POST to email service: expected 200, got %d", resp.StatusCode)  // BUG: says email
    }
    ...
}
```

The request targets `shippingSvcAddr`; the error message says "email service".

## Expected behavior

The error message should read `"failed POST to shipping service: expected 200, got %d"`.

## Impact

- **Operability**: an operator or on-call engineer reading the log is pointed at the wrong service when shipping-quote returns non-200.
- **Reproducibility**: this is the exact path hit by our fault-injection experiment (shipping-service delay) — the misleading message surfaced when the shipping call degraded.

## Suggested fix

```go
if resp.StatusCode != http.StatusOK {
    return nil, fmt.Errorf("failed POST to shipping service: expected 200, got %d", resp.StatusCode)
}
```

## How we found it

We run isolated chaos experiments on the demo's checkout path (shipping-service latency injection). When the shipping quote call degraded, the error message blamed "email service", which contradicted the actual failing dependency — we traced it back to this copy-paste error.
