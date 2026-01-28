import sys
from pathlib import Path
import time
import threading
import uuid
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

    unique_id = str(uuid.uuid4())[:8]
    username = f"seller_test_{idx}_{unique_id}"
    password = f"seller_test_{idx}_{unique_id}"


    create_resp = client.send("create_account", {
        "username": username,
        "password": password
    })
    
    if create_resp is None:
        print(f"Thread-{idx} create_account returned None")
        client.close()
        return
    
    if create_resp.get("status") != "ok":
        print(f"Thread-{idx} create account failed", create_resp)
        client.close()
        return

    # Login with error handling
    resp = client.send("login", {
        "username": username,
        "password": password
    })

    if resp is None:
        print(f"Thread-{idx}login returned None")
        client.close()
        return

    if resp.get("status") != "ok":
        print(f"Thread-{idx} login failed", resp)
        client.close()
        return

    client.session_id = resp["data"]["session_id"]
    print(f"Thread-{idx} Logged in successfully")

    latencies = []

    print(f"Thread-{idx} Running {NUM_OPS} API calls...")

    # Wait for all threads to be ready before starting the benchmark
    thread_barrier.wait()

    for i in range(NUM_OPS):
        t0 = time.perf_counter()
        result = client.send("display_items_for_sale")
        t1 = time.perf_counter()
        
        # Handle None responses
        if result is None:
            print(f"Thread-{idx} display_items_for_sale returned None at iteration {i}")
            continue
            
        latencies.append(t1 - t0)

    if len(latencies) == 0:
        print(f"Thread-{idx} error no operations completed")
        client.close()
        return

    total_time = sum(latencies)
    avg_latency = sum(latencies) / len(latencies)
    throughput = len(latencies) / total_time
    
    with metrics_lock:
        avg_latencies_per_client.append(avg_latency)
        throughputs_per_client.append(throughput)

    print(f"[Thread-{idx}] Completed {len(latencies)}/{NUM_OPS} operations")
    print(f"[Thread-{idx}] Avg Latency: {avg_latency*1000:.2f}ms, Throughput: {throughput:.2f} ops/sec")

    client.close()


def run_evaluation(num_users):
    thread_barrier = threading.Barrier(num_users + 1)
    threads = []
    print(f"Starting Evaluation with {num_users} Concurrent Users")

    for i in range(num_users):
        t = threading.Thread(target=simulate_seller, args=(i, thread_barrier))
        threads.append(t)
        t.start()
    
    # Wait for all threads to be ready
    thread_barrier.wait()

    for t in threads:
        t.join()
        
    print("\n Evaluation Results ")
    
    if len(avg_latencies_per_client) > 0:
        overall_avg_latency = sum(avg_latencies_per_client) / len(avg_latencies_per_client)
        overall_throughput = sum(throughputs_per_client)
        
        print(f"Overall Average Latency: {overall_avg_latency*1000:.2f} ms")
        print(f"Overall Throughput: {overall_throughput:.2f} ops/sec")
    else:
        print("Evaluation Failed")

if __name__ == "__main__":
    run_evaluation(10)