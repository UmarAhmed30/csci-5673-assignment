import sys
from pathlib import Path
import time
import threading
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent))
from client.buyer.buyer import BuyerClient  

NUM_API_CALLS = 1000

avg_latencies_per_client = []
throughputs_per_client = []
metrics_lock = threading.Lock()


def simulate_buyer(idx, thread_barrier, op):
    client = BuyerClient()
    client.connect()

    unique_id = str(uuid.uuid4())[:8]
    username = f"buyer_test_{idx}_{unique_id}"
    password = username

    # Create account
    create_resp = client.send("create_account", {
        "username": username,
        "password": password
    })
    if not create_resp or create_resp.get("status") != "ok":
        client.close()
        return

    # Login
    resp = client.send("login", {
        "username": username,
        "password": password
    })
    if not resp or resp.get("status") != "ok":
        client.close()
        return

    client.session_id = resp["data"]["session_id"]
    print(f"Thread-{idx} Logged in")

    latencies = []

    # synchronize start
    thread_barrier.wait()
    start = time.perf_counter()

    # Api calls
    if op == "get_seller_rating":
        for _ in range(NUM_API_CALLS):
            t0 = time.perf_counter()
            result = client.send("get_seller_rating", {
                "seller_id": 1
            })
            t1 = time.perf_counter()
            if result:
                latencies.append(t1 - t0)

    elif op == "search_items":
        for _ in range(NUM_API_CALLS):
            t0 = time.perf_counter()
            result = client.send("search_items", {
                "keywords": ["test"]
            })
            t1 = time.perf_counter()
            if result:
                latencies.append(t1 - t0)


    stop = time.perf_counter()

    if not latencies:
        client.close()
        return

    avg_latency = sum(latencies) / len(latencies)
    throughput = len(latencies) / (stop - start)

    with metrics_lock:
        avg_latencies_per_client.append(avg_latency)
        throughputs_per_client.append(throughput)

    client.close()


def run_evaluation(num_users, op):
    global avg_latencies_per_client, throughputs_per_client
    avg_latencies_per_client = []
    throughputs_per_client = []

    thread_barrier = threading.Barrier(num_users)
    threads = []

    print(f"\nStarting Evaluation: {num_users} users | op={op}")

    for i in range(num_users):
        t = threading.Thread(
            target=simulate_buyer,
            args=(i, thread_barrier, op)
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\nEvaluation Results (Buyer)")
    if avg_latencies_per_client:
        print(f"Avg Latency: {(sum(avg_latencies_per_client)/len(avg_latencies_per_client))*1000:.2f} ms")
        print(f"Total Throughput: {sum(throughputs_per_client):.2f} ops/sec")
    else:
        print("Evaluation Failed")


if __name__ == "__main__":
    run_evaluation(10, "get_seller_rating")
    run_evaluation(10, "search_items")
