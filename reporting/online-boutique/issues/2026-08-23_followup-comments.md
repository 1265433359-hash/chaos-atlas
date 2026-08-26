# Follow-up comments for existing issues

These comments are ready to paste into the corresponding GitHub issues. They
are follow-ups to the existing issue reports, not new issues.

## GoogleCloudPlatform/microservices-demo#3473

Additional evidence from the same pinned commit:

Besides the PodKill case, we also tested 100% packet loss to
`productcatalogservice`. The first `GET /` request remained pending for
approximately 26.7 seconds and then returned HTTP 500.

This suggests that the failure mode is not only fail-closed rendering, but also
the absence of a bounded request deadline on the frontend-to-product-catalog
path. After fault removal and service recovery, the home page returned to its
baseline behavior.

The 26.7-second value is an experimental observation boundary, not a production
SLO claim. Could you confirm whether this fail-closed and unbounded behavior is
intentional for the demo?

Issue: https://github.com/GoogleCloudPlatform/microservices-demo/issues/3473

## GoogleCloudPlatform/microservices-demo#3474

Additional evidence for the checkout dependency behavior:

The `PlaceOrder` path invokes `shippingservice` twice: once for `GetQuote` and
once for `ShipOrder`. With a 2-second delay injected into `shippingservice`, the
total `PlaceOrder` latency increased to approximately 4021.5 ms from a baseline
of about 17 ms.

With simultaneous 2-second delays on `paymentservice` and `emailservice`, the
end-to-end latency was approximately 4016.2 ms, showing that synchronous
downstream delays accumulate across the checkout path.

These are controlled experiment measurements, not production SLO claims. The
main question is whether each dependency should have an explicit deadline and
whether the non-critical email operation should be asynchronous or best-effort.

Issue: https://github.com/GoogleCloudPlatform/microservices-demo/issues/3474
