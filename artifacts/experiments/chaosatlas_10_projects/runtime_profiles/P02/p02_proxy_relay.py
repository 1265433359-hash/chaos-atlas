import socket
import threading


LISTEN = ("172.18.0.1", 7890)
UPSTREAM = ("172.20.96.1", 7890)


def copy_stream(source: socket.socket, target: socket.socket) -> None:
    try:
        while True:
            data = source.recv(65536)
            if not data:
                return
            target.sendall(data)
    finally:
        source.close()
        target.close()


def handle(client: socket.socket) -> None:
    try:
        upstream = socket.create_connection(UPSTREAM, timeout=10)
    except OSError:
        client.close()
        return
    threading.Thread(target=copy_stream, args=(client, upstream), daemon=True).start()
    copy_stream(upstream, client)


def main() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
