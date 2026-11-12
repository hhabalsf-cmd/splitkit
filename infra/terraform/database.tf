# Single-AZ Postgres 16 in private subnets, plus the two app secrets.
#
# Note: generated passwords live in Terraform state. State is in a private,
# encrypted, TLS-only S3 bucket (see bootstrap/), so treat it as sensitive.

resource "random_password" "db" {
  length  = 32
  special = false # keeps the DSN free of URL-escaping
}

resource "random_password" "admin_key" {
  length  = 40
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = var.project
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier     = var.project
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "splitkit"
  username = "splitkit"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  apply_immediately          = true
  copy_tags_to_snapshot      = true

  skip_final_snapshot = !var.db_final_snapshot
  # Timestamped so repeated destroy/re-create cycles don't collide.
  final_snapshot_identifier = var.db_final_snapshot ? "${var.project}-final-${formatdate("YYYYMMDDhhmmss", timestamp())}" : null
  deletion_protection       = false # this is a demo stack; destroy must work

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}

# recovery_window_in_days = 0 lets destroy/re-create reuse the same names.
resource "aws_secretsmanager_secret" "pg_dsn" {
  name                    = "${var.project}/pg-dsn"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "pg_dsn" {
  secret_id = aws_secretsmanager_secret.pg_dsn.id
  # RDS for Postgres 16 enforces TLS (rds.force_ssl=1).
  secret_string = format(
    "postgresql://%s:%s@%s:%d/%s?sslmode=require",
    aws_db_instance.main.username,
    random_password.db.result,
    aws_db_instance.main.address,
    aws_db_instance.main.port,
    aws_db_instance.main.db_name,
  )
}

resource "aws_secretsmanager_secret" "admin_key" {
  name                    = "${var.project}/admin-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "admin_key" {
  secret_id     = aws_secretsmanager_secret.admin_key.id
  secret_string = random_password.admin_key.result
}
