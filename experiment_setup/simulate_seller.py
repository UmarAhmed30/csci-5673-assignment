import sys
from pathlib import Path
import time
import threading
sys.path.insert(0, str(Path(__file__).parent.parent))
from client.seller.seller import SellerClient  

NUM_OPS = 1000

avg_latencies_per_client = []
throughputs_per_client = []
metrics_lock = threading.Lock()

def simulate_seller(idx, thread_barrier):
    client = SellerClient()
    client.connect()
    client.sock.settimeout(5)

    username = f"seller_test_{idx}"
    password = f"seller_test_{idx}"

    client.send("create_account", {
        "username": username,
        "password": password
    })

    resp = client.send("login", {
        "username": username,
        "password": password
    })

    if resp.get("status") != "ok":
        print("Login failed:", resp)
        return

    client.session_id = resp["data"]["session_id"]
    print("Logged in successfully")

    latencies = []

    print(f"Running {NUM_OPS} API calls...")

    thread_barrier.wait()

    for i in range(NUM_OPS):
        t0 = time.perf_counter()
        client.send("display_items_for_sale")
        t1 = time.perf_counter()
        latencies.append(t1 - t0)

    total_time = sum(latencies)
    avg_latency = sum(latencies) / len(latencies)
    throughput = NUM_OPS / total_time
    with metrics_lock:
        avg_latencies_per_client.append(avg_latency)
        throughputs_per_client.append(throughput)

    client.close()


def run_evaluation(num_users):
    thread_barrier = threading.Barrier(num_users + 1)
    threads = []
    print(f"Starting Evaluation with {num_users} Concurrent Users")

    for i in range(num_users):
        t = threading.Thread(target=simulate_seller, args=(i,thread_barrier))
        threads.append(t)
        t.start()
    thread_barrier.wait()

    for t in threads:
        t.join()
        
    print("--- Evaluation Complete ---")

if __name__ == "__main__":
    run_evaluation(10)
