resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "orders" {
  name       = "${local.p}-orders"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_security_group" "db" {
  name        = "${local.p}-orders-db"
  description = "PostgreSQL for the RetailPulse orders database"
  vpc_id      = data.aws_vpc.default.id
}

# Databricks serverless has no fixed egress IP, so dev allows a wide range here. TLS is forced
# below and the password is long and random; see the README for this known gap.
resource "aws_vpc_security_group_ingress_rule" "db" {
  for_each          = toset(var.db_ingress_cidrs)
  security_group_id = aws_security_group.db.id
  cidr_ipv4         = each.value
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
}

resource "aws_db_parameter_group" "orders" {
  name   = "${local.p}-orders-pg17"
  family = "postgres17"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "orders" {
  identifier     = "${local.p}-orders"
  engine         = "postgres"
  engine_version = "17"
  instance_class = var.db_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "retailpulse"
  username = "retailpulse_admin"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.orders.name
  vpc_security_group_ids = [aws_security_group.db.id]
  parameter_group_name   = aws_db_parameter_group.orders.name
  publicly_accessible    = true
  multi_az               = false

  # One day of automated backups costs nothing extra up to the size of the database.
  backup_retention_period      = 1
  auto_minor_version_upgrade   = true
  performance_insights_enabled = false
  monitoring_interval          = 0
  apply_immediately            = true

  # Dev must tear down cleanly. Prod would keep a final snapshot and deletion protection.
  skip_final_snapshot = true
  deletion_protection = false
}
