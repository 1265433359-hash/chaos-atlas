#!/usr/bin/env python3
"""gRPC client for Online Boutique lab: add item to cart, then PlaceOrder.
Usage: python ob_client.py <checkout_addr:port>
"""
import sys
import time

import grpc
import demo_pb2 as pb
import demo_pb2_grpc as pbgrpc

CHECKOUT = sys.argv[1] if len(sys.argv) > 1 else "localhost:15050"
CART = sys.argv[2] if len(sys.argv) > 2 else "localhost:17070"


def run_one(idx, timeout_s=10.0):
    """Add one product to a unique user cart, then place the order."""
    user = f"lab-user-{idx}"
    cart_stub = pbgrpc.CartServiceStub(grpc.insecure_channel(CART))
    try:
        cart_stub.AddItem(
            pb.AddItemRequest(
                user_id=user,
                item=pb.CartItem(product_id="OLJCESPC7Z", quantity=1),
            ),
            timeout=timeout_s,
        )
    except Exception as e:  # noqa: BLE001
        return ("cart_add_failed", str(e))

    ch = grpc.insecure_channel(CHECKOUT)
    stub = pbgrpc.CheckoutServiceStub(ch)
    req = pb.PlaceOrderRequest(
        user_id=user,
        user_currency="USD",
        address=pb.Address(
            street_address="1600 Amphitheatre Parkway",
            city="Mountain View",
            state="CA",
            country="United States",
            zip_code=94043,
        ),
        email=f"{user}@example.com",
        credit_card=pb.CreditCardInfo(
            credit_card_number="4432-8015-6152-0454",
            credit_card_expiration_year=2039,
            credit_card_expiration_month=1,
            credit_card_cvv=672,
        ),
    )
    t0 = time.time()
    try:
        resp = stub.PlaceOrder(req, timeout=timeout_s)
        dt = time.time() - t0
        oid = resp.order.order_id
        tracking = resp.order.shipping_tracking_id
        return (f"ok oid={oid} tracking={tracking}", f"{dt*1000:.1f}ms")
    except grpc.RpcError as e:
        dt = time.time() - t0
        code = e.code().name if e.code() else "?"
        return (f"rpc_error code={code} details={e.details()}", f"{dt*1000:.1f}ms")


if __name__ == "__main__":
    mode = sys.argv[3] if len(sys.argv) > 3 else "1"
    n = int(mode)
    for i in range(n):
        result, dur = run_one(i)
        print(f"[{i}] {result} ({dur})")
        time.sleep(0.5)
