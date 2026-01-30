import sys
from pathlib import Path
import time
import threading
import uuid
sys.path.insert(0, str(Path(__file__).parent.parent))
from client.seller.seller import SellerClient  

num_api_calls = 1000

avg_latencies_per_client = []
throughputs_per_client = []
metrics_lock = threading.Lock()

def simulate_seller(idx, thread_barrier, op):
    client = SellerClient()
    client.connect()

    unique_id = str(uuid.uuid4())[:8]
    username = f"seller_test_{idx}_{unique_id}"
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

    # run simulation for 2 operations
    if op == "display_items_for_sale":
        for _ in range(num_api_calls):
            t0 = time.perf_counter()
            result = client.send("display_items_for_sale")
            t1 = time.perf_counter()
            if result:
                latencies.append(t1 - t0)

    # run simulation for 2 operations
    elif op == "get_seller_rating":
        for _ in range(num_api_calls):
            t0 = time.perf_counter()
            result = client.send("get_seller_rating")
            t1 = time.perf_counter()
            if result:
                latencies.append(t1 - t0)
                
    elif op == "register_item_for_sale":
        for i in range(num_api_calls):
            t0 = time.perf_counter()
            result = client.send("register_item_for_sale", {
                "item_name": f"test_{unique_id}_{i}",
                "category": 1,
                "condition_type": "new",
                "price": 1.0,
                "quantity": 1,
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
            target=simulate_seller,
            args=(i, thread_barrier, op)
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print("\nEvaluation Results")
    if avg_latencies_per_client:
        print(f"Avg Latency: {(sum(avg_latencies_per_client)/len(avg_latencies_per_client))*1000:.2f} ms")
        print(f"Total Throughput: {sum(throughputs_per_client):.2f} ops/sec")
    else:
        print("Evaluation Failed")

if __name__ == "__main__":
    run_evaluation(10, "display_items_for_sale")
    run_evaluation(10, "register_item_for_sale")