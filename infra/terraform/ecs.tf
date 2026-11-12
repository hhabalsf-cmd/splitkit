locals {
  app_port       = 8000
  container_name = "app"
}

resource "aws_ecr_repository" "app" {
  name                 = var.project
  image_tag_mutability = "IMMUTABLE" # every deploy is a commit SHA
  force_delete         = true        # so `terraform destroy` works with images present

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 15 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 15 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = var.project
  setting {
    name  = "containerInsights"
    value = "disabled" # extra cost; logs + ALB metrics are enough here
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

# ---- task execution role: pull image, write logs, read the two secrets -----

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.pg_dsn.arn, aws_secretsmanager_secret.admin_key.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# ---- task definition + service ---------------------------------------------
# The app makes no AWS API calls, so there is no task role.

resource "aws_ecs_task_definition" "app" {
  family                   = var.project
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # matches the GitHub-hosted runner that builds it
  }

  container_definitions = jsonencode([{
    name         = local.container_name
    image        = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = local.app_port, protocol = "tcp" }]
    environment = [
      { name = "WEB_CONCURRENCY", value = "2" },
      { name = "SPLITKIT_POOL_MAX", value = "5" },           # per worker; t4g.micro allows ~80 conns
      { name = "SPLITKIT_TRUSTED_PROXY_HOPS", value = "2" }, # CloudFront -> ALB
      { name = "SPLITKIT_CORS_ORIGINS", value = join(",", var.cors_origins) },
    ]
    secrets = [
      { name = "SPLITKIT_PG_DSN", valueFrom = aws_secretsmanager_secret.pg_dsn.arn },
      { name = "SPLITKIT_ADMIN_KEY", valueFrom = aws_secretsmanager_secret.admin_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "app"
      }
    }
  }])

  depends_on = [aws_secretsmanager_secret_version.pg_dsn, aws_secretsmanager_secret_version.admin_key]
}

resource "aws_ecs_service" "app" {
  name                              = var.project
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.app.arn
  desired_count                     = var.desired_count
  health_check_grace_period_seconds = 60

  capacity_provider_strategy {
    capacity_provider = var.use_fargate_spot ? "FARGATE_SPOT" : "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true # egress without a NAT gateway; SG blocks all inbound but the ALB
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = local.container_name
    container_port   = local.app_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # CI registers new revisions with the commit-SHA image; don't roll them back.
  lifecycle {
    ignore_changes = [task_definition]
  }

  # The target group joins the ALB only via the listener rule (default action is 403).
  depends_on = [aws_lb_listener_rule.from_cloudfront, aws_ecs_cluster_capacity_providers.main]
}
