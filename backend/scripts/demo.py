"""
End-to-end demo of the ContextClock API against a real running server.

Unlike the test suite (which calls route functions directly, or mocks
the Gemini call), this script makes real HTTP requests to a live
uvicorn process and makes real Gemini calls. Run this to see the
whole pipeline work together, not in isolation.

Usage:
    1. In one terminal:  uvicorn app.main:app --reload
    2. In another:       python scripts/demo.py
"""

import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000"


def check_server_is_up() -> None:
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=3)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        print(
            f"Could not reach {BASE_URL}. Start the server first:\n"
            f"    uvicorn app.main:app --reload"
        )
        sys.exit(1)


def create_memory(content: str, category: str, user_id: str, agent_id: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/memories",
        json={"content": content, "category": category, "user_id": user_id, "agent_id": agent_id},
    )
    response.raise_for_status()
    return response.json()


def get_score(memory_id: str) -> dict:
    response = requests.get(f"{BASE_URL}/memories/{memory_id}/score")
    response.raise_for_status()
    return response.json()


def record_access(memory_id: str) -> dict:
    response = requests.post(f"{BASE_URL}/memories/{memory_id}/access")
    response.raise_for_status()
    return response.json()


def print_score(label: str, scored: dict) -> None:
    score = scored["score"]
    print(f"\n--- {label} ---")
    print(f"  final_score:          {score['final_score']}")
    print(f"  staleness_level:      {score['staleness_level']}")
    print(f"  time_decay_score:     {score['time_decay_score']}")
    print(f"  contradiction_score:  {score['contradiction_score']}")
    print(f"  access_anomaly_score: {score['access_anomaly_score']}")
    print(f"  explanation:          {score['explanation']}")


def main() -> None:
    check_server_is_up()
    user_id, agent_id = "demo_user", "demo_agent"

    print("1. Creating a memory: 'User works at Google'")
    memory = create_memory("User works at Google", "employment", user_id, agent_id)
    print(f"   -> id: {memory['id']}")

    scored = get_score(memory["id"])
    print_score("Score immediately after creation", scored)

    print("\n2. Marking the memory as accessed (agent actually used it)")
    accessed = record_access(memory["id"])
    print(f"   -> access_count is now {accessed['access_count']}")

    print("\n3. Creating a newer, contradicting memory: 'User now works at Microsoft'")
    time.sleep(1)  # ensure a clearly later created_at than the first memory
    create_memory("User now works at Microsoft", "employment", user_id, agent_id)

    scored_after_contradiction = get_score(memory["id"])
    print_score("Score for the ORIGINAL memory after the contradiction exists", scored_after_contradiction)

    print(
        "\nNote the contradiction_score and final_score above should have "
        "risen compared to step 1, driven entirely by the newer, "
        "contradicting memory -- this is the real Gemini call, not a mock."
    )


if __name__ == "__main__":
    main()