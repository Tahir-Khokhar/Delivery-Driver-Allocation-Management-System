"""
Delivery & Driver Allocation Management System
==============================================
Pure Python - No frameworks, no external packages, in-memory state only.
"""

# ---------------------------------------------------------------------------
# 1. GLOBAL CONFIGURATION & STARTER DATA
# ---------------------------------------------------------------------------
CONFIG = {
    "currency": "$",
    "base_delivery_charge": 5.0,
    "base_driver_earning": 3.0,
    "urgent_surcharge": 0.25,
    "order_bonus_threshold": 150,
    "driver_bonus_pct": 0.10,
    "charge_slabs": (
        (0, 5, 1.00),
        (6, 10, 1.50),
        (11, float("inf"), 2.00)
    ),
    "earning_slabs": (
        (0, 5, 0.80),
        (6, 10, 1.20),
        (11, float("inf"), 1.50)
    ),
}

# State machine for task transitions
VALID_TRANSITIONS = {
    "pending": ("assigned",),
    "assigned": ("picked_up",),
    "picked_up": ("delivered", "failed"),
    "delivered": (),
    "failed": (),
}
TERMINAL_STATUSES = {"delivered", "failed"}

drivers = {
    "D001": {"name": "Ali", "zone": "A", "available": True, "rating": 4.8},
    "D002": {"name": "Ahmed", "zone": "B", "available": True, "rating": 4.5},
    "D003": {"name": "Usman", "zone": "A", "available": False, "rating": 4.9},
    "D004": {"name": "Hamza", "zone": "A", "available": True, "rating": 4.2},
}

deliveries = [
    {"id": "TASK001", "customer": "Customer A", "zone": "A", "distance": 4, "order_amount": 120, "priority": "normal", "status": "pending"},
    {"id": "TASK002", "customer": "Customer B", "zone": "B", "distance": 12, "order_amount": 80, "priority": "urgent", "status": "pending"},
    {"id": "TASK003", "customer": "Customer C", "zone": "A", "distance": 7, "order_amount": 200, "priority": "normal", "status": "pending"},
]

# Stores task_id -> {driver_id, charges, earnings}
task_runtime = {}


