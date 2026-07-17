# Safety checks for the target stack.
#
# Running more than one backend task requires the shared DynamoDB session store;
# with the in-memory registry each task would enforce limits independently and
# the global cap would be wrong. This check surfaces a clear warning on plan/
# apply when that invariant is violated. (check blocks are advisory: they warn
# without blocking, so they never wedge an apply.)

check "session_store_required_for_multitask" {
  assert {
    condition = var.backend_max_capacity <= 1 || var.enable_dynamodb_session_store
    error_message = join("", [
      "backend_max_capacity is ", tostring(var.backend_max_capacity),
      " but enable_dynamodb_session_store is false. Running more than one task ",
      "requires the shared DynamoDB session store; set ",
      "enable_dynamodb_session_store = true (and SESSION_STORE_BACKEND=dynamodb ",
      "on the task) before raising max capacity."
    ])
  }
}
