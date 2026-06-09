"""Permission governance: tier + action allowlist per worker type. Denials are events."""
from .schemas import PermissionPolicy

TIER_NAMES = {
    0: "READ_ONLY",
    1: "RESEARCH",
    2: "INTERNAL_MODIFICATION",
    3: "BUILD_ACTIONS",
    4: "EXTERNAL_PLATFORM_ACTIONS",
    5: "FINANCIAL_ACTIONS",
    6: "PUBLIC_ACTIONS",
}


class PermissionDenied(Exception):
    pass


def register_policy(store, worker_type, tier, allowed_actions, actor="system"):
    policy = PermissionPolicy(worker_type=worker_type, tier=tier,
                              allowed_actions=list(allowed_actions))
    store.save_policy(policy)
    store.emit("PERMISSION_POLICY_SET", actor, worker_type,
               {"tier": tier, "allowed_actions": list(allowed_actions)})
    return policy


def check(store, worker_type, action, required_tier):
    policy = store.get_policy(worker_type)
    if policy is None:
        denial = "no policy registered"
    elif required_tier > policy.tier:
        denial = f"requires tier {required_tier}, has tier {policy.tier}"
    elif action not in policy.allowed_actions:
        denial = f"action {action!r} not in allowed_actions"
    else:
        return True
    store.emit("PERMISSION_DENIED", worker_type, worker_type,
               {"action": action, "required_tier": required_tier, "why": denial})
    raise PermissionDenied(f"{worker_type}: {denial}")