# ===========================================================================
# 2. HELPER FUNCTIONS
# ===========================================================================
def is_number(value):
    """Check if a value is an int or float, but not a boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def get_rate(distance, slabs):
    """Find the correct rate per km based on distance slabs."""
    for low, high, rate in slabs:
        if low <= distance <= high:
            return rate
    return slabs[-1][2]  # Fallback to the last slab

def find_task(task_id):
    """Find a task by its ID in the deliveries list."""
    for task in deliveries:
        if task["id"] == task_id:
            return task
    return None


# ===========================================================================
# 3. VALIDATION FUNCTIONS
# ===========================================================================
def validate_task(task):
    """Validate a task dictionary. Returns (True, "") or (False, reason)."""
    required_keys = ("id", "customer", "zone", "distance", "order_amount", "priority", "status")
    for key in required_keys:
        if key not in task:
            return False, f"Missing key: {key}"

    if not isinstance(task["id"], str) or not task["id"]:
        return False, "Invalid ID"
    if not isinstance(task["customer"], str) or not task["customer"]:
        return False, "Invalid customer"
    if not isinstance(task["zone"], str) or not task["zone"]:
        return False, "Invalid zone"
    if not is_number(task["distance"]) or task["distance"] < 0:
        return False, "Invalid distance"
    if not is_number(task["order_amount"]) or task["order_amount"] < 0:
        return False, "Invalid order amount"
    if task["priority"] not in ("normal", "urgent"):
        return False, "Invalid priority"
    if task["status"] not in VALID_TRANSITIONS:
        return False, "Invalid status"

    return True, ""


# ===========================================================================
# 4. CALCULATIONS (*args and **kwargs)
# ===========================================================================
def calculate_delivery_charge(distance, priority="normal", **options):
    """
    Calculate delivery charge. 
    **options allows overriding global CONFIG values (LEGB scope demo).
    """
    base_charge = options.get("base_charge", CONFIG["base_delivery_charge"])
    surcharge_pct = options.get("urgent_surcharge", CONFIG["urgent_surcharge"])
    slabs = options.get("charge_slabs", CONFIG["charge_slabs"])
    currency = options.get("currency", CONFIG["currency"])

    if not is_number(distance) or distance < 0:
        return {"error": "Invalid distance", "final_charge": 0.0, "currency": currency}
    if priority not in ("normal", "urgent"):
        return {"error": "Invalid priority", "final_charge": 0.0, "currency": currency}

    rate = get_rate(distance, slabs)
    distance_charge = distance * rate
    subtotal = base_charge + distance_charge
    
    priority_surcharge = 0.0
    if priority == "urgent":
        priority_surcharge = subtotal * surcharge_pct

    final_charge = subtotal + priority_surcharge

    return {
        "base_charge": base_charge,
        "distance_charge": distance_charge,
        "priority_surcharge": priority_surcharge,
        "final_charge": final_charge,
        "currency": currency
    }

def calculate_driver_earning(distance, order_amount, **options):
    """Calculate driver earning. **options allows overriding CONFIG values."""
    base_earning = options.get("base_earning", CONFIG["base_driver_earning"])
    slabs = options.get("earning_slabs", CONFIG["earning_slabs"])
    threshold = options.get("bonus_threshold", CONFIG["order_bonus_threshold"])
    bonus_pct = options.get("bonus_pct", CONFIG["driver_bonus_pct"])

    if not is_number(distance) or distance < 0:
        return {"error": "Invalid distance", "final_earning": 0.0}
    if not is_number(order_amount) or order_amount < 0:
        return {"error": "Invalid order amount", "final_earning": 0.0}

    rate = get_rate(distance, slabs)
    distance_earning = distance * rate
    subtotal = base_earning + distance_earning

    bonus = 0.0
    if order_amount >= threshold:
        bonus = subtotal * bonus_pct

    final_earning = subtotal + bonus

    return {
        "base_earning": base_earning,
        "distance_earning": distance_earning,
        "bonus": bonus,
        "final_earning": final_earning
    }

def calculate_total(*amounts):
    """Sum any number of amounts using *args. Skips invalid values."""
    total = 0.0
    skipped = 0
    for amount in amounts:
        if is_number(amount) and amount >= 0:
            total += amount
        else:
            skipped += 1
    return {"total": total, "skipped": skipped}


# ===========================================================================
# 5. DRIVER ALLOCATION
# ===========================================================================
def get_eligible_drivers(zone):
    """Return list of available driver IDs in a specific zone."""
    eligible = []
    for driver_id, info in drivers.items():
        if info["available"] and info["zone"] == zone:
            eligible.append(driver_id)
    return eligible

def assign_driver(task_id):
    """Assign the best available driver to a task."""
    task = find_task(task_id)
    if not task:
        return {"ok": False, "reason": f"Task {task_id} not found"}

    is_valid, reason = validate_task(task)
    if not is_valid:
        return {"ok": False, "reason": reason}

    if task["status"] != "pending":
        return {"ok": False, "reason": f"Task is already {task['status']}"}

    eligible = get_eligible_drivers(task["zone"])
    if not eligible:
        return {"ok": False, "reason": f"No drivers available in zone {task['zone']}"}

    # Sort by highest rating, then smallest ID (tie-breaker)
    eligible.sort(key=lambda did: (-drivers[did]["rating"], did))
    best_driver_id = eligible[0]

    # Apply assignment
    task["status"] = "assigned"
    drivers[best_driver_id]["available"] = False

    # Calculate and store runtime info
    charge = calculate_delivery_charge(task["distance"], task["priority"])
    earning = calculate_driver_earning(task["distance"], task["order_amount"])

    task_runtime[task_id] = {
        "driver_id": best_driver_id,
        "delivery_charge": charge["final_charge"],
        "driver_earning": earning["final_earning"]
    }

    return {"ok": True, "reason": "Assigned", "driver_id": best_driver_id}


# ===========================================================================
# 6. STATUS MANAGEMENT
# ===========================================================================
def update_task_status(task_id, new_status):
    """Update task status following the state machine rules."""
    task = find_task(task_id)
    if not task:
        return {"ok": False, "reason": f"Task {task_id} not found"}

    if new_status not in VALID_TRANSITIONS:
        return {"ok": False, "reason": f"Invalid status: {new_status}"}

    old_status = task["status"]
    if old_status in TERMINAL_STATUSES:
        return {"ok": False, "reason": f"Task is already terminal ({old_status})"}

    if new_status not in VALID_TRANSITIONS[old_status]:
        return {"ok": False, "reason": f"Cannot transition from {old_status} to {new_status}"}

    task["status"] = new_status

    released_driver = None
    if new_status in TERMINAL_STATUSES:
        runtime_info = task_runtime.get(task_id)
        if runtime_info:
            driver_id = runtime_info["driver_id"]
            drivers[driver_id]["available"] = True
            released_driver = driver_id

    return {"ok": True, "reason": f"{old_status} -> {new_status}", "released_driver": released_driver}


# ===========================================================================
# 7. REPORTS & INSIGHTS
# ===========================================================================
def generate_driver_report(driver_id):
    """Generate a performance report for a single driver."""
    if driver_id not in drivers:
        return {"error": "Driver not found"}

    driver = drivers[driver_id]
    assigned_tasks = []
    
    for tid, runtime_info in task_runtime.items():
        if runtime_info["driver_id"] == driver_id:
            task = find_task(tid)
            if task:
                assigned_tasks.append(task)

    delivered_tasks = [t for t in assigned_tasks if t["status"] == "delivered"]
    failed_tasks = [t for t in assigned_tasks if t["status"] == "failed"]

    total_distance = sum(t["distance"] for t in delivered_tasks)
    total_earnings = sum(task_runtime[t["id"]]["driver_earning"] for t in delivered_tasks)
    
    if assigned_tasks:
        completion_rate = (len(delivered_tasks) / len(assigned_tasks)) * 100
    else:
        completion_rate = 0.0

    return {
        "driver_id": driver_id,
        "name": driver["name"],
        "zone": driver["zone"],
        "total_assigned": len(assigned_tasks),
        "delivered": len(delivered_tasks),
        "failed": len(failed_tasks),
        "total_distance": total_distance,
        "total_earnings": total_earnings,
        "completion_rate": round(completion_rate, 2)
    }

def print_reports():
    """Print all system reports clearly."""
    cur = CONFIG["currency"]
    
    print("\n" + "=" * 60)
    print("DRIVER PERFORMANCE REPORTS")
    print("=" * 60)
    for did in sorted(drivers.keys()):
        report = generate_driver_report(did)
        if "error" in report:
            continue
            
        print(f"\nDriver {report['driver_id']} - {report['name']} (Zone {report['zone']})")
        print(f"  Assigned    : {report['total_assigned']}")
        print(f"  Delivered   : {report['delivered']}")
        print(f"  Failed      : {report['failed']}")
        print(f"  Distance    : {report['total_distance']:.2f} km")
        print(f"  Earnings    : {cur}{report['total_earnings']:.2f}")
        print(f"  Success Rate: {report['completion_rate']:.2f}%")

    print("\n" + "=" * 60)
    print("SYSTEM DASHBOARD & INSIGHTS")
    print("=" * 60)
    
    total_orders = sum(t["order_amount"] for t in deliveries)
    print(f"Total Order Value: {cur}{total_orders:.2f}")

    # Longest delivery
    longest_task = max(deliveries, key=lambda t: t["distance"])
    print(f"Longest delivery: {longest_task['id']} - {longest_task['distance']} km")

    # Highest value order
    highest_task = max(deliveries, key=lambda t: t["order_amount"])
    print(f"Highest-value order: {highest_task['id']} - {cur}{highest_task['order_amount']:.2f}")

    # Tasks per zone
    zones = set(t["zone"] for t in deliveries)
    tasks_per_zone = {z: sum(1 for t in deliveries if t["zone"] == z) for z in zones}
    print(f"Tasks per zone: {tasks_per_zone}")

    # Available vs Busy
    available = [did for did, d in drivers.items() if d["available"]]
    busy = [did for did, d in drivers.items() if not d["available"]]
    print(f"Available drivers: {available}")
    print(f"Busy drivers     : {busy}")


# ===========================================================================
# 8. EDGE CASE VALIDATION SUITE
# ===========================================================================
def run_edge_case_tests():
    """Run tests to ensure invalid data doesn't crash the system."""
    print("\n" + "#" * 60)
    print("# EDGE CASE VALIDATION SUITE")
    print("#" * 60)

    # 1. Invalid distance
    result = calculate_delivery_charge(-5, "normal")
    print(f"\n[1] Negative Distance -> {result['error']}")

    # 2. Invalid priority
    result = calculate_delivery_charge(5, "express")
    print(f"[2] Invalid Priority -> {result['error']}")

    # 3. Invalid task ID
    result = assign_driver("TASK999")
    print(f"[3] Invalid Task ID -> {result['reason']}")

    # 4. Invalid status transition
    # We need a task to be assigned first to test this properly
    assign_driver("TASK001")  # Moves to 'assigned'
    result = update_task_status("TASK001", "delivered")  # Should fail, must be picked_up first
    print(f"[4] Invalid Transition (assigned -> delivered) -> {result['reason']}")
    
    # Reset task state for main run if needed, or just leave it.
    # For the sake of the test suite, we just print the outcome.

    print("\nEdge cases handled successfully without crashes.")


