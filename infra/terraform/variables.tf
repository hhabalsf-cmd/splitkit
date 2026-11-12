variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "splitkit"
}

variable "image_tag" {
  description = "Tag Terraform puts in its task definition. CI deploys replace it with the commit SHA."
  type        = string
  default     = "bootstrap"
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "task_cpu" {
  description = "Fargate CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate memory in MiB (numpy/scipy + 2 uvicorn workers need ~1 GiB)."
  type        = number
  default     = 1024
}

variable "use_fargate_spot" {
  description = "~70% cheaper compute; the task can be interrupted (brief ingest gap)."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "GiB of gp3 storage."
  type        = number
  default     = 20
}

variable "db_final_snapshot" {
  description = "Take a final snapshot on destroy (costs a little storage; keeps the experiment data)."
  type        = bool
  default     = true
}

variable "cors_origins" {
  description = "Browser origins allowed to call the public SDK routes, e.g. the LayerLab site."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for o in var.cors_origins : can(regex("^https?://[^/]+$", o))])
    error_message = "Each origin must be scheme://host[:port] with no path or trailing slash."
  }
}

variable "github_repo" {
  description = "owner/name allowed to assume the deploy role (main branch only)."
  type        = string
  default     = "hhabalsf-cmd/splitkit"
}

variable "create_github_oidc_provider" {
  description = "Set false if the account already has the token.actions.githubusercontent.com provider."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  type    = number
  default = 14
}
