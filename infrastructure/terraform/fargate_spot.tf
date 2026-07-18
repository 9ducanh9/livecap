# Optional Fargate Spot capacity (D2).
#
# Off by default. When enabled, the target service runs on FARGATE_SPOT (up to
# ~70% cheaper) instead of on-demand FARGATE. Trade-off: Spot tasks can be
# reclaimed with a 2-minute warning, which drops any in-flight WebSocket
# session. Best for dev/demo, or with fargate_on_demand_base > 0 to keep a
# guaranteed on-demand baseline while extra tasks use Spot.
#
# Requires the cluster to advertise both capacity providers (below). The service
# strategy is wired in ecs.tf (dynamic capacity_provider_strategy).

variable "enable_fargate_spot" {
  description = "Run the target service on FARGATE_SPOT (cheaper, interruptible) instead of on-demand FARGATE."
  type        = bool
  default     = false
}

variable "fargate_spot_weight" {
  description = "Relative weight of FARGATE_SPOT in the capacity-provider strategy."
  type        = number
  default     = 1
}

variable "fargate_on_demand_base" {
  description = "Number of tasks always placed on on-demand FARGATE before Spot is used (0 = all Spot)."
  type        = number
  default     = 0
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  count = var.enable_fargate_spot ? 1 : 0

  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = var.fargate_spot_weight
    base              = 0
  }
}