# ===========================================================================
# 9. SYSTEM EXECUTION
# ===========================================================================
def execute_system():
    """Run the core delivery management system workflow."""
    print("#" * 60)
    print("# DELIVERY & DRIVER ALLOCATION MANAGEMENT SYSTEM")
    print("#" * 60)

    # 1. Charge and Earning Calculations (with **kwargs override)
    print("\n--- CONFIGURATION OVERRIDE DEMONSTRATION ---")
    c1 = calculate_delivery_charge(12, "urgent")
    print(f"Default urgent charge (12km): ${c1['final_charge']:.2f}")
    
    c2 = calculate_delivery_charge(12, "urgent", base_charge=10, urgent_surcharge=0.5)
    print(f"Overridden charge (base=10, surcharge=0.5): ${c2['final_charge']:.2f}")

    # 2. Argument Aggregation (*args)
    print("\n--- ARGUMENT AGGREGATION ---")
    total = calculate_total(5.0, 10.0, "invalid", -2.0, 3.0)
    print(f"Total of valid amounts: {total['total']} (Skipped: {total['skipped']})")

    # 3. Automatic Driver Allocation
    print("\n--- AUTOMATIC DRIVER ALLOCATION ---")
    for task in deliveries:
        result = assign_driver(task["id"])
        if result["ok"]:
            driver_name = drivers[result["driver_id"]]["name"]
            print(f"  {task['id']} assigned to {result['driver_id']} ({driver_name})")
        else:
            print(f"  {task['id']} failed: {result['reason']}")

    # 4. Task Status Workflow
    print("\n--- TASK STATUS WORKFLOW ---")
    # TASK001 is 'assigned', let's move it to picked_up, then delivered
    print(update_task_status("TASK001", "picked_up")["reason"])
    print(update_task_status("TASK001", "delivered")["reason"])

    # 5. Generate Reports
    print_reports()

    # 6. Run Edge Cases
    run_edge_case_tests()

    print("\n" + "#" * 60)
    print("# SYSTEM EXECUTION COMPLETE")
    print("#" * 60)

if __name__ == "__main__":
    execute_system()
